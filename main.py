"""
曲线落煤管堵煤早期预警及自愈系统 - 主程序
版本: v2.3 
"""

import time
import logging
import signal
import sys
import os
import threading
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

import config_final as config
from audio_source import SensorSource
from detector_engine import AnomalyDetector
from state_machine import ChuteFSM
from utils import Watchdog
from patter_controller import PatterController
from emergency_stop import EmergencyStopController
from health_analyst_fixed import HealthAnalyst

# --- 全局单例对象引用（供 API 和主循环共享） ---
class SharedState:
    def __init__(self):
        self.source = None
        self.detector = None
        self.fsm = None
        self.patter = None
        self.estop = None
        self.analyst = HealthAnalyst()
        self.current_rmse = 0.0
        self.start_time = datetime.now()

ss = SharedState()

# --- FastAPI 定义 ---
app = FastAPI(title="曲线溜槽健康监测系统 API", version="2.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/status")
async def get_status():
    """实时状态查询接口"""
    fsm_status = ss.fsm.get_status() if ss.fsm else {}
    return {
        "state": fsm_status.get('state', 'INIT'),
        "rmse": round(ss.current_rmse, 6),
        "thresh_a": round(fsm_status.get('thresh_a', 0), 4),
        "thresh_b": round(fsm_status.get('thresh_b', 0), 4),
        "retry_count": fsm_status.get('retry_count', 0),
        "is_masking": fsm_status.get('is_masking', False),
        "uptime": str(datetime.now() - ss.start_time),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/report")
async def get_report():
    """获取健康趋势分析报告"""
    report, _ = ss.analyst.analyze_wear_trend()
    return report if report else {"error": "No data available"}

@app.get("/anomalies")
async def get_anomalies():
    """获取最近的异常事件"""
    return ss.analyst.get_latest_anomalies(20)

@app.post("/control/patter")
async def manual_patter():
    """手动触发拍打器"""
    if ss.patter:
        success = ss.patter.trigger(force_sync=False)
        return {"status": "success" if success else "busy", "msg": "Manual patter triggered"}
    return {"status": "error", "msg": "Patter not initialized"}

@app.post("/control/reset")
async def reset_system():
    """重置紧急停机状态（需要人工确认后调用）"""
    if ss.estop and ss.fsm:
        ss.estop.reset()
        ss.fsm.reset()
        return {"status": "success", "msg": "System reset completed"}
    return {"status": "error", "msg": "System not initialized"}

@app.get("/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "components": {
            "source": ss.source is not None,
            "detector": ss.detector is not None,
            "fsm": ss.fsm is not None,
            "patter": ss.patter is not None,
            "estop": ss.estop is not None
        }
    }

# --- Web 服务启动函数 ---
def run_api_server():
    """启动 Web 服务 (默认端口 8000)"""
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="error")

