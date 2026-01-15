"""
曲线落煤管堵煤早期预警及自愈系统 - 状态机模块
版本: v2.3 (修复紧急停机逻辑 + 添加噪声屏蔽期)
"""

import time
import json
import os
import logging
import numpy as np
from datetime import datetime
import config_final as config

class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating, np.ndarray)):
            return obj.tolist() if isinstance(obj, np.ndarray) else float(obj)
        return super().default(obj)

class ChuteFSM:
    def __init__(self, detector, patter_controller, emergency_stop):
        self.state = "S0_MONITOR"
        self.det = detector
        self.patter = patter_controller
        self.emergency_stop = emergency_stop
        self.retry_count = 0
        self.timer = 0
        self.last_action_ts = None
        
        # [修复v2.3] 添加噪声屏蔽期相关属性
        self.is_masking = False  # 是否处于噪声屏蔽期
        self.mask_counter = 0    # 屏蔽期计数器
        self.MASK_DURATION = getattr(config, 'STABLE_COLLECT_DELAY', 100)  # 屏蔽期长度
        
        # [修复v2.3] 紧急停机是否已触发（防止重复触发）
        self._emergency_triggered = False

    def _save_anomaly(self, rmse, data, recovery_duration=None, rmse_after=None):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        os.makedirs(config.NPY_DIR, exist_ok=True)
        os.makedirs(config.METADATA_DIR, exist_ok=True)
        
        # 文件名包含状态信息以便区分
        npy_path = os.path.join(config.NPY_DIR, f"err_{ts}_{self.state}_{rmse:.4f}.npy")
        np.save(npy_path, data)
        
        metadata = {
            'timestamp': ts, 
            'rmse': float(rmse), 
            'state': self.state,
            'thresh_a': float(self.det.thresh_a),
            'thresh_b': float(self.det.thresh_b),
            'retry_count': self.retry_count,
            'recovery_duration': recovery_duration,
            'rmse_after_recovery': rmse_after
        }
        metadata_path = os.path.join(config.METADATA_DIR, f"err_{ts}_{self.state}_{rmse:.4f}.json")
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, cls=NumpyEncoder)
        
        logging.debug(f"异常样本已保存: {npy_path}")

    def _start_masking_period(self):
        """开始噪声屏蔽期（拍打动作后的波动抑制）"""
        self.is_masking = True
        self.mask_counter = 0
        logging.debug(f"进入噪声屏蔽期 ({self.MASK_DURATION} ticks)")

    def _update_masking(self):
        """更新噪声屏蔽期状态"""
        if self.is_masking:
            self.mask_counter += 1
            if self.mask_counter >= self.MASK_DURATION:
                self.is_masking = False
                self.mask_counter = 0
                logging.debug("噪声屏蔽期结束")

    def step(self, rmse, data):
        """
        状态机主逻辑
        
        状态转换图:
        S0_MONITOR -> S1_PRE_WARN (rmse > thresh_a)
        S1_PRE_WARN -> S2_ACTION (rmse > thresh_b 或 持续超时)
        S1_PRE_WARN -> S0_MONITOR (rmse < thresh_a，恢复正常)
        S2_ACTION -> S3_RECOVERY (执行拍打后)
        S3_RECOVERY -> S0_MONITOR (自愈成功)
        S3_RECOVERY -> S2_ACTION (自愈失败，重试)
        S3_RECOVERY -> S4_ALARM (达到最大重试次数)
        S4_ALARM -> [锁定] (需要人工干预)
        """
        
        # 更新噪声屏蔽期
        self._update_masking()
        
        # [修复v2.3] S4 紧急状态锁定 - 只在首次进入时触发紧急停机
        if self.state == "S4_ALARM":
            if not self._emergency_triggered:
                logging.critical("!!! 达到最大重试次数，执行紧急停机 !!!")
                if self.emergency_stop:
                    self.emergency_stop.trigger(async_mode=True)
                self._emergency_triggered = True
            return self.state

        # S0: 正常监控状态
        if self.state == "S0_MONITOR":
            # 噪声屏蔽期内不做状态跳转判断
            if self.is_masking:
                return self.state
                
            if rmse > self.det.thresh_b: 
                # 严重异常，直接进入动作状态
                self.state = "S2_ACTION"
                self.last_action_ts = time.time()
                logging.warning(f"[S0->S2] 严重异常! RMSE: {rmse:.4f} > thresh_b: {self.det.thresh_b:.4f}")
            elif rmse > self.det.thresh_a:
                # 轻微异常，进入预警状态
                self.state = "S1_PRE_WARN"
                self.timer = 0
                logging.info(f"[S0->S1] 进入预警状态. RMSE: {rmse:.4f} > thresh_a: {self.det.thresh_a:.4f}")
                
        # S1: 预警状态
        elif self.state == "S1_PRE_WARN":
            self.timer += 1
            if rmse > self.det.thresh_b or self.timer >= config.T1_PREWARN_TICKS:
                self.state = "S2_ACTION"
                self.last_action_ts = time.time()
                logging.warning(f"[S1->S2] 持续异常触发拍打. timer={self.timer}, RMSE={rmse:.4f}")
            elif rmse < self.det.thresh_a: 
                # 恢复正常
                self.state = "S0_MONITOR"
                logging.info(f"[S1->S0] 预警解除，恢复正常. RMSE: {rmse:.4f}")
                
        # S2: 动作状态（执行拍打）
        elif self.state == "S2_ACTION":
            logging.warning(f"触发拍打器动作! RMSE: {rmse:.4f}, 重试次数: {self.retry_count}")
            
            # 保存触发瞬间的异常数据
            self._save_anomaly(rmse, data)
            
            # 触发拍打器
            if self.patter:
                self.patter.trigger()
            
            # 开始噪声屏蔽期
            self._start_masking_period()
            
            # 进入恢复等待状态
            self.state = "S3_RECOVERY"
            self.timer = 0
            
        # S3: 恢复等待状态
        elif self.state == "S3_RECOVERY":
            self.timer += 1
            
            # 等待足够时间后判断是否自愈成功
            if self.timer >= config.T2_RECOVERY_WAIT_TICKS:
                duration = time.time() - self.last_action_ts if self.last_action_ts else 0
                
                if rmse < self.det.thresh_a:
                    # 自愈成功
                    logging.info(f"✓ 自愈成功! 耗时: {duration:.1f}s, RMSE: {rmse:.4f}")
                    self._save_anomaly(rmse, data, recovery_duration=duration, rmse_after=rmse)
                    self.retry_count = 0
                    self.state = "S0_MONITOR"
                else:
                    # 自愈失败
                    self.retry_count += 1
                    logging.warning(f"✗ 自愈失败! RMSE: {rmse:.4f}, 重试次数: {self.retry_count}/{config.MAX_RETRIES}")
                    
                    if self.retry_count >= config.MAX_RETRIES:
                        # 达到最大重试次数，保存严重故障样本并进入紧急状态
                        logging.critical(f"!!! 达到最大重试次数 ({config.MAX_RETRIES})，进入紧急状态 !!!")
                        self._save_anomaly(rmse, data)
                        self.state = "S4_ALARM"
                        # 注意：紧急停机将在下一次step()调用时触发
                    else:
                        # 重试拍打
                        self.state = "S2_ACTION"
                        self.last_action_ts = time.time()
                        
        return self.state

    def reset(self):
        """
        重置状态机（仅用于维护后的手动恢复）
        警告：生产环境中应该由人工确认后才能调用此方法
        """
        logging.warning("状态机被手动重置")
        self.state = "S0_MONITOR"
        self.retry_count = 0
        self.timer = 0
        self.is_masking = False
        self.mask_counter = 0
        self._emergency_triggered = False
        
    def get_status(self) -> dict:
        """获取状态机当前状态信息"""
        return {
            'state': self.state,
            'retry_count': self.retry_count,
            'timer': self.timer,
            'is_masking': self.is_masking,
            'mask_counter': self.mask_counter,
            'emergency_triggered': self._emergency_triggered,
            'thresh_a': self.det.thresh_a if self.det else 0,
            'thresh_b': self.det.thresh_b if self.det else 0
        }