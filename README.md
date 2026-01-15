# 曲线落煤管堵煤早期预警及自愈系统


## 📋 目录

- [系统概述](#系统概述)
- [核心特性](#核心特性)
- [系统架构](#系统架构)
- [硬件要求](#硬件要求)
- [软件依赖](#软件依赖)
- [安装部署](#安装部署)
- [配置说明](#配置说明)
- [使用指南](#使用指南)
- [API接口文档](#api接口文档)
- [故障排查](#故障排查)
- [维护指南](#维护指南)
- [性能优化](#性能优化)
- [开发说明](#开发说明)
- [版本历史](#版本历史)
- [常见问题](#常见问题)
- [许可证](#许可证)

---

## 🎯 系统概述

曲线落煤管堵煤早期预警及自愈系统是一套基于**深度学习**和**状态机控制**的智能监测系统，专为煤矿、电厂等工业场景中的曲线落煤管设计。系统通过**15个骨传导传感器**实时采集振动信号，利用**卷积自编码器（CAE）**进行异常检测，并通过**自动拍打器**实现自愈功能，在严重故障时触发**紧急停机**保护。

### 应用场景

- **煤矿**: 井下运输系统的曲线落煤管堵煤监测
- **电厂**: 输煤系统的落煤管堵塞预警
- **港口**: 散货装卸系统的溜槽监测
- **水泥厂**: 原料输送管道的堵塞检测

### 核心价值

- ⚡ **早期预警**: 在堵煤形成初期即可检测到异常振动模式
- 🔧 **自动自愈**: 通过拍打器自动清除轻微堵塞，减少人工干预
- 🛡️ **安全保护**: 严重故障时自动停机，防止设备损坏和安全事故
- 🚀 **边缘计算**: 基于Jetson Orin NX实现实时推理，延迟<50ms
- 📈 **持续学习**: 动态阈值自适应调整，适应设备磨损等长期变化
- 📊 **数据分析**: 完整的异常事件记录和趋势分析报告

---

## ✨ 核心特性

### 1. 智能检测引擎

#### 深度学习模型
- **卷积自编码器（CAE）**: 针对多通道时序信号设计的深度学习模型
- **输入维度**: 15通道 × 513频点（FFT特征）
- **模型结构**: 3层编码器 + 3层解码器
- **训练策略**: 增量学习，Golden Buffer + Recent Buffer混合训练

#### 异常检测算法
- **RMSE指标**: 重构误差作为异常度量
- **动态阈值**: 基于滑动窗口（1000样本）的自适应阈值
  - 预警阈值：`thresh_a = mean + 3σ`
  - 触发阈值：`thresh_b = mean + 6σ`
- **噪声屏蔽**: 拍打动作后100个采样点的波动抑制

### 2. 五状态机控制

```
┌─────────────────────────────────────────────────────────────┐
│                     状态转换图                                │
└─────────────────────────────────────────────────────────────┘

    S0_MONITOR (正常监控)
         │
         │ RMSE > thresh_a
         ↓
    S1_PRE_WARN (预警状态)
         │
         │ RMSE > thresh_b 或持续10次采样
         ↓
    S2_ACTION (执行拍打)
         │
         │ 拍打完成
         ↓
    S3_RECOVERY (恢复等待)
         │
         ├─ 30次采样后 RMSE < thresh_a → S0_MONITOR (自愈成功)
         │
         └─ 30次采样后 RMSE ≥ thresh_a → 重试拍打
              │
              └─ 重试次数 ≥ 3 → S4_ALARM (紧急停机)
```

**状态说明**:

- **S0_MONITOR**: 正常监控状态，持续检测RMSE
- **S1_PRE_WARN**: 轻微异常预警，RMSE超过阈值A
- **S2_ACTION**: 触发拍打器清除堵塞
- **S3_RECOVERY**: 等待拍打效果，判断是否自愈成功
- **S4_ALARM**: 紧急停机，需要人工干预

### 3. 硬件接口

#### GPIO拍打器控制
- **异步非阻塞**: 拍打动作不阻塞主监控循环
- **继电器支持**: 常开（NO）和常闭（NC）继电器
- **可配置时长**: 默认0.5秒，可调整
- **状态查询**: 实时查询拍打器动作状态

#### 紧急停机输出
- **可配置信号**: HIGH或LOW触发
- **信号保持**: 可设置停机信号保持时间（默认5秒）
- **防重复触发**: S4状态下只触发一次
- **手动重置**: 提供API接口用于故障排除后的系统重置

#### 多通道音频采集
- **16通道采集卡**: 支持最多16个传感器
- **实际使用**: 15个传感器（保留1个通道备用）
- **采样率**: 44.1kHz
- **FFT特征**: 实时提取513维频域特征

### 4. 远程监控

#### RESTful API
- `GET /status` - 实时状态查询（RMSE、阈值、状态机状态）
- `GET /report` - 健康趋势分析报告
- `GET /anomalies` - 异常事件历史
- `POST /control/patter` - 手动触发拍打器
- `POST /control/reset` - 系统重置（需人工确认）
- `GET /health` - 健康检查

#### 数据分析
- **异常样本归档**: 自动保存异常时刻的振动数据
- **元数据记录**: RMSE、阈值、重试次数等完整信息
- **趋势分析**: 基于历史数据的磨损趋势预测

### 5. 生产级特性

#### 可靠性保障
- **看门狗保护**: 检测主线程卡死并自动重启
- **断电保护**: Golden Buffer持久化存储
- **优雅退出**: 信号处理确保状态安全保存
- **异常恢复**: 完整的错误处理和日志记录

#### 性能优化
- **GPU加速**: 利用Jetson Orin NX的CUDA核心
- **混合精度**: FP16推理加速，不损失精度
- **异步训练**: 独立线程进行增量学习
- **内存管理**: FIFO缓冲区防止内存溢出

---

## 🏗️ 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         硬件层                                   │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────┐            |
│  │ 15x骨传导    │  │  拍打器       │  │  急停输出     │            |
│  │ 传感器       │  │  (继电器)     │  │  (GPIO)      │            │
│  └──────┬──────┘  └──────┬───────┘  └──────┬───────┘            │
└─────────┼─────────────────┼──────────────────┼──────────────────┘
          │                 │                  │
┌─────────┼─────────────────┼──────────────────┼──────────────────┐
│         │                 │                  │   驱动层          │
│  ┌──────▼──────┐   ┌──────▼───────┐  ┌──────▼────────┐          │
│  │ PyAudio     │   │ Jetson.GPIO  │  │ Jetson.GPIO   │          │
│  │ (16通道)     │   │ (拍打控制)    │  │ (停机控制)     │          ｜
│  └──────┬──────┘   └──────┬───────┘  └──────┬────────┘          │
└─────────┼─────────────────┼──────────────────┼──────────────────┘
          │                 │                  │
┌─────────┼─────────────────┼──────────────────┼──────────────────┐
│         │                 │                  │   应用层          │
│  ┌──────▼──────────┐      │                  │                  │
│  │ audio_source.py │      │                  │                  │
│  │ • 实时采集       │       │                  │                 ｜
│  │ • FFT特征提取    │       │                  │                 ｜
│  │ • 能量归一化      │      │                  │                  ｜ 
│  └──────┬──────────┘       │                  │                  │
│         │                  │                  │                  │
│  ┌──────▼──────────────────┴──────────────────┴──────┐          │
│  │ detector_engine.py                                │          │
│  │ • CAE模型推理 (GPU加速)                            │           │
│  │ • RMSE计算与异常检测                               │           │
│  │ • 动态阈值更新                                     │            │
│  │ • 增量学习 (Golden + Recent Buffer)               │            │
│  └──────┬─────────────────────────────────────────────┘          │
│         │                                                        │
│  ┌──────▼──────────────────────────────────────────┐             │
│  │ state_machine.py                                │            │
│  │ • 五状态转换逻辑 (S0→S1→S2→S3→S4)                 │             │
│  │ • 拍打触发决策                                     │            │
│  │ • 紧急停机决策                                     │            │
│  │ • 噪声屏蔽期管理                                   │            │
│  └──────┬───────────────────────────────────────────┘            │
│         │                                                        │
│  ┌──────▼──────────┐  ┌──────────────────┐                       │
│  │ patter_ctrl.py  │  │ emergency_stop.py│                       │
│  │ • 异步拍打执行    │  │ • 停机信号输出     │                       │ 
│  │ • 继电器控制      │  │ • 信号保持        │                       │
│  └─────────────────┘  └──────────────────┘                       │
│                                                                  │
│  ┌───────────────────────────────────────────────────┐           │
│  │ main.py (主控程序)                                 │           │
│  │ • 初始化所有模块                                    │           │
│  │ • 冷启动校准 (100样本)                              │           │
│  │ • 主监控循环                                       │            │
│  │ • 看门狗监控                                       │            │
│  │ • 信号处理与优雅退出                                 │           │
│  └───────────────────────────────────────────────────┘           │
│                                                                  │
│  ┌───────────────────────────────────────────────────┐           │
│  │ FastAPI (Web监控接口)                               │          │
│  │ • /status    - 实时状态查询                         │           │
│  │ • /report    - 健康趋势报告                         │           │
│  │ • /anomalies - 异常事件列表                         │           │
│  │ • /control/* - 手动控制接口                         │           │
│  └───────────────────────────────────────────────────┘           │
└──────────────────────────────────────────────────────────────────┘
```

### 模块说明

| 模块 | 文件 | 功能描述 |
|------|------|----------|
| 音频采集 | `audio_source.py` | 16通道音频采集、FFT特征提取、能量归一化 |
| 异常检测 | `detector_engine.py` | CAE模型推理、RMSE计算、动态阈值、增量学习 |
| 状态机 | `state_machine.py` | 五状态转换逻辑、决策控制 |
| 拍打器 | `patter_controller.py` | GPIO控制、异步执行、继电器驱动 |
| 紧急停机 | `emergency_stop.py` | 停机信号输出、信号保持 |
| 健康分析 | `health_analyst_fixed.py` | 趋势分析、磨损预测 |
| 主程序 | `main.py` | 系统初始化、主循环、API服务 |
| 配置 | `config_final.py` | 所有可配置参数 |
| 工具 | `utils.py` | 看门狗、辅助函数 |
| 检测工具 | `check_devices.py` | 音频设备检测和测试 |

---

## 🖥️ 硬件要求

### 核心控制器

**NVIDIA Jetson Orin NX (推荐配置)**
- **GPU**: 1024-core NVIDIA Ampere架构
- **CPU**: 8-core Arm Cortex-A78AE @ 2.0GHz
- **内存**: 8GB LPDDR5 (最低要求: 8GB)
- **存储**: 64GB NVMe SSD (推荐: 128GB以上)
- **功耗**: 10W - 25W (可配置)

**替代方案**:
- Jetson Xavier NX (性能稍低，但可满足需求)
- Jetson AGX Orin (性能更强，适合扩展)

### 传感器系统

**骨传导传感器 × 15**
- **类型**: 加速度传感器或骨传导麦克风
- **频响范围**: 20Hz - 20kHz
- **灵敏度**: -38dB ± 2dB
- **接口**: 3.5mm TRS 或 XLR
- **安装方式**: 磁吸或螺栓固定在落煤管外壁

**推荐型号**:
- Dayton Audio DAEX25 (性价比高)
- TDK PiezoHapt (工业级)

**音频采集卡 (16通道USB音频接口)**
- **采样率**: 44.1kHz / 48kHz
- **位深**: 16-bit / 24-bit
- **接口**: USB 2.0 / USB 3.0
- **供电**: USB供电或外部电源

**推荐型号**:
- Behringer U-PHORIA UMC1820 (8通道×2，性价比高)
- Focusrite Scarlett 18i20 (专业级)
- MOTU 16A (高端选择)

### 执行器

**拍打器（电磁振动器）**
- **类型**: 电磁式振动器或气动锤
- **工作电压**: 12V / 24V DC
- **功率**: 20W - 100W
- **响应时间**: < 10ms
- **安装位置**: 落煤管易堵塞位置

**继电器模块**
- **触点容量**: ≥ 10A (用于拍打器控制)
- **线圈电压**: 5V (由GPIO驱动)
- **类型**: 常开（NO）或常闭（NC）可选

**急停输出**
- **接触器**: ≥ 10A / 250VAC
- **控制信号**: 3.3V / 5V GPIO
- **连接**: 连接到皮带运输机控制系统

### 附件

**电源系统**
- 工业级开关电源: 12V/24V DC，功率 ≥ 150W
- UPS电源（可选，用于断电保护）

**防护外壳**
- 等级: IP54 或更高（防尘防水）
- 材质: ABS或金属
- 散热: 风扇或散热片

**连接线缆**
- 屏蔽音频线: 15米内使用低阻抗线缆
- GPIO杜邦线: 26AWG
- 网线: CAT5e或以上（用于远程访问）

---

## 📦 软件依赖

### 操作系统

**JetPack SDK 5.x / 6.x**
- 基于 Ubuntu 20.04 / 22.04
- 包含 CUDA 11.7+ 和 cuDNN
- TensorRT 8.x (可选，用于模型加速)

### Python 版本

- **Python 3.8** 或更高版本
- 建议使用 Python 3.10 (性能更优)

### 核心依赖

```txt
# requirements.txt

# 深度学习框架
torch>=2.0.0              # PyTorch (支持CUDA 11.7+)
# 安装GPU版本: pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 数据处理
numpy>=1.24.0             # 数值计算
pandas>=1.5.0             # 数据分析

# 音频处理
pyaudio>=0.2.11           # 音频采集 (需要先安装PortAudio开发库)

# Web服务
fastapi                   # RESTful API框架
uvicorn                   # ASGI服务器
pydantic                  # 数据验证

# 科学计算与可视化
scipy>=1.9.0              # 科学计算
matplotlib>=3.5.0         # 可视化 (可选，用于调试)

# GPIO控制 (Jetson专用)
Jetson.GPIO               # sudo pip3 install Jetson.GPIO
```

### 系统库依赖

```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install -y \
    portaudio19-dev \
    python3-dev \
    build-essential \
    libsndfile1 \
    python3-pip \
    git

# CentOS/RHEL
sudo yum install -y \
    portaudio-devel \
    python3-devel \
    gcc \
    gcc-c++ \
    make
```

---

## 🚀 安装部署

### 1. 环境准备

#### 1.1 系统配置

```bash
# 检查JetPack版本
sudo apt-cache show nvidia-jetpack

# 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 安装系统依赖
sudo apt-get install -y \
    portaudio19-dev \
    python3-dev \
    build-essential \
    libsndfile1 \
    python3-pip \
    python3-venv \
    git \
    htop
```

#### 1.2 用户权限配置

```bash
# 添加用户到GPIO和audio组
sudo usermod -aG gpio $USER
sudo usermod -aG audio $USER

# 重新登录以使权限生效
logout
# 或者
su - $USER
```

#### 1.3 克隆代码

```bash
# 创建项目目录
mkdir -p ~/chute-monitor
cd ~/chute-monitor

# 克隆代码（如果使用Git）
git clone https://github.com/yourusername/chute-monitor.git .

# 或者解压源代码包
# unzip chute-monitor-v2.3.zip
# cd chute-monitor-v2.3
```

### 2. Python环境配置

#### 2.1 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级pip
pip install --upgrade pip
```

#### 2.2 安装依赖

```bash
# 安装PyTorch (GPU版本)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 安装其他依赖
pip install -r requirements.txt

# 安装Jetson.GPIO (需要root权限)
sudo pip3 install Jetson.GPIO
```

#### 2.3 验证安装

```bash
# 测试PyTorch和CUDA
python3 << EOF
import torch
print(f"PyTorch版本: {torch.__version__}")
print(f"CUDA可用: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA版本: {torch.version.cuda}")
    print(f"GPU设备: {torch.cuda.get_device_name(0)}")
EOF

# 测试PyAudio
python3 -c "import pyaudio; print('PyAudio版本:', pyaudio.__version__)"

# 测试GPIO (需要root)
sudo python3 << EOF
try:
    import Jetson.GPIO as GPIO
    print("Jetson.GPIO已安装")
except ImportError:
    print("Jetson.GPIO未安装或不可用")
EOF
```

### 3. 硬件连接

#### 3.1 音频采集卡连接

```
传感器1-15 → 音频采集卡通道1-15
音频采集卡 → Jetson Orin NX (USB 3.0接口)
```

**检测音频设备**:

```bash
# 运行设备检测工具
python3 check_devices.py

# 输出示例:
# ================================================================================
#                     音频设备检测工具
# ================================================================================
# 
# 检测到 3 个音频设备:
# 
# ================================================================================
# 设备索引: 0
# 设备名称: USB Audio Device
# 最大输入通道: 16
# 最大输出通道: 0
# 默认采样率: 44100 Hz
# 
# ================================================================================
# 
# 推荐设备索引: 0
# 推荐设备名称: USB Audio Device
# 支持通道数:   16
# 
# ✓ 该设备支持 15 通道配置
# 
# 在 config_final.py 中设置:
#   DEVICE_NAME_FRAGMENT = "USB"
# ================================================================================
```

#### 3.2 GPIO引脚连接

**Jetson Orin NX GPIO引脚图**: 参考官方文档

**拍打器连接**:
```
Jetson GPIO Pin 7 (BCM 4) → 继电器模块 IN
继电器模块 COM → 拍打器电源 +
继电器模块 NO → 拍打器
拍打器另一端 → 电源地
```

**紧急停机连接**:
```
Jetson GPIO Pin 11 (BCM 17) → 接触器线圈
接触器触点 → 皮带运输机控制回路
```

**配置GPIO引脚**:

```python
# 编辑 config_final.py
PATTER_GPIO_PIN = 4              # BCM编号，对应物理引脚7
PATTER_RELAY_TYPE = "NO"         # 常开继电器
EMERGENCY_STOP_GPIO_PIN = 17     # BCM编号，对应物理引脚11
EMERGENCY_STOP_SIGNAL_TYPE = "HIGH"  # 高电平触发
```

### 4. 配置文件设置

#### 4.1 编辑 config_final.py

```python
# ============================================================================
# 1. 硬件采集参数
# ============================================================================
ACTIVE_SENSORS = 15              # 实际使用的传感器数量
HARDWARE_CHANNELS = 16           # 音频采集卡通道数
DEVICE_NAME_FRAGMENT = "USB"     # 设备名称关键词（根据check_devices.py输出设置）

# ============================================================================
# 2. 预警阈值与逻辑
# ============================================================================
THRESH_A_MULTIPLIER = 3.0        # 预警阈值：mean + 3*std
THRESH_B_MULTIPLIER = 6.0        # 触发阈值：mean + 6*std
T1_PREWARN_TICKS = 10            # S1预警持续10个采样周期后触发拍打
T2_RECOVERY_WAIT_TICKS = 30      # S3恢复等待30个采样周期
MAX_RETRIES = 3                  # 拍打重试次数上限

# ============================================================================
# 8. 拍打器接口配置
# ============================================================================
PATTER_ENABLED = True
PATTER_DURATION = 0.5            # 拍打持续时间（秒）
PATTER_GPIO_PIN = 4              # GPIO引脚号（BCM编号）
PATTER_RELAY_TYPE = "NO"         # 继电器类型：NO(常开) 或 NC(常闭)
PATTER_ASYNC = True              # 异步执行拍打

# ============================================================================
# 9. 紧急停机接口配置
# ============================================================================
ENABLE_EMERGENCY_STOP = True
EMERGENCY_STOP_GPIO_PIN = 17     # 紧急停机GPIO引脚
EMERGENCY_STOP_SIGNAL_TYPE = "HIGH"  # 触发信号类型
EMERGENCY_STOP_HOLD_TIME = 5.0   # 停机信号保持时间（秒）
```

#### 4.2 验证配置

```bash
# 运行配置验证
python3 << EOF
import config_final as config
errors, warnings = config.validate_config()

print("配置验证结果:")
if errors:
    print("\n❌ 错误:")
    for err in errors:
        print(f"  - {err}")
else:
    print("\n✅ 配置无错误")

if warnings:
    print("\n⚠️  警告:")
    for warn in warnings:
        print(f"  - {warn}")
else:
    print("\n✅ 配置无警告")
EOF
```

### 5. 首次运行

#### 5.1 测试模式运行

```bash
# 激活虚拟环境
source venv/bin/activate

# 首次运行（会进行冷启动校准）
python3 main.py

# 输出示例:
# ============================================================
# 曲线落煤管堵煤早期预警及自愈系统 v2.3
# ============================================================
# 系统正在启动 (API + 监控主循环)...
# ✓ 自动定位到音频设备:
#   索引: 0
#   名称: USB Audio Device
#   通道数: 16
# 音频设备初始化成功: 索引 0
# ✓ Jetson Orin NX CUDA优化已启用
#   - 设备: NVIDIA Orin
#   - CUDA版本: 11.4
#   - 显存: 7.62 GB
# 拍打器运行在模拟模式（GPIO不可用或未配置引脚）
# 紧急停机运行在模拟模式（GPIO不可用或未配置引脚）
# API 服务已在后台启动 (Port: 8000)
# 看门狗已启动 (超时: 60s)
# 开始冷启动校准 (需要 100 个样本)...
# 校准进度: 100/100 (100%)
# 校准及基准持久化完成. 阈值A: 0.0234, B: 0.0456
# ============================================================
# 监控系统已进入运行状态
# ============================================================
# [S0_MONITOR  ] | RMSE: 0.0198 | A: 0.0234 | B: 0.0456
```

#### 5.2 测试API接口

在另一个终端：

```bash
# 查询实时状态
curl http://localhost:8000/status

# 输出示例:
# {
#   "state": "S0_MONITOR",
#   "rmse": 0.019834,
#   "thresh_a": 0.0234,
#   "thresh_b": 0.0456,
#   "retry_count": 0,
#   "is_masking": false,
#   "uptime": "0:05:23.456789",
#   "timestamp": "2026-01-15T10:30:45.123456"
# }

# 健康检查
curl http://localhost:8000/health

# 手动触发拍打（测试）
curl -X POST http://localhost:8000/control/patter
```

### 6. 生产部署

#### 6.1 创建systemd服务

```bash
# 创建服务文件
sudo nano /etc/systemd/system/chute-monitor.service
```

```ini
[Unit]
Description=Chute Blockage Early Warning and Self-Healing System
After=network.target

[Service]
Type=simple
User=jetson
WorkingDirectory=/home/jetson/chute-monitor
Environment="PATH=/home/jetson/chute-monitor/venv/bin"
ExecStart=/home/jetson/chute-monitor/venv/bin/python3 /home/jetson/chute-monitor/main.py
Restart=always
RestartSec=10

# 日志配置
StandardOutput=journal
StandardError=journal
SyslogIdentifier=chute-monitor

[Install]
WantedBy=multi-user.target
```

```bash
# 重新加载systemd配置
sudo systemctl daemon-reload

# 启用服务（开机自启动）
sudo systemctl enable chute-monitor.service

# 启动服务
sudo systemctl start chute-monitor.service

# 查看服务状态
sudo systemctl status chute-monitor.service

# 查看日志
journalctl -u chute-monitor.service -f
```

#### 6.2 配置日志轮转

```bash
# 创建日志轮转配置
sudo nano /etc/logrotate.d/chute-monitor
```

```
/home/jetson/chute-monitor/chute_monitor.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    create 0644 jetson jetson
}
```

#### 6.3 配置防火墙

```bash
# 如果使用ufw
sudo ufw allow 8000/tcp
sudo ufw reload

# 如果使用iptables
sudo iptables -A INPUT -p tcp --dport 8000 -j ACCEPT
sudo iptables-save | sudo tee /etc/iptables/rules.v4
```

---

## ⚙️ 配置说明

### 核心配置参数

| 参数分类 | 参数名 | 默认值 | 说明 |
|---------|--------|--------|------|
| **硬件采集** | `ACTIVE_SENSORS` | 15 | 实际使用的传感器数量 |
| | `HARDWARE_CHANNELS` | 16 | 音频采集卡通道数 |
| | `SAMPLE_RATE` | 44100 | 采样率（Hz） |
| | `CHUNK_SIZE` | 1024 | 每次读取帧数 |
| **预警阈值** | `THRESH_A_MULTIPLIER` | 3.0 | 预警阈值倍数 |
| | `THRESH_B_MULTIPLIER` | 6.0 | 触发阈值倍数 |
| | `T1_PREWARN_TICKS` | 10 | 预警持续次数 |
| | `T2_RECOVERY_WAIT_TICKS` | 30 | 恢复等待次数 |
| | `MAX_RETRIES` | 3 | 最大重试次数 |
| **算法配置** | `LEARNING_RATE` | 5e-5 | 学习率 |
| | `TRAIN_BATCH_SIZE` | 16 | 训练批次大小 |
| | `TRAIN_EVERY_N_SAMPLES` | 20 | 触发训练间隔 |
| | `MIXED_SAMPLE_GOLDEN_RATIO` | 0.2 | Golden样本比例 |
| **拍打器** | `PATTER_ENABLED` | True | 是否启用拍打器 |
| | `PATTER_DURATION` | 0.5 | 拍打持续时间（秒） |
| | `PATTER_GPIO_PIN` | None | GPIO引脚号 |
| | `PATTER_RELAY_TYPE` | "NO" | 继电器类型 |
| **紧急停机** | `ENABLE_EMERGENCY_STOP` | True | 是否启用紧急停机 |
| | `EMERGENCY_STOP_GPIO_PIN` | None | GPIO引脚号 |
| | `EMERGENCY_STOP_SIGNAL_TYPE` | "HIGH" | 触发信号类型 |
| | `EMERGENCY_STOP_HOLD_TIME` | 5.0 | 信号保持时间（秒） |

### 阈值调优指南

#### 场景1: 误报率过高

**症状**: 系统频繁触发预警，但实际并无堵塞

**解决方案**:
```python
# 增大预警阈值倍数
THRESH_A_MULTIPLIER = 4.0  # 从3.0增加到4.0
THRESH_B_MULTIPLIER = 8.0  # 从6.0增加到8.0

# 增加预警持续时间
T1_PREWARN_TICKS = 15      # 从10增加到15
```

#### 场景2: 漏报率过高

**症状**: 实际发生堵塞时，系统未能及时预警

**解决方案**:
```python
# 降低预警阈值倍数
THRESH_A_MULTIPLIER = 2.5  # 从3.0降低到2.5
THRESH_B_MULTIPLIER = 5.0  # 从6.0降低到5.0

# 减少预警持续时间
T1_PREWARN_TICKS = 5       # 从10减少到5
```

#### 场景3: 拍打效果不佳

**症状**: 拍打后堵塞未能清除，频繁重试

**解决方案**:
```python
# 增加拍打持续时间
PATTER_DURATION = 0.8      # 从0.5增加到0.8

# 增加恢复等待时间
T2_RECOVERY_WAIT_TICKS = 50  # 从30增加到50

# 增加最大重试次数
MAX_RETRIES = 5            # 从3增加到5
```

---

## 📖 使用指南

### 日常操作

#### 启动系统

```bash
# 方法1: 直接运行
cd ~/chute-monitor
source venv/bin/activate
python3 main.py

# 方法2: 使用systemd（生产环境）
sudo systemctl start chute-monitor

# 方法3: 后台运行
nohup python3 main.py > /dev/null 2>&1 &
```

#### 停止系统

```bash
# 方法1: Ctrl+C（如果在前台运行）
# 按 Ctrl+C，系统会优雅退出

# 方法2: 使用systemd
sudo systemctl stop chute-monitor

# 方法3: 发送SIGTERM信号
kill -TERM <pid>
```

#### 查看状态

```bash
# 实时监控输出
# 前台运行时，终端会显示：
# [S0_MONITOR  ] | RMSE: 0.0198 | A: 0.0234 | B: 0.0456

# 查看日志
tail -f chute_monitor.log

# 查看systemd日志
journalctl -u chute-monitor.service -f

# 通过API查询
curl http://localhost:8000/status | python3 -m json.tool
```

### 监控与分析

#### 实时状态查询

```bash
# 查询当前状态
curl http://localhost:8000/status

# 美化输出
curl http://localhost:8000/status | jq '.'

# 持续监控（每2秒刷新）
watch -n 2 'curl -s http://localhost:8000/status | jq "."'
```

#### 异常事件查询

```bash
# 查询最近20条异常事件
curl http://localhost:8000/anomalies

# 查询健康报告
curl http://localhost:8000/report
```

#### 查看异常样本

```bash
# 异常样本保存在 anomaly_samples/ 目录
ls -lh anomaly_samples/

# 查看元数据
cat anomaly_metadata/err_20260115_103045_S2_ACTION_0.1234.json | jq '.'

# 使用Python读取异常样本
python3 << EOF
import numpy as np
import json

# 读取异常数据
data = np.load('anomaly_samples/err_20260115_103045_S2_ACTION_0.1234.npy')
print(f"数据形状: {data.shape}")  # (15, 513)

# 读取元数据
with open('anomaly_metadata/err_20260115_103045_S2_ACTION_0.1234.json') as f:
    metadata = json.load(f)
    print(f"RMSE: {metadata['rmse']}")
    print(f"状态: {metadata['state']}")
    print(f"重试次数: {metadata['retry_count']}")
EOF
```

### 手动控制

#### 手动触发拍打

```bash
# 通过API触发
curl -X POST http://localhost:8000/control/patter

# 响应示例:
# {"status": "success", "msg": "Manual patter triggered"}
```

#### 系统重置（故障排除后）

```bash
# ⚠️ 警告: 仅在人工确认故障已排除后使用
curl -X POST http://localhost:8000/control/reset

# 响应示例:
# {"status": "success", "msg": "System reset completed"}
```

### 数据备份

```bash
# 备份配置文件
cp config_final.py config_final.py.backup

# 备份Golden Buffer
cp golden_samples.npy golden_samples.npy.backup

# 备份模型检查点
tar -czf checkpoints_$(date +%Y%m%d).tar.gz checkpoints/

# 备份异常样本（按日期）
tar -czf anomaly_samples_$(date +%Y%m%d).tar.gz \
    anomaly_samples/ \
    anomaly_metadata/

# 完整备份
tar -czf chute-monitor-backup_$(date +%Y%m%d_%H%M%S).tar.gz \
    config_final.py \
    golden_samples.npy \
    checkpoints/ \
    anomaly_samples/ \
    anomaly_metadata/ \
    chute_monitor.log
```

---

## 🌐 API接口文档

### 基础信息

- **Base URL**: `http://<jetson-ip>:8000`
- **Content-Type**: `application/json`
- **认证**: 无（局域网内使用，如需认证请自行添加）

### 接口列表

#### 1. 实时状态查询

**请求**:
```http
GET /status
```

**响应**:
```json
{
  "state": "S0_MONITOR",
  "rmse": 0.019834,
  "thresh_a": 0.0234,
  "thresh_b": 0.0456,
  "retry_count": 0,
  "is_masking": false,
  "uptime": "1:23:45.678901",
  "timestamp": "2026-01-15T10:30:45.123456"
}
```

**字段说明**:
- `state`: 当前状态机状态（S0/S1/S2/S3/S4）
- `rmse`: 当前重构误差
- `thresh_a`: 预警阈值
- `thresh_b`: 触发阈值
- `retry_count`: 当前重试次数
- `is_masking`: 是否处于噪声屏蔽期
- `uptime`: 系统运行时间
- `timestamp`: 当前时间戳

#### 2. 健康趋势报告

**请求**:
```http
GET /report
```

**响应**:
```json
{
  "trend": "stable",
  "avg_rmse": 0.0198,
  "anomaly_count": 5,
  "last_anomaly": "2026-01-15T09:30:00",
  "recommendation": "系统运行正常，建议继续监控"
}
```

#### 3. 异常事件列表

**请求**:
```http
GET /anomalies?limit=20
```

**参数**:
- `limit` (可选): 返回数量，默认20

**响应**:
```json
[
  {
    "timestamp": "2026-01-15T09:30:00",
    "state": "S2_ACTION",
    "rmse": 0.1234,
    "thresh_a": 0.0234,
    "thresh_b": 0.0456,
    "retry_count": 1,
    "recovery_duration": 15.3,
    "rmse_after_recovery": 0.0198
  },
  ...
]
```

#### 4. 手动触发拍打

**请求**:
```http
POST /control/patter
```

**响应**:
```json
{
  "status": "success",
  "msg": "Manual patter triggered"
}
```

**状态码**:
- `success`: 触发成功
- `busy`: 拍打器正在动作中
- `error`: 拍打器未初始化

#### 5. 系统重置

**请求**:
```http
POST /control/reset
```

**响应**:
```json
{
  "status": "success",
  "msg": "System reset completed"
}
```

**⚠️ 警告**: 此接口仅用于故障排除后的系统恢复，生产环境应配合人工确认使用。

#### 6. 健康检查

**请求**:
```http
GET /health
```

**响应**:
```json
{
  "status": "healthy",
  "components": {
    "source": true,
    "detector": true,
    "fsm": true,
    "patter": true,
    "estop": true
  }
}
```

### 使用示例

#### Python

```python
import requests
import json

BASE_URL = "http://192.168.1.100:8000"

# 查询状态
response = requests.get(f"{BASE_URL}/status")
status = response.json()
print(f"当前状态: {status['state']}")
print(f"RMSE: {status['rmse']:.4f}")

# 手动触发拍打
response = requests.post(f"{BASE_URL}/control/patter")
result = response.json()
print(f"拍打触发: {result['status']}")
```

#### JavaScript

```javascript
const BASE_URL = 'http://192.168.1.100:8000';

// 查询状态
fetch(`${BASE_URL}/status`)
  .then(response => response.json())
  .then(data => {
    console.log(`当前状态: ${data.state}`);
    console.log(`RMSE: ${data.rmse}`);
  });

// 手动触发拍打
fetch(`${BASE_URL}/control/patter`, {
  method: 'POST'
})
  .then(response => response.json())
  .then(data => {
    console.log(`拍打触发: ${data.status}`);
  });
```

#### Shell

```bash
#!/bin/bash

BASE_URL="http://192.168.1.100:8000"

# 查询状态
curl -s "${BASE_URL}/status" | jq '.'

# 监控RMSE（每2秒刷新）
while true; do
    RMSE=$(curl -s "${BASE_URL}/status" | jq -r '.rmse')
    echo "RMSE: $RMSE"
    sleep 2
done
```

---

## 🔧 故障排查

### 常见问题

#### 1. 音频设备未找到

**症状**:
```
✗ 未找到匹配的音频设备 (关键词: 'USB', 需要≥16通道)
RuntimeError: 音频设备未找到
```

**解决方法**:
```bash
# 1. 检查设备连接
lsusb | grep Audio

# 2. 检查设备识别
python3 check_devices.py

# 3. 修改配置
# 编辑 config_final.py
DEVICE_NAME_FRAGMENT = "<实际设备名称关键词>"

# 4. 如果通道数不足，调整配置
ACTIVE_SENSORS = <实际可用通道数>
```

#### 2. CUDA不可用

**症状**:
```
配置为使用CUDA，但当前环境CUDA不可用，将降级到CPU
```

**解决方法**:
```bash
# 1. 检查CUDA安装
nvcc --version
nvidia-smi

# 2. 检查PyTorch CUDA支持
python3 -c "import torch; print(torch.cuda.is_available())"

# 3. 重新安装PyTorch (GPU版本)
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# 4. 如果仍然失败，临时使用CPU
# 编辑 config_final.py
DEVICE = "cpu"
```

#### 3. GPIO权限错误

**症状**:
```
GPIO初始化失败: [Errno 13] Permission denied
```

**解决方法**:
```bash
# 1. 检查用户组
groups $USER

# 2. 添加到gpio组
sudo usermod -aG gpio $USER

# 3. 重新登录
logout
# 或者
su - $USER

# 4. 验证权限
ls -l /sys/class/gpio/export

# 5. 如果仍然失败，使用sudo运行（不推荐生产环境）
sudo python3 main.py
```

#### 4. 拍打器无响应

**症状**:
```
[模拟模式] 拍打器触发 0.5秒
拍打器运行在模拟模式（GPIO不可用或未配置引脚）
```

**解决方法**:
```bash
# 1. 检查配置
# 编辑 config_final.py
PATTER_GPIO_PIN = 4  # 确保设置了正确的引脚号

# 2. 测试GPIO
sudo python3 << EOF
import Jetson.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(4, GPIO.OUT)
GPIO.output(4, GPIO.HIGH)
import time
time.sleep(1)
GPIO.output(4, GPIO.LOW)
GPIO.cleanup()
print("GPIO测试完成")
EOF

# 3. 检查继电器连接
# 使用万用表测试GPIO输出电压
```

#### 5. 系统频繁触发拍打

**症状**:
系统短时间内多次进入S2_ACTION状态

**解决方法**:
```python
# 1. 检查阈值设置是否过于敏感
# 编辑 config_final.py
THRESH_A_MULTIPLIER = 4.0  # 增大阈值
THRESH_B_MULTIPLIER = 8.0

# 2. 增加预警持续时间
T1_PREWARN_TICKS = 15

# 3. 增加恢复等待时间
T2_RECOVERY_WAIT_TICKS = 50

# 4. 检查噪声屏蔽期
STABLE_COLLECT_DELAY = 150  # 增加屏蔽期
```

#### 6. 紧急停机无法重置

**症状**:
```
系统处于S4_ALARM状态，无法恢复
```

**解决方法**:
```bash
# 1. 通过API重置（需要人工确认故障已排除）
curl -X POST http://localhost:8000/control/reset

# 2. 重启系统
sudo systemctl restart chute-monitor

# 3. 如果仍然失败，删除状态文件后重启
rm -f /tmp/chute_monitor_state.lock
sudo systemctl restart chute-monitor
```

### 日志分析

#### 查看关键日志

```bash
# 查看最近的错误
grep "ERROR" chute_monitor.log | tail -20

# 查看状态转换
grep "S0->S1\|S1->S2\|S2->S3\|S3->S0\|S3->S4" chute_monitor.log

# 查看拍打触发记录
grep "触发拍打器" chute_monitor.log

# 查看紧急停机记录
grep "紧急停机" chute_monitor.log

# 实时监控
tail -f chute_monitor.log | grep --color "ERROR\|WARNING\|CRITICAL"
```

#### 日志级别调整

```python
# 编辑 config_final.py

# 生产环境（默认）
LOG_LEVEL = "INFO"

# 调试阶段
LOG_LEVEL = "DEBUG"

# 仅记录错误
LOG_LEVEL = "ERROR"
```

---

## 🛠️ 维护指南

### 定期维护任务

#### 每日检查

```bash
#!/bin/bash
# daily_check.sh

echo "=== 每日健康检查 $(date) ==="

# 1. 检查系统运行状态
systemctl status chute-monitor

# 2. 检查磁盘空间
df -h | grep -E "Filesystem|/home"

# 3. 检查异常样本数量
echo "异常样本数量: $(ls anomaly_samples/ | wc -l)"

# 4. 检查最近的异常事件
curl -s http://localhost:8000/anomalies?limit=5 | jq '.[]|{timestamp, state, rmse}'

# 5. 查看最近的错误日志
tail -100 chute_monitor.log | grep "ERROR\|CRITICAL"
```

#### 每周维护

```bash
#!/bin/bash
# weekly_maintenance.sh

echo "=== 每周维护任务 $(date) ==="

# 1. 备份配置和数据
tar -czf weekly_backup_$(date +%Y%m%d).tar.gz \
    config_final.py \
    golden_samples.npy \
    checkpoints/ \
    anomaly_samples/ \
    anomaly_metadata/

# 2. 清理旧的异常样本（保留30天）
find anomaly_samples/ -type f -mtime +30 -delete
find anomaly_metadata/ -type f -mtime +30 -delete

# 3. 清理旧的检查点（保留最近5个）
cd checkpoints/
ls -t model_*.pth | tail -n +6 | xargs -r rm

# 4. 检查系统性能
nvidia-smi
htop -n 1

# 5. 生成健康报告
curl -s http://localhost:8000/report | jq '.' > weekly_report_$(date +%Y%m%d).json
```

#### 每月维护

```bash
#!/bin/bash
# monthly_maintenance.sh

echo "=== 每月维护任务 $(date) ==="

# 1. 完整系统备份
tar -czf monthly_full_backup_$(date +%Y%m).tar.gz \
    ~/chute-monitor/

# 2. 分析异常趋势
python3 << EOF
import json
import glob
from datetime import datetime, timedelta
from collections import Counter

# 读取最近30天的异常事件
files = glob.glob('anomaly_metadata/*.json')
recent_files = [f for f in files 
                if datetime.fromtimestamp(os.path.getmtime(f)) > 
                   datetime.now() - timedelta(days=30)]

states = []
for f in recent_files:
    with open(f) as fp:
        data = json.load(fp)
        states.append(data['state'])

print("最近30天异常统计:")
for state, count in Counter(states).items():
    print(f"  {state}: {count}次")
EOF

# 3. 更新系统
sudo apt-get update
sudo apt-get upgrade -y

# 4. 检查存储空间，清理旧备份
find ~/backups/ -type f -mtime +90 -delete
```

### 模型更新

#### 重新校准

```bash
# 1. 停止系统
sudo systemctl stop chute-monitor

# 2. 备份当前模型
cp golden_samples.npy golden_samples.npy.old
tar -czf checkpoints_backup.tar.gz checkpoints/

# 3. 删除旧的Golden Buffer
rm golden_samples.npy

# 4. 重新启动（会自动进行冷启动校准）
sudo systemctl start chute-monitor

# 5. 监控校准过程
journalctl -u chute-monitor.service -f
```

#### 手动训练

```python
#!/usr/bin/env python3
# manual_train.py

import numpy as np
import torch
from models import CurvedChuteCAE
import config_final as config

# 加载历史正常样本
normal_samples = []
for i in range(1, 201):  # 假设有200个正常样本
    try:
        sample = np.load(f'normal_samples/sample_{i:03d}.npy')
        normal_samples.append(sample)
    except FileNotFoundError:
        pass

if len(normal_samples) < 50:
    print("正常样本不足，请先收集更多数据")
    exit(1)

# 初始化模型
device = torch.device(config.DEVICE)
model = CurvedChuteCAE().to(device)
optimizer = torch.optim.Adam(model.parameters(), lr=config.LEARNING_RATE)
criterion = torch.nn.MSELoss()

# 转换为tensor
data = torch.tensor(np.array(normal_samples), dtype=torch.float32).to(device)

# 训练
model.train()
for epoch in range(200):
    optimizer.zero_grad()
    output = model(data)
    loss = criterion(output, data)
    loss.backward()
    optimizer.step()
    
    if (epoch + 1) % 20 == 0:
        print(f'Epoch [{epoch+1}/200], Loss: {loss.item():.6f}')

# 保存模型
torch.save({
    'model_state_dict': model.state_dict(),
}, 'checkpoints/manual_trained_model.pth')

print("模型训练完成，保存至: checkpoints/manual_trained_model.pth")
```

### 硬件维护

#### 传感器检查

```bash
# 1. 检查传感器连接（通过音频采集卡）
python3 check_devices.py

# 2. 测试单个传感器
python3 << EOF
import pyaudio
import numpy as np
import config_final as config

pa = pyaudio.PyAudio()
stream = pa.open(
    format=pyaudio.paInt16,
    channels=config.HARDWARE_CHANNELS,
    rate=config.SAMPLE_RATE,
    input=True,
    input_device_index=0,
    frames_per_buffer=config.CHUNK_SIZE
)

# 读取几帧数据
for i in range(5):
    data = stream.read(config.CHUNK_SIZE)
    audio = np.frombuffer(data, dtype=np.int16)
    audio = audio.reshape(-1, config.HARDWARE_CHANNELS).T
    
    print(f"\n采样 {i+1}:")
    for ch in range(config.ACTIVE_SENSORS):
        rms = np.sqrt(np.mean(audio[ch]**2))
        print(f"  传感器 {ch+1:2d}: RMS = {rms:8.2f}", end="")
        if rms < 10:
            print("  ⚠️  信号过弱")
        elif rms > 5000:
            print("  ⚠️  信号过强/饱和")
        else:
            print("  ✓")

stream.stop_stream()
stream.close()
pa.terminate()
EOF
```

#### 拍打器测试

```bash
# 1. 手动测试拍打器
sudo python3 << EOF
from patter_controller import PatterController

with PatterController(gpio_pin=4, relay_type="NO") as patter:
    print("拍打器测试...")
    patter.test_pattern(count=3, interval=2.0)
    print("测试完成")
EOF

# 2. 通过API测试
curl -X POST http://localhost:8000/control/patter
```

---

## ⚡ 性能优化

### GPU优化

#### TensorRT加速（可选）

```python
# install_tensorrt.py
import torch
import torch_tensorrt

# 加载训练好的模型
from models import CurvedChuteCAE
model = CurvedChuteCAE()
model.load_state_dict(torch.load('checkpoints/latest.pth')['model_state_dict'])
model.eval()

# 转换为TensorRT
dummy_input = torch.randn(1, 15, 513).cuda()
trt_model = torch_tensorrt.compile(
    model,
    inputs=[dummy_input],
    enabled_precisions={torch.float16},  # FP16加速
    workspace_size=1 << 30  # 1GB
)

# 保存TensorRT模型
torch.jit.save(trt_model, 'checkpoints/model_trt.ts')
print("TensorRT模型已保存")
```

#### 混合精度优化

系统已默认启用混合精度训练和推理（FP16），无需额外配置。如需调整：

```python
# 编辑 config_final.py
USE_MIXED_PRECISION = True  # 启用（默认）
USE_MIXED_PRECISION = False # 禁用（更高精度，但速度慢）
```

### 内存优化

```python
# 编辑 config_final.py

# 减小缓冲区大小
MAX_GOLDEN_BUFFER_SIZE = 300  # 从500减少
MAX_RECENT_BUFFER_SIZE = 1000  # 从2000减少

# 减小滑动窗口
RMSE_WINDOW_SIZE = 500  # 从1000减少

# 减小训练批次
TRAIN_BATCH_SIZE = 8  # 从16减少
```

### CPU优化

```bash
# 设置CPU性能模式
sudo nvpmodel -m 0  # 最大性能模式

# 设置CPU频率
sudo jetson_clocks  # 锁定最高频率
```

### 网络优化

如需远程访问API，建议使用Nginx反向代理：

```bash
# 安装Nginx
sudo apt-get install nginx

# 配置反向代理
sudo nano /etc/nginx/sites-available/chute-monitor
```

```nginx
server {
    listen 80;
    server_name chute-monitor.local;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
# 启用配置
sudo ln -s /etc/nginx/sites-available/chute-monitor /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 👨‍💻 开发说明

### 项目结构

```
chute-monitor/
├── main.py                      # 主程序入口
├── config_final.py              # 配置文件
├── models.py                    # 深度学习模型定义
├── audio_source.py              # 音频采集模块
├── detector_engine.py           # 异常检测引擎
├── state_machine.py             # 状态机控制
├── patter_controller.py         # 拍打器硬件接口
├── emergency_stop.py            # 紧急停机控制
├── health_analyst_fixed.py      # 健康分析模块
├── utils.py                     # 工具函数
├── check_devices.py             # 设备检测工具
├── requirements.txt             # Python依赖
├── README.md                    # 本文档
├── LICENSE                      # 许可证
│
├── checkpoints/                 # 模型检查点
│   └── model_YYYYMMDD_HHMMSS.pth
│
├── anomaly_samples/             # 异常样本数据
│   └── err_YYYYMMDD_HHMMSS_STATE_RMSE.npy
│
├── anomaly_metadata/            # 异常样本元数据
│   └── err_YYYYMMDD_HHMMSS_STATE_RMSE.json
│
├── backups/                     # 备份目录
└── chute_monitor.log            # 运行日志
```

### 开发环境搭建

```bash
# 克隆代码
git clone https://github.com/yourusername/chute-monitor.git
cd chute-monitor

# 创建开发分支
git checkout -b dev

# 安装开发依赖
pip install -r requirements-dev.txt

# 安装pre-commit钩子
pre-commit install
```

### 代码规范

- **Python风格**: PEP 8
- **文档字符串**: Google风格
- **类型提示**: 推荐使用（Python 3.8+）
- **测试覆盖率**: 目标 >80%

### 添加新功能

#### 示例: 添加温度传感器监测

1. **更新配置文件** (`config_final.py`):

```python
# 温度传感器配置
ENABLE_TEMPERATURE_MONITOR = True
TEMPERATURE_GPIO_PIN = 18
TEMPERATURE_THRESHOLD = 80.0  # °C
```

2. **创建温度监测模块** (`temperature_monitor.py`):

```python
import time
import logging

class TemperatureMonitor:
    def __init__(self, gpio_pin, threshold):
        self.gpio_pin = gpio_pin
        self.threshold = threshold
        self.current_temp = 0.0
        
    def read_temperature(self):
        """读取温度（示例，实际需要根据传感器类型实现）"""
        # TODO: 实现实际的温度读取逻辑
        return self.current_temp
    
    def check_overheat(self):
        """检查是否过热"""
        temp = self.read_temperature()
        if temp > self.threshold:
            logging.warning(f"温度过高: {temp}°C")
            return True
        return False
```

3. **集成到主程序** (`main.py`):

```python
from temperature_monitor import TemperatureMonitor
import config_final as config

# 在main()函数中初始化
if config.ENABLE_TEMPERATURE_MONITOR:
    temp_monitor = TemperatureMonitor(
        gpio_pin=config.TEMPERATURE_GPIO_PIN,
        threshold=config.TEMPERATURE_THRESHOLD
    )

# 在主循环中检查
if config.ENABLE_TEMPERATURE_MONITOR:
    if temp_monitor.check_overheat():
        logging.warning("检测到过热，建议检查设备")
```

4. **添加API接口**:

```python
@app.get("/temperature")
async def get_temperature():
    """获取当前温度"""
    if not config.ENABLE_TEMPERATURE_MONITOR:
        return {"error": "Temperature monitoring not enabled"}
    
    return {
        "temperature": temp_monitor.read_temperature(),
        "threshold": config.TEMPERATURE_THRESHOLD,
        "status": "normal" if temp_monitor.read_temperature() < config.TEMPERATURE_THRESHOLD else "warning"
    }
```

### 测试

```bash
# 运行单元测试
python3 -m pytest tests/

# 运行特定测试
python3 -m pytest tests/test_state_machine.py

# 查看覆盖率
python3 -m pytest --cov=. tests/
```

### 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

---

## 📜 版本历史

### v2.3 (2026-01-15) - 当前版本
- 🔧 修复紧急停机逻辑，防止重复触发
- ✨ 添加噪声屏蔽期机制，提高系统稳定性
- 📊 集成健康分析模块（HealthAnalyst）
- 🌐 完整的RESTful API接口
- 📝 完善日志记录和异常样本归档

### v2.2 (2026-01-10)
- 🔧 修复卷积自编码器维度问题（513→513）
- ⚡ 更新PyTorch混合精度API（torch.amp）
- 🎵 添加设备检测工具（check_devices.py）
- 📦 Golden Buffer持久化存储
- 🛡️ 改进异常处理和错误恢复

### v2.1 (2026-01-05)
- ✨ 支持异步非阻塞拍打器执行
- 🎛️ 可配置继电器类型（NO/NC）
- 🚨 完善紧急停机控制器
- 📈 动态阈值自适应调整
- 🐛 修复内存泄漏问题

### v2.0 (2025-12-20)
- 🏗️ 完全重构代码架构
- 🧠 引入卷积自编码器（CAE）模型
- 🤖 五状态机控制逻辑
- ⚙️ 增量学习与样本管理
- 🔌 GPIO硬件接口支持

### v1.0 (2025-11-01) - 初始版本
- 🎯 基础异常检测功能
- 📊 简单阈值判断
- 📝 日志记录

---

## ❓ 常见问题

### Q1: 系统支持哪些硬件平台？

**A**: 系统主要针对NVIDIA Jetson系列开发，特别是Jetson Orin NX。理论上也可以运行在：
- Jetson Xavier NX
- Jetson AGX Orin
- 任何支持CUDA的Linux系统（需要修改GPIO部分代码）

### Q2: 可以使用少于15个传感器吗？

**A**: 可以。修改配置文件：

```python
ACTIVE_SENSORS = 8  # 实际使用的传感器数量
HARDWARE_CHANNELS = 8  # 对应的音频采集卡通道数
```

注意：传感器数量会影响检测精度，建议至少使用10个传感器。

### Q3: 系统的延迟是多少？

**A**: 
- 采集延迟: ~23ms（1024采样点 / 44.1kHz）
- 推理延迟: <5ms（GPU加速）
- 总延迟: <50ms（端到端）

### Q4: 如何调整灵敏度？

**A**: 主要通过调整阈值倍数：

- **提高灵敏度**（更容易触发预警）：
  ```python
  THRESH_A_MULTIPLIER = 2.5  # 降低预警阈值
  THRESH_B_MULTIPLIER = 5.0  # 降低触发阈值
  ```

- **降低灵敏度**（减少误报）：
  ```python
  THRESH_A_MULTIPLIER = 4.0  # 提高预警阈值
  THRESH_B_MULTIPLIER = 8.0  # 提高触发阈值
  ```

### Q5: 系统可以在无GPU环境下运行吗？

**A**: 可以，但性能会降低。修改配置：

```python
DEVICE = "cpu"
USE_MIXED_PRECISION = False
```

CPU模式下延迟约为100-200ms。

### Q6: 如何备份和恢复系统？

**A**: 

**备份**:
```bash
# 完整备份
tar -czf chute-monitor-backup.tar.gz \
    config_final.py \
    golden_samples.npy \
    checkpoints/ \
    anomaly_samples/ \
    anomaly_metadata/
```

**恢复**:
```bash
# 解压备份
tar -xzf chute-monitor-backup.tar.gz

# 重启系统
sudo systemctl restart chute-monitor
```

### Q7: 系统的功耗是多少？

**A**: 
- Jetson Orin NX: 10-25W（可配置功率模式）
- 音频采集卡: 5W（USB供电）
- 拍打器: 20-100W（工作时）
- 总计: 约35-130W

### Q8: 可以同时监测多个落煤管吗？

**A**: 当前版本不直接支持，但可以通过以下方式实现：

1. **方案1**: 部署多套系统，每套监测一个落煤管
2. **方案2**: 扩展代码，使用多个音频采集卡和多组传感器
3. **方案3**: 使用时分复用（轮询检测）

### Q9: 如何联系技术支持？

**A**: 
- 📧 Email: support@example.com
- 💬 Issue: [GitHub Issues](https://github.com/yourusername/chute-monitor/issues)
- 📞 电话: +86-XXX-XXXX-XXXX（工作日 9:00-18:00）

### Q10: 系统有商业许可证吗？

**A**: 当前版本采用MIT许可证，可免费用于商业用途。如需企业级支持或定制开发，请联系我们。

---

## 📄 许可证



---

## 🙏 致谢

- 
- 
- 

---

## 📞 联系方式

- **项目主页**: 
- **文档**: 
- **Email**: 
- **微信**: 

---

**最后更新**: 2026-01-15
**文档版本**: v2.3.0
**维护者**: 
