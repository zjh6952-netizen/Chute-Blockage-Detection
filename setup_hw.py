cat << 'EOF' > setup_hw.py
import re
import os
import subprocess

def get_input(prompt, default):
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default

def update_config(file_path, settings):
    if not os.path.exists(file_path):
        print(f"错误: 找不到文件 {file_path}")
        return

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    for key, value in settings.items():
        # 正则表达式匹配 key = value 这种格式，忽略空格和注释
        # 兼容 None, 数字, 和字符串
        pattern = rf"({key}\s*=\s*)([^#\n]+)"
        
        # 格式化新值
        if value is None:
            new_val_str = "None"
        elif isinstance(value, str) and not value.replace('.','',1).isdigit() and value not in ["True", "False", "None"]:
            new_val_str = f"'{value}'"
        else:
            new_val_str = str(value)

        content = re.sub(pattern, rf"\1{new_val_str}", content)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print("\n✅ 配置文件 config_final.py 已自动更新！")

def main():
    print("="*50)
    print("      曲线溜槽监测系统 - 硬件部署助手")
    print("="*50)

    # 1. 自动运行设备检测
    print("\n[步骤 1] 正在检测音频设备...")
    try:
        # 运行 check_devices.py 并获取输出
        subprocess.run(["python3", "check_devices.py"], check=True)
    except:
        print("警告: 无法运行 check_devices.py，请手动确认索引。")

    print("\n" + "-"*50)
    print("[步骤 2] 请输入现场硬件参数 (直接按回车则保持默认)")
    
    # 交互提问
    dev_idx = get_input("音频设备索引 (DEVICE_INDEX)", "None")
    patter_pin = get_input("拍打器 GPIO 引脚 (PATTER_GPIO_PIN)", "4")
    stop_pin = get_input("急停 GPIO 引脚 (EMERGENCY_STOP_GPIO_PIN)", "17")
    log_level = get_input("日志级别 (LOG_LEVEL: INFO/DEBUG)", "INFO")

    # 准备更新字典
    settings = {
        "DEVICE_INDEX": dev_idx,
        "PATTER_GPIO_PIN": patter_pin,
        "EMERGENCY_STOP_GPIO_PIN": stop_pin,
        "LOG_LEVEL": log_level
    }

    # 执行更新
    update_config("config_final.py", settings)

    print("\n" + "="*50)
    print("配置完成！现在你可以运行以下命令启动系统：")
    print("python3 main.py")
    print("="*50)

if __name__ == "__main__":
    main()
EOF