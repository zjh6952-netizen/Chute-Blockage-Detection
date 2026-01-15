import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import threading
import logging
import random
import os
import glob
from queue import Queue, Empty, Full
from collections import deque
from datetime import datetime
import config_final as config
from models import CurvedChuteCAE

class AnomalyDetector:
    def __init__(self):
        self.device = torch.device(config.DEVICE)
        self.model = CurvedChuteCAE().to(self.device)
        self.optimizer = optim.Adam(self.model.parameters(), lr=config.LEARNING_RATE)
        self.criterion = nn.MSELoss()
        
        # 混合精度初始化
        self.use_amp = config.USE_MIXED_PRECISION and self.device.type == 'cuda'
        self.scaler = torch.amp.GradScaler('cuda') if self.use_amp else None
        
        self.lock = threading.Lock()
        
        # 【架构修复】输入维度改为 (Batch, Sensors, Dim)，保留空间分辨率
        self.input_buffer = torch.zeros((1, config.ACTIVE_SENSORS, config.FEATURE_DIM), device=self.device)
        self.batch_buffer = torch.zeros((config.TRAIN_BATCH_SIZE, config.ACTIVE_SENSORS, config.FEATURE_DIM), device=self.device)
        
        self.thresh_a = 0.0
        self.thresh_b = 0.0
        
        # 【抗漂移逻辑】用于动态计算阈值的滑动窗口
        self.rmse_history = deque(maxlen=config.RMSE_WINDOW_SIZE)
        
        self.golden_buffer = deque(maxlen=config.MAX_GOLDEN_BUFFER_SIZE)
        self.recent_buffer = deque(maxlen=config.MAX_RECENT_BUFFER_SIZE)
        
        # 【抗污染逻辑】稳定期计数器
        self.stable_counter = 0 
        
        # 【基准持久化】尝试加载历史Golden基准
        self._load_golden_buffer()

        self.train_queue = Queue(maxsize=5)
        self.stop_event = threading.Event()
        self.train_thread = threading.Thread(target=self._train_worker, daemon=True)
        self.train_thread.start()
        self.frame_counter = 0

    def _load_golden_buffer(self):
        """从磁盘加载永久基准集"""
        path = getattr(config, 'GOLDEN_DATA_PATH', "golden_samples.npy")
        if os.path.exists(path):
            try:
                data = np.load(path)
                self.golden_buffer.extend(data)
                logging.info(f"成功加载持久化基准集: {len(data)} 样本")
            except Exception as e:
                logging.error(f"加载基准集失败: {e}")

    def _train_worker(self):
        while not self.stop_event.is_set():
            try:
                batch_np = self.train_queue.get(timeout=1.0)
                with self.lock:
                    self.batch_buffer.copy_(torch.from_numpy(batch_np))
                    self.model.train()
                    self.optimizer.zero_grad()
                    if self.use_amp:
                        with torch.amp.autocast('cuda'):
                            output = self.model(self.batch_buffer)
                            loss = self.criterion(output, self.batch_buffer)
                        self.scaler.scale(loss).backward()
                        self.scaler.step(self.optimizer)
                        self.scaler.update()
                    else:
                        output = self.model(self.batch_buffer)
                        loss = self.criterion(output, self.batch_buffer)
                        loss.backward()
                        self.optimizer.step()
                self.train_queue.task_done()
            except Empty: continue

    def collect_sample(self, feat, current_state):
        """
        【抗污染修复】
        1. 只有在 S0_MONITOR 状态下才收集数据
        2. 增加稳定期延迟，防止动作刚结束后的残余波动进入训练集
        """
        if current_state != "S0_MONITOR":
            self.stable_counter = 0
            return

        self.stable_counter += 1
        if self.stable_counter < getattr(config, 'STABLE_COLLECT_DELAY', 100):
            return

        self.recent_buffer.append(feat)
        self.frame_counter += 1
        
        if self.frame_counter >= config.TRAIN_EVERY_N_SAMPLES:
            self.frame_counter = 0
            if len(self.recent_buffer) >= config.TRAIN_BATCH_SIZE:
                # 按照 config 中的比例混合采样 (例如 2:8)
                n_golden = int(config.TRAIN_BATCH_SIZE * config.MIXED_SAMPLE_GOLDEN_RATIO)
                n_recent = config.TRAIN_BATCH_SIZE - n_golden
                
                if len(self.golden_buffer) >= n_golden:
                    g_samples = random.sample(self.golden_buffer, n_golden)
                    r_samples = random.sample(self.recent_buffer, n_recent)
                    # 混合数据 shape: (Batch, 15, 513)
                    batch = np.array(g_samples + r_samples, dtype=np.float32)
                    try:
                        self.train_queue.put_nowait(batch)
                    except Full: pass

    def calibrate(self, raw_samples, sensor_obj):
        """
        【持久化修复】
        1. 设定能量基准
        2. 将归一化后的Golden数据持久化存盘
        3. 计算初始动态阈值
        """
        sensor_obj.set_scale(raw_samples)
        norm_samples = [np.clip(s / (sensor_obj.global_scale + 1e-8), 0, 1) for s in raw_samples]
        
        # 存盘防止断电丢失锚点
        path = getattr(config, 'GOLDEN_DATA_PATH', "golden_samples.npy")
        np.save(path, np.array(norm_samples))
        
        # 更新内存Buffer
        self.golden_buffer.clear()
        self.golden_buffer.extend(norm_samples)
        
        # Shape: (Samples, 15, 513)
        tensor_data = torch.as_tensor(np.array(norm_samples), dtype=torch.float32).to(self.device)
        
        with self.lock:
            self.model.train()
            for epoch in range(config.CALIBRATION_EPOCHS):
                self.optimizer.zero_grad()
                output = self.model(tensor_data)
                loss = self.criterion(output, tensor_data)
                loss.backward()
                self.optimizer.step()
            
            self.model.eval()
            with torch.no_grad():
                recons = self.model(tensor_data)
                # 计算全通道RMSE
                rmses = torch.sqrt(torch.mean((recons - tensor_data)**2, dim=(1,2))).cpu().numpy()
                self.thresh_a = np.mean(rmses) + config.THRESH_A_MULTIPLIER * np.std(rmses)
                self.thresh_b = np.mean(rmses) + config.THRESH_B_MULTIPLIER * np.std(rmses)
                
                # 初始化历史窗口
                self.rmse_history.extend(rmses.tolist())
        
        logging.info(f"校准及基准持久化完成. 阈值A: {self.thresh_a:.4f}, B: {self.thresh_b:.4f}")

    def predict(self, feat):
        """执行推理并记录RMSE历史"""
        with self.lock:
            # feat shape: (15, 513)
            self.input_buffer[0].copy_(torch.from_numpy(feat.astype(np.float32)))
            self.model.eval()
            with torch.no_grad():
                recon = self.model(self.input_buffer)
                rmse = torch.sqrt(torch.mean((recon - self.input_buffer)**2)).item()
        
        return rmse

    def update_dynamic_thresholds(self, current_rmse, current_state):
        """
        【漂移自适应修复】
        根据最近正常状态下的均值和标准差动态调整阈值
        """
        if current_state == "S0_MONITOR":
            self.rmse_history.append(current_rmse)
            if len(self.rmse_history) >= 100:
                avg = np.mean(self.rmse_history)
                std = np.std(self.rmse_history)
                # 动态缓慢修正阈值
                self.thresh_a = avg + config.THRESH_A_MULTIPLIER * std
                self.thresh_b = avg + config.THRESH_B_MULTIPLIER * std

    def save_checkpoint(self, path=None):
        if path is None:
            os.makedirs(config.MODEL_CHECKPOINT_DIR, exist_ok=True)
            path = os.path.join(config.MODEL_CHECKPOINT_DIR, f"model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pth")
        
        with self.lock:
            checkpoint = {
                'model_state_dict': self.model.state_dict(),
                'thresh_a': self.thresh_a,
                'thresh_b': self.thresh_b,
                'rmse_history': list(self.rmse_history)
            }
            torch.save(checkpoint, path)
            logging.info(f"模型快照已存盘: {path}")

        ckpt_files = sorted(glob.glob(os.path.join(config.MODEL_CHECKPOINT_DIR, "model_*.pth")))
        if len(ckpt_files) > 5:
            for old_file in ckpt_files[:-5]:
                try: os.remove(old_file)
                except: pass

    def shutdown(self):
        self.stop_event.set()
        if self.train_thread.is_alive():
            self.train_thread.join(timeout=2)