import numpy as np
import pyaudio
import logging
import config_final as config

class SensorSource:
    def __init__(self, device_index=None):
        self.pa = pyaudio.PyAudio()
        self.global_scale = 1.0
        self.saturation_counter = 0
        self.stream = None
        
        if device_index is None:
            device_index = config.find_audio_device_index()
            if device_index is None:
                logging.error("无法自动找到合适的音频设备")
                self.pa.terminate()
                raise RuntimeError("音频设备未找到")
        
        self.device_index = device_index
        self._validate_device()
        
        try:
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=config.HARDWARE_CHANNELS,
                rate=config.SAMPLE_RATE,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=config.CHUNK_SIZE
            )
            logging.info(f"音频设备初始化成功: 索引 {self.device_index}")
        except Exception as e:
            self.pa.terminate()
            raise e

    def _validate_device(self):
        device_info = self.pa.get_device_info_by_index(self.device_index)
        if device_info['maxInputChannels'] < config.HARDWARE_CHANNELS:
            raise RuntimeError(f"设备通道数不足")

    def get_fft_feature(self, is_calibrating=False):
        try:
            waiting = self.stream.read_available()
            if waiting > config.CHUNK_SIZE * config.MAX_BUFFER_FRAMES:
                discard_frames = waiting - config.CHUNK_SIZE
                self.stream.read(discard_frames, exception_on_overflow=False)
            
            raw_data = self.stream.read(config.CHUNK_SIZE, exception_on_overflow=False)
            # data shape: (CHANNELS, CHUNK_SIZE)
            data = np.frombuffer(raw_data, dtype=np.int16).reshape(-1, config.HARDWARE_CHANNELS).T
            data = data[:config.ACTIVE_SENSORS, :] # 保留15个传感器
            
            # 对每个通道进行FFT
            fft_all = np.abs(np.fft.rfft(data, axis=1)) # shape: (15, 513)
            signal_fft = fft_all[:, :config.FEATURE_DIM] 
            
            if is_calibrating: return signal_fft
            
            # 归一化
            norm_feat = np.clip(signal_fft / (self.global_scale + 1e-8), 0, 1)
            return norm_feat
        except Exception as e:
            logging.warning(f"采集异常: {e}")
            return None

    def set_scale(self, raw_samples):
        q95 = np.percentile(raw_samples, 95)
        std = np.std(raw_samples)
        self.global_scale = q95 + 2 * std
        logging.info(f"能量基准已设定: {self.global_scale:.2f}")

    def close(self):
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
        self.pa.terminate()