# --- 主程序逻辑 ---
def main():
    # 1. 配置日志
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL),
        format='%(asctime)s.%(msecs)03d [%(levelname)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(config.LOG_FILE, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    logging.info("="*60)
    logging.info("曲线落煤管堵煤早期预警及自愈系统 v2.3")
    logging.info("="*60)
    logging.info("系统正在启动 (API + 监控主循环)...")

    # 2. 验证配置
    errors, warnings = config.validate_config()
    if errors:
        for err in errors: 
            logging.error(f"配置错误: {err}")
        sys.exit(1)
    for warn in warnings: 
        logging.warning(f"配置警告: {warn}")

    # 3. 硬件加速优化
    config.apply_jetson_optimizations()
    
    # 4. 初始化模块并存入共享状态
    try:
        logging.info("初始化音频采集模块...")
        ss.source = SensorSource()
        
        logging.info("初始化异常检测引擎...")
        ss.detector = AnomalyDetector()
        
        logging.info("初始化拍打器控制器...")
        ss.patter = PatterController()
        
        logging.info("初始化紧急停机控制器...")
        ss.estop = EmergencyStopController()
        
        logging.info("初始化状态机...")
        ss.fsm = ChuteFSM(ss.detector, ss.patter, ss.estop)
        
        logging.info("所有模块初始化完成")
        
    except Exception as e:
        logging.critical(f"硬件初始化失败: {e}", exc_info=True)
        sys.exit(1)
    
    # 5. 启动 API 服务线程
    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    logging.info("API 服务已在后台启动 (Port: 8000)")

    # 6. 看门狗
    def on_watchdog_timeout():
        logging.critical("看门狗超时！主线程可能已卡死。")
        # 尝试保存检查点
        if ss.detector:
            try:
                ss.detector.save_checkpoint()
            except:
                pass
        os._exit(1)

    watchdog = Watchdog(timeout=config.WATCHDOG_TIMEOUT, callback=on_watchdog_timeout)
    if config.ENABLE_WATCHDOG:
        watchdog.start()
        logging.info(f"看门狗已启动 (超时: {config.WATCHDOG_TIMEOUT}s)")

    # 7. 优雅退出处理
    def signal_handler(sig, frame):
        logging.info("接收到退出信号，正在保存状态...")
        try:
            if ss.detector: 
                ss.detector.save_checkpoint()
            if ss.source: 
                ss.source.close()
            if ss.detector: 
                ss.detector.shutdown()
            if ss.patter:
                ss.patter.cleanup()
            if ss.estop:
                ss.estop.cleanup()
        except Exception as e:
            logging.error(f"清理资源时出错: {e}")
        logging.info("系统已安全退出")
        sys.exit(0)
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # 8. 校准阶段
    logging.info(f"开始冷启动校准 (需要 {config.INIT_CALIBRATION_SAMPLES} 个样本)...")
    c_data = []
    while len(c_data) < config.INIT_CALIBRATION_SAMPLES:
        f = ss.source.get_fft_feature(is_calibrating=True)
        if f is not None: 
            c_data.append(f)
            # 进度显示
            progress = len(c_data) / config.INIT_CALIBRATION_SAMPLES * 100
            print(f"\r校准进度: {len(c_data)}/{config.INIT_CALIBRATION_SAMPLES} ({progress:.0f}%)", end="", flush=True)
    print()  # 换行
    
    ss.detector.calibrate(c_data, ss.source)
    ss.detector.save_checkpoint()
    logging.info("冷启动校准完成")

    # 9. 主循环
    logging.info("="*60)
    logging.info("监控系统已进入运行状态")
    logging.info("="*60)
    
    process_every_n = max(1, int(config.SAMPLE_INTERVAL * config.SAMPLE_RATE / config.CHUNK_SIZE))
    sample_counter = 0
    loop_counter = 0

    while True:
        try:
            feat = ss.source.get_fft_feature()
            if feat is not None:
                # 传入当前状态，用于防污染判断
                ss.detector.collect_sample(feat, ss.fsm.state)
                
                sample_counter += 1
                if sample_counter >= process_every_n:
                    sample_counter = 0
                    
                    # 预测
                    rmse = ss.detector.predict(feat)
                    ss.current_rmse = rmse
                    
                    # 更新动态阈值
                    ss.detector.update_dynamic_thresholds(rmse, ss.fsm.state)
                    
                    # 状态机步进
                    state = ss.fsm.step(rmse, feat)
                    
                    # 喂狗
                    watchdog.feed()
                    
                    # 界面显示（带噪声屏蔽期提示）
                    mask_str = " [MASK]" if ss.fsm.is_masking else ""
                    retry_str = f" R:{ss.fsm.retry_count}" if ss.fsm.retry_count > 0 else ""
                    print(f"\r[{state:12}]{mask_str}{retry_str} | RMSE: {rmse:.4f} | "
                          f"A: {ss.detector.thresh_a:.4f} | B: {ss.detector.thresh_b:.4f}", 
                          end="", flush=True)
                    
                    # 定期保存检查点
                    loop_counter += 1
                    if loop_counter >= config.MODEL_SAVE_INTERVAL:
                        loop_counter = 0
                        ss.detector.save_checkpoint()
            
            time.sleep(0.005)
            
        except KeyboardInterrupt:
            logging.info("接收到键盘中断...")
            break
        except Exception as e:
            logging.error(f"主循环异常: {e}", exc_info=True)
            time.sleep(1)

    # 清理
    signal_handler(None, None)


if __name__ == "__main__":
    main()