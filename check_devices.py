#!/usr/bin/env python3
"""
音频设备检测工具
用于列出所有可用的音频输入设备及其详细信息
"""

import pyaudio
import sys

def list_audio_devices():
    """列出所有音频设备及详细信息"""
    pa = pyaudio.PyAudio()
    
    print("\n" + "="*80)
    print("                    音频设备检测工具")
    print("="*80)
    print()
    
    device_count = pa.get_device_count()
    print(f"检测到 {device_count} 个音频设备:\n")
    
    input_devices = []
    
    for i in range(device_count):
        try:
            info = pa.get_device_info_by_index(i)
            
            # 只显示输入设备
            if info['maxInputChannels'] > 0:
                input_devices.append((i, info))
                
                print(f"{'='*80}")
                print(f"设备索引: {i}")
                print(f"设备名称: {info['name']}")
                print(f"最大输入通道: {info['maxInputChannels']}")
                print(f"最大输出通道: {info['maxOutputChannels']}")
                print(f"默认采样率: {int(info['defaultSampleRate'])} Hz")
                
                # 检查是否为默认设备
                try:
                    default_input = pa.get_default_input_device_info()
                    if default_input['index'] == i:
                        print(f"默认输入设备: ✓ 是")
                except:
                    pass
                
                print()
        
        except Exception as e:
            print(f"设备 {i}: 无法获取信息 ({e})")
    
    pa.terminate()
    
    print("="*80)
    print(f"\n找到 {len(input_devices)} 个输入设备")
    
    if not input_devices:
        print("\n⚠️  警告: 未检测到任何输入设备！")
        print("请检查:")
        print("  1. 麦克风/音频设备是否正确连接")
        print("  2. 设备驱动是否已安装")
        print("  3. 系统是否授予了麦克风访问权限")
        return
    
    print("\n建议配置:")
    print("-" * 80)
    
    # 推荐最合适的设备
    recommended = None
    for idx, info in input_devices:
        # 优先推荐通道数较多的设备
        if info['maxInputChannels'] >= 15:
            recommended = (idx, info)
            break
        elif recommended is None or info['maxInputChannels'] > recommended[1]['maxInputChannels']:
            recommended = (idx, info)
    
    if recommended:
        idx, info = recommended
        print(f"推荐设备索引: {idx}")
        print(f"推荐设备名称: {info['name']}")
        print(f"支持通道数:   {info['maxInputChannels']}")
        
        if info['maxInputChannels'] < 15:
            print(f"\n⚠️  注意: 该设备只支持 {info['maxInputChannels']} 个通道")
            print(f"   您的配置需要 15 个通道")
            print(f"\n建议方案:")
            if info['maxInputChannels'] >= 16:
                print(f"  1. 在 config.py 中设置 CHANNELS = {info['maxInputChannels']}")
                print(f"  2. 在代码中切片取前15个通道: data = data[:15, :]")
            else:
                print(f"  1. 更换支持更多通道的音频接口")
                print(f"  2. 或修改系统设计，使用 {info['maxInputChannels']} 个通道")
        else:
            print(f"\n✓ 该设备支持 15 通道配置")
        
        print(f"\n在 config.py 中设置:")
        print(f"  DEVICE_INDEX = {idx}")
        if info['maxInputChannels'] >= 16 and info['maxInputChannels'] != 15:
            print(f"  CHANNELS = {info['maxInputChannels']}  # 然后在代码中切片取前15个")
    
    print("="*80)
    print()

def test_device(device_index, channels=2):
    """测试指定设备是否可用"""
    print(f"\n测试设备 {device_index} (通道数: {channels})...")
    
    pa = pyaudio.PyAudio()
    
    try:
        # 尝试打开设备
        stream = pa.open(
            format=pyaudio.paInt16,
            channels=channels,
            rate=44100,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=1024
        )
        
        # 尝试读取一帧数据
        data = stream.read(1024, exception_on_overflow=False)
        
        stream.stop_stream()
        stream.close()
        
        print(f"✓ 设备 {device_index} 测试成功！")
        print(f"  可以正常读取 {channels} 通道的音频数据")
        return True
        
    except Exception as e:
        print(f"✗ 设备 {device_index} 测试失败:")
        print(f"  错误: {e}")
        return False
    
    finally:
        pa.terminate()

def main():
    """主函数"""
    print("\n曲面溜槽健康监测系统 - 设备检测工具 v1.0")
    
    # 列出所有设备
    list_audio_devices()
    
    # 交互式测试
    while True:
        try:
            response = input("\n是否要测试特定设备? (输入设备索引，或按 Enter 退出): ").strip()
            
            if not response:
                break
            
            device_idx = int(response)
            
            channels_input = input(f"输入通道数 (默认 2): ").strip()
            channels = int(channels_input) if channels_input else 2
            
            test_device(device_idx, channels)
            
        except ValueError:
            print("无效输入，请输入数字")
        except KeyboardInterrupt:
            print("\n")
            break
        except Exception as e:
            print(f"错误: {e}")
    
    print("检测完成。")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n检测已取消。")
        sys.exit(0)
    except Exception as e:
        print(f"\n发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
