"""
紧急停机控制器模块
用于在S4紧急状态下触发物理停机信号
版本: v2.1
"""

import time
import logging
import threading
from typing import Optional

# 尝试导入Jetson GPIO库
try:
    import Jetson.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("Jetson.GPIO未安装，紧急停机将以模拟模式运行")

import config_final as config


class EmergencyStopController:
    """紧急停机控制器"""
    
    def __init__(self, gpio_pin: Optional[int] = None, signal_type: str = "HIGH"):
        """
        初始化紧急停机控制器
        
        Args:
            gpio_pin: GPIO引脚号（BCM编号），None则为模拟模式
            signal_type: 触发信号类型，"HIGH" 或 "LOW"
        """
        self.gpio_pin = gpio_pin or config.EMERGENCY_STOP_GPIO_PIN
        self.signal_type = signal_type.upper()
        self.enabled = config.ENABLE_EMERGENCY_STOP
        self.hold_time = config.EMERGENCY_STOP_HOLD_TIME
        self.is_initialized = False
        self.is_stopped = False
        self.simulation_mode = not GPIO_AVAILABLE or self.gpio_pin is None
        
        # 线程安全
        self._lock = threading.Lock()
        self._stop_thread = None
        
        if not self.enabled:
            logging.info("紧急停机功能已禁用（config.ENABLE_EMERGENCY_STOP = False）")
            return
        
        if self.simulation_mode:
            logging.warning("紧急停机运行在模拟模式（GPIO不可用或未配置引脚）")
        else:
            self._initialize_gpio()
    
    def _initialize_gpio(self):
        """初始化GPIO"""
        try:
            # 设置GPIO模式为BCM编号
            GPIO.setmode(GPIO.BCM)
            
            # 配置引脚为输出，初始状态为非触发
            if self.signal_type == "HIGH":
                GPIO.setup(self.gpio_pin, GPIO.OUT, initial=GPIO.LOW)
            else:
                GPIO.setup(self.gpio_pin, GPIO.OUT, initial=GPIO.HIGH)
            
            self.is_initialized = True
            logging.info(f"紧急停机GPIO初始化成功 (引脚: {self.gpio_pin}, 信号类型: {self.signal_type})")
            
        except Exception as e:
            logging.error(f"紧急停机GPIO初始化失败: {e}")
            self.simulation_mode = True
    
    def trigger(self, async_mode: bool = False) -> bool:
        """
        触发紧急停机
        
        Args:
            async_mode: 是否异步执行（不阻塞）
            
        Returns:
            bool: 是否成功触发
        """
        if not self.enabled:
            logging.debug("紧急停机已禁用，跳过触发")
            return False
        
        with self._lock:
            if self.is_stopped:
                logging.warning("紧急停机已经触发过，不重复触发")
                return False
        
        if async_mode:
            self._stop_thread = threading.Thread(
                target=self._do_trigger,
                name="EmergencyStop",
                daemon=True
            )
            self._stop_thread.start()
            return True
        else:
            return self._do_trigger()
    
    def _do_trigger(self) -> bool:
        """执行紧急停机"""
        if self.simulation_mode:
            return self._simulate_trigger()
        else:
            return self._gpio_trigger()
    
    def _simulate_trigger(self) -> bool:
        """模拟紧急停机触发（用于测试）"""
        logging.critical("=" * 70)
        logging.critical("[模拟模式] ⚠️  紧急停机信号已触发 ⚠️")
        logging.critical("=" * 70)
        logging.critical("生产环境中，此时应该:")
        logging.critical("  1. 皮带运输机立即停止")
        logging.critical("  2. 声光报警器启动")
        logging.critical("  3. 通知现场人员检查")
        logging.critical(f"  4. 停机信号保持 {self.hold_time:.1f} 秒")
        logging.critical("=" * 70)
        
        with self._lock:
            self.is_stopped = True
        
        time.sleep(self.hold_time)
        
        logging.critical("[模拟模式] 紧急停机信号结束")
        return True
    
    def _gpio_trigger(self) -> bool:
        """通过GPIO触发紧急停机"""
        try:
            logging.critical("=" * 70)
            logging.critical(f"⚠️  触发紧急停机 (GPIO {self.gpio_pin}) ⚠️")
            logging.critical("=" * 70)
            
            # 输出触发信号
            if self.signal_type == "HIGH":
                GPIO.output(self.gpio_pin, GPIO.HIGH)
                logging.critical("紧急停机信号: HIGH (触发)")
            else:
                GPIO.output(self.gpio_pin, GPIO.LOW)
                logging.critical("紧急停机信号: LOW (触发)")
            
            with self._lock:
                self.is_stopped = True
            
            # 保持信号
            logging.critical(f"保持停机信号 {self.hold_time:.1f} 秒...")
            time.sleep(self.hold_time)
            
            logging.critical("紧急停机信号已发送完成")
            logging.critical("=" * 70)
            
            return True
            
        except Exception as e:
            logging.error(f"紧急停机触发失败: {e}")
            return False
    
    def reset(self) -> bool:
        """
        重置紧急停机状态（恢复运行）
        注意：仅用于测试，生产环境需要人工确认后才能重置
        
        Returns:
            bool: 是否成功重置
        """
        with self._lock:
            if not self.is_stopped:
                logging.info("紧急停机未触发，无需重置")
                return True
        
        if self.simulation_mode:
            logging.warning("[模拟模式] 重置紧急停机状态")
            with self._lock:
                self.is_stopped = False
            return True
        
        try:
            # 恢复非触发状态
            if self.signal_type == "HIGH":
                GPIO.output(self.gpio_pin, GPIO.LOW)
            else:
                GPIO.output(self.gpio_pin, GPIO.HIGH)
            
            with self._lock:
                self.is_stopped = False
            logging.info("紧急停机状态已重置")
            return True
            
        except Exception as e:
            logging.error(f"重置紧急停机失败: {e}")
            return False
    
    def cleanup(self):
        """清理GPIO资源"""
        # 等待停机线程完成
        if self._stop_thread and self._stop_thread.is_alive():
            self._stop_thread.join(timeout=self.hold_time + 2)
        
        if self.is_initialized and not self.simulation_mode:
            try:
                # 确保恢复非触发状态
                if self.signal_type == "HIGH":
                    GPIO.output(self.gpio_pin, GPIO.LOW)
                else:
                    GPIO.output(self.gpio_pin, GPIO.HIGH)
                
                GPIO.cleanup(self.gpio_pin)
                logging.info("紧急停机GPIO资源已释放")
                
            except Exception as e:
                logging.error(f"紧急停机GPIO清理失败: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.cleanup()
    
    def get_status(self) -> dict:
        """获取紧急停机状态信息"""
        with self._lock:
            is_stopped = self.is_stopped
        
        return {
            'enabled': self.enabled,
            'simulation_mode': self.simulation_mode,
            'gpio_pin': self.gpio_pin,
            'signal_type': self.signal_type,
            'hold_time': self.hold_time,
            'is_initialized': self.is_initialized,
            'is_stopped': is_stopped
        }


# ============================================================================
# 测试代码
# ============================================================================
if __name__ == "__main__":
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s'
    )
    
    print("="*60)
    print("紧急停机控制器测试 (v2.1)")
    print("="*60)
    
    # 创建控制器
    with EmergencyStopController() as emergency_stop:
        # 显示状态
        status = emergency_stop.get_status()
        print(f"\n紧急停机状态:")
        for key, value in status.items():
            print(f"  {key:20}: {value}")
        
        # 测试触发
        if status['enabled']:
            print(f"\n⚠️  警告：这将触发紧急停机测试！")
            response = input("是否继续? 生产环境请输入 'YES' 确认: ")
            
            if response == 'YES':
                print("\n触发紧急停机...")
                emergency_stop.trigger()
                
                print("\n测试重置功能...")
                time.sleep(2)
                emergency_stop.reset()
            else:
                print("测试已取消")
        else:
            print("\n紧急停机已禁用，跳过测试")
    
    print("\n测试完成")
