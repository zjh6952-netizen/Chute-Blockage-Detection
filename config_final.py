"""
曲线落煤管堵煤早期预警及自愈系统 - 最终生产版配置
硬件平台: Jetson Orin NX
传感器: 15个骨传导传感器
版本: v2.2 (修复配置验证逻辑)
"""

import torch
import os

MAX_STORAGE_GB = 10              # 异常样本最大占用空间
GOLDEN_DATA_PATH = "golden_samples.npy" # 基准集存盘路径
STABLE_COLLECT_DELAY = 100       # 从S3回S0后，延迟N个采样点再收集，防止残余波动污染
RMSE_WINDOW_SIZE = 1000          # 动态阈值滑动窗口大小
# ============================================================================
# 1. 硬件采集参数
# ============================================================================
ACTIVE_SENSORS = 15         # 实际使用的传感器数量
HARDWARE_CHANNELS = 16      # 硬件设备的物理通道数（音频采集卡实际支持的通道数）

# 设备识别
DEVICE_INDEX = None              # 将在运行时自动查找（不再硬编码）
DEVICE_NAME_FRAGMENT = "USB"     # 设备名称关键词，用于自动识别

# 音频参数
SAMPLE_RATE = 44100        # 采样率 44.1kHz
CHUNK_SIZE = 1024          # 每次读取帧数（约23ms数据）
FEATURE_DIM = 513          # CHUNK_SIZE // 2 + 1 (FFT实际输出)

# 设备调试开关
LIST_DEVICES = False       # 设为True时，程序启动后列出所有音频设备然后退出

# ============================================================================
# 2. 预警阈值与逻辑（参考技术文档）
# ============================================================================
THRESH_A_MULTIPLIER = 3.0  # 预警阈值：mean + 3*std
THRESH_B_MULTIPLIER = 6.0  # 触发阈值：mean + 6*std
T1_PREWARN_TICKS = 10      # S1预警状态持续10个采样周期后触发拍打
T2_RECOVERY_WAIT_TICKS = 30 # S3恢复等待30个采样周期后判定自愈成功/失败
MAX_RETRIES = 3            # 拍打重试次数上限，超过则紧急停机
SAMPLE_INTERVAL = 0.1      # 采样处理间隔（秒）

# ============================================================================
# 3. 算法配置（针对Jetson Orin NX优化）
# ============================================================================
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
USE_MIXED_PRECISION = True  # 在GPU上使用混合精度加速（FP16）
NUM_WORKERS = 2             # 数据加载线程数

# 动态样本库策略 (FIFO Dual-Buffer) [修复：明确Golden与Recent的比例]
BUFFER_CAPACITY = 2000      # Recent Buffer总容量
GOLDEN_RATIO = 0.2          # Golden Buffer占比 (训练时20% Golden + 80% Recent)
MAX_GOLDEN_BUFFER_SIZE = 500  # Golden Buffer最大容量
MAX_RECENT_BUFFER_SIZE = 2000  # Recent Buffer最大容量
LEARNING_RATE = 5e-5        # 学习率（防止模型快速漂移）
TRAIN_EVERY_N_SAMPLES = 20  # 增量学习触发间隔
TRAIN_BATCH_SIZE = 16
MIXED_SAMPLE_GOLDEN_RATIO = 0.2  # 混合采样时Golden的比例 (2:8)

# ============================================================================
# 4. 日志与存储
# ============================================================================
LOG_FILE = "chute_monitor.log"
LOG_LEVEL = "INFO"          # 生产环境使用INFO
NPY_DIR = "anomaly_samples"
METADATA_DIR = "anomaly_metadata"
SATURATION_THRESHOLD = 0.95
SATURATION_COUNT_LIMIT = 50

# ============================================================================
# 5. 冷启动校准
# ============================================================================
INIT_CALIBRATION_SAMPLES = 100
CALIBRATION_EPOCHS = 100

# ============================================================================
# 6. 安全设置
# ============================================================================
THREAD_JOIN_TIMEOUT = 5.0
MODEL_SAVE_INTERVAL = 1000
MODEL_CHECKPOINT_DIR = "checkpoints"
ENABLE_WATCHDOG = True           # 启用看门狗
WATCHDOG_TIMEOUT = 60            # 看门狗超时时间（秒）

# ============================================================================
# 7. 音频缓冲区管理
# ============================================================================
MAX_BUFFER_FRAMES = 2

# ============================================================================
# 8. 拍打器接口配置
# ============================================================================
PATTER_ENABLED = True
PATTER_DURATION = 0.5            # 拍打持续时间（秒）
PATTER_GPIO_PIN = None           # GPIO引脚号（实际接线后配置）
PATTER_RELAY_TYPE = "NO"         # 继电器类型：NO(常开) 或 NC(常闭)
PATTER_ASYNC = True              # [新增] 是否异步执行拍打（不阻塞主线程）

# ============================================================================
# 9. 紧急停机接口配置
# ============================================================================
ENABLE_EMERGENCY_STOP = True     # 是否启用紧急停机物理输出
EMERGENCY_STOP_GPIO_PIN = None   # 紧急停机GPIO引脚
EMERGENCY_STOP_SIGNAL_TYPE = "HIGH"  # 触发信号类型：HIGH 或 LOW
EMERGENCY_STOP_HOLD_TIME = 5.0   # 紧急停机信号保持时间（秒）

# ============================================================================
# 10. 远程监控接口
# ============================================================================
ENABLE_REMOTE_MONITORING = False
REMOTE_API_PORT = 8080
ENABLE_MQTT = False
MQTT_BROKER = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC_PREFIX = "chute/sensor"

# ============================================================================
# 11. 性能监控
# ============================================================================
ENABLE_PERFORMANCE_LOGGING = True
PERFORMANCE_LOG_INTERVAL = 100

# ============================================================================
# 12. 数据备份
# ============================================================================
ENABLE_DAILY_BACKUP = True
BACKUP_DIR = "backups"
BACKUP_RETENTION_DAYS = 30


# ============================================================================
# 辅助函数
# ============================================================================
def find_audio_device_index(name_fragment=None, required_channels=None):
    """
    根据设备名称自动查找音频设备索引
    
    Args:
        name_fragment: 设备名称关键词（例如："USB", "Audio"）
        required_channels: 需要的最小通道数
    
    Returns:
        int: 设备索引，如果未找到返回None
    """
    import pyaudio
    
    name_fragment = name_fragment or DEVICE_NAME_FRAGMENT
    required_channels = required_channels or HARDWARE_CHANNELS
    
    try:
        p = pyaudio.PyAudio()
        count = p.get_device_count()
        
        candidates = []
        
        for i in range(count):
            try:
                dev_info = p.get_device_info_by_index(i)
                
                # 必须是输入设备
                if dev_info['maxInputChannels'] == 0:
                    continue
                
                # 必须满足通道数要求
                if dev_info['maxInputChannels'] < required_channels:
                    continue
                
                # 检查名称匹配
                if name_fragment and name_fragment.lower() in dev_info['name'].lower():
                    candidates.append((i, dev_info))
                elif not name_fragment:
                    candidates.append((i, dev_info))
                    
            except Exception:
                continue
        
        p.terminate()
        
        if candidates:
            # 返回通道数最多的设备
            best = max(candidates, key=lambda x: x[1]['maxInputChannels'])
            idx, info = best
            print(f"✓ 自动定位到音频设备:")
            print(f"  索引: {idx}")
            print(f"  名称: {info['name']}")
            print(f"  通道数: {info['maxInputChannels']}")
            return idx
        else:
            print(f"✗ 未找到匹配的音频设备 (关键词: '{name_fragment}', 需要≥{required_channels}通道)")
            return None
            
    except Exception as e:
        print(f"✗ 查找音频设备时出错: {e}")
        return None


def validate_config():
    """
    验证配置的有效性
    
    Returns:
        tuple: (errors: list, warnings: list)
    """
    errors = []
    warnings = []
    
    # 检查FEATURE_DIM
    expected_feature_dim = CHUNK_SIZE // 2 + 1
    if FEATURE_DIM != expected_feature_dim:
        errors.append(
            f"FEATURE_DIM配置错误: 应为{expected_feature_dim}, 当前为{FEATURE_DIM}"
        )
    
    # 检查通道数配置
    if ACTIVE_SENSORS > HARDWARE_CHANNELS:
        errors.append(
            f"传感器数量({ACTIVE_SENSORS})不能超过硬件通道数({HARDWARE_CHANNELS})"
        )
    
    # [修复v2.2] 检查硬件通道数是否为常见值
    common_channel_counts = [1, 2, 4, 8, 16, 32, 64]
    if HARDWARE_CHANNELS not in common_channel_counts:
        warnings.append(
            f"HARDWARE_CHANNELS = {HARDWARE_CHANNELS} 不是常见配置，"
            f"大多数音频设备只支持 {common_channel_counts}"
        )
    
    # 检查CUDA可用性
    if DEVICE == "cuda" and not torch.cuda.is_available():
        warnings.append(
            "配置为使用CUDA，但当前环境CUDA不可用，将降级到CPU"
        )
    
    # 检查GPIO引脚配置
    if PATTER_ENABLED and PATTER_GPIO_PIN is None:
        warnings.append(
            "拍打器已启用但未配置GPIO引脚，将以模拟模式运行"
        )
    
    if ENABLE_EMERGENCY_STOP and EMERGENCY_STOP_GPIO_PIN is None:
        warnings.append(
            "紧急停机已启用但未配置GPIO引脚，将无法执行物理停机"
        )
    
    # 检查拍打时长
    if PATTER_DURATION > 1.0:
        warnings.append(
            f"拍打持续时间({PATTER_DURATION}s)较长，可能导致电磁阀过热，建议≤0.5s"
        )
    
    # 检查混合采样比例
    if MIXED_SAMPLE_GOLDEN_RATIO < 0.1 or MIXED_SAMPLE_GOLDEN_RATIO > 0.5:
        warnings.append(
            f"混合采样Golden比例({MIXED_SAMPLE_GOLDEN_RATIO})建议在0.1-0.5之间"
        )
    
    # [修复v2.2] 检查Golden Buffer容量是否合理
    if MAX_GOLDEN_BUFFER_SIZE < INIT_CALIBRATION_SAMPLES:
        warnings.append(
            f"MAX_GOLDEN_BUFFER_SIZE({MAX_GOLDEN_BUFFER_SIZE})小于"
            f"INIT_CALIBRATION_SAMPLES({INIT_CALIBRATION_SAMPLES})，"
            "Golden Buffer可能无法存储全部校准样本"
        )
    
    # 检查目录权限
    for directory in [NPY_DIR, METADATA_DIR, MODEL_CHECKPOINT_DIR, BACKUP_DIR]:
        try:
            os.makedirs(directory, exist_ok=True)
            test_file = os.path.join(directory, ".write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except Exception as e:
            errors.append(f"无法在目录 {directory} 中写入: {e}")
    
    return errors, warnings


def apply_jetson_optimizations():
    """应用Jetson Orin NX特定的优化设置"""
    if torch.cuda.is_available():
        # 启用TensorFloat-32 (TF32) 加速
        torch.backends.cuda.matmul.allow_tf32 = True
        torch.backends.cudnn.allow_tf32 = True
        
        # 启用cuDNN自动调优
        torch.backends.cudnn.benchmark = True
        
        # 设置内存分配器策略
        os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'max_split_size_mb:128'
        
        print("✓ Jetson Orin NX CUDA优化已启用")
        print(f"  - 设备: {torch.cuda.get_device_name(0)}")
        print(f"  - CUDA版本: {torch.version.cuda}")
        print(f"  - 显存: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")


# ============================================================================
# 配置说明
# ============================================================================
"""
【v2.2 关键修复】

1. 卷积自编码器维度修复：
   - 使用自适应裁剪确保输出维度与输入完全匹配
   - 输入513 → 输出513（不再是520）

2. PyTorch混合精度API更新：
   - torch.cuda.amp.GradScaler() → torch.amp.GradScaler('cuda')
   - torch.cuda.amp.autocast() → torch.amp.autocast('cuda')

3. 新增list_devices()方法：
   - SensorSource类现在支持列出所有音频设备

4. 改进异常处理：
   - 不再静默吞掉异常
   - 记录完整堆栈信息便于调试

5. Golden Buffer优化：
   - 现在存储全部校准样本（最多MAX_GOLDEN_BUFFER_SIZE个）
   - 而不是只存储20%

【部署前检查清单】
1. 运行 check_devices.py 确认设备名称
2. 设置 DEVICE_NAME_FRAGMENT 为匹配的关键词
3. 确认 HARDWARE_CHANNELS 与实际设备一致
4. 配置 PATTER_GPIO_PIN 和 EMERGENCY_STOP_GPIO_PIN
5. 验证用户权限: sudo usermod -aG gpio,audio $USER

"""
