"""
拍打器硬件接口模块
用于控制Jetson GPIO引脚，驱动继电器触发拍打器动作
版本: v2.1 - 支持异步非阻塞执行
"""

import time
import logging
import threading
from typing import Optional, Callable

# 尝试导入Jetson GPIO库
try:
    import Jetson.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logging.warning("Jetson.GPIO未安装，拍打器将以模拟模式运行")

import config_final as config


class PatterController:
    """拍打器控制器 - 支持同步和异步执行"""
    
    def __init__(self, gpio_pin: Optional[int] = None, relay_type: str = "NO"):
        """
        初始化拍打器控制器
        
        Args:
            gpio_pin: GPIO引脚号（BCM编号），None则为模拟模式
            relay_type: 继电器类型，"NO"(常开) 或 "NC"(常闭)
        """
        self.gpio_pin = gpio_pin or config.PATTER_GPIO_PIN
        self.relay_type = relay_type.upper()
        self.enabled = config.PATTER_ENABLED
        self.duration = config.PATTER_DURATION
        self.async_mode = getattr(config, 'PATTER_ASYNC', True)  # 默认异步
        self.is_initialized = False
        self.simulation_mode = not GPIO_AVAILABLE or self.gpio_pin is None
        
        # 异步执行相关
        self._action_thread = None
        self._is_acting = False
        self._action_lock = threading.Lock()
        self._action_start_time = None
        self._action_complete_callback = None
        
        if not self.enabled:
            logging.info("拍打器功能已禁用（config.PATTER_ENABLED = False）")
            return
        
        if self.simulation_mode:
            logging.warning("拍打器运行在模拟模式（GPIO不可用或未配置引脚）")
        else:
            self._initialize_gpio()
    
    def _initialize_gpio(self):
        """初始化GPIO"""
        try:
            # 设置GPIO模式为BCM编号
            GPIO.setmode(GPIO.BCM)
            
            # 配置引脚为输出
            GPIO.setup(self.gpio_pin, GPIO.OUT, initial=GPIO.LOW)
            
            # 根据继电器类型设置初始状态
            if self.relay_type == "NC":
                GPIO.output(self.gpio_pin, GPIO.HIGH)
            else:
                GPIO.output(self.gpio_pin, GPIO.LOW)
            
            self.is_initialized = True
            logging.info(f"拍打器GPIO初始化成功 (引脚: {self.gpio_pin}, 类型: {self.relay_type})")
            
        except Exception as e:
            logging.error(f"GPIO初始化失败: {e}")
            self.simulation_mode = True
    
    def is_acting(self) -> bool:
        """检查拍打器是否正在动作中"""
        with self._action_lock:
            return self._is_acting
    
    def get_action_elapsed_time(self) -> Optional[float]:
        """获取当前动作已执行的时间（秒）"""
        with self._action_lock:
            if self._is_acting and self._action_start_time:
                return time.time() - self._action_start_time
            return None
    
    def trigger(self, duration: Optional[float] = None, 
                callback: Optional[Callable[[bool], None]] = None,
                force_sync: bool = False) -> bool:
        """
        触发拍打器动作
        
        Args:
            duration: 拍打持续时间（秒），None则使用默认值
            callback: 动作完成后的回调函数，参数为是否成功
            force_sync: 强制同步执行（阻塞）
            
        Returns:
            bool: 是否成功触发（异步模式下表示是否成功启动）
        """
        if not self.enabled:
            logging.debug("拍打器已禁用，跳过触发")
            return False
        
        # 检查是否正在动作中
        if self.is_acting():
            logging.warning("拍打器正在动作中，跳过本次触发")
            return False
        
        duration = duration or self.duration
        self._action_complete_callback = callback
        
        # 决定同步还是异步执行
        if self.async_mode and not force_sync:
            return self._trigger_async(duration)
        else:
            return self._trigger_sync(duration)
    
    def _trigger_sync(self, duration: float) -> bool:
        """同步执行拍打（阻塞）"""
        if self.simulation_mode:
            return self._simulate_trigger(duration)
        else:
            return self._gpio_trigger(duration)
    
    def _trigger_async(self, duration: float) -> bool:
        """异步执行拍打（非阻塞）"""
        with self._action_lock:
            self._is_acting = True
            self._action_start_time = time.time()
        
        def async_action():
            try:
                if self.simulation_mode:
                    success = self._simulate_trigger(duration)
                else:
                    success = self._gpio_trigger(duration)
                
                # 调用回调
                if self._action_complete_callback:
                    try:
                        self._action_complete_callback(success)
                    except Exception as e:
                        logging.error(f"拍打完成回调执行失败: {e}")
                        
            finally:
                with self._action_lock:
                    self._is_acting = False
                    self._action_start_time = None
        
        self._action_thread = threading.Thread(
            target=async_action, 
            name="PatterAction",
            daemon=True
        )
        self._action_thread.start()
        
        logging.info(f"拍打器异步触发已启动 ({duration:.1f}秒)")
        return True
    
    def _simulate_trigger(self, duration: float) -> bool:
        """模拟拍打器触发（用于测试）"""
        logging.warning(f"[模拟模式] 拍打器触发 {duration:.1f}秒")
        time.sleep(duration)
        logging.warning("[模拟模式] 拍打器动作完成")
        return True
    
    def _gpio_trigger(self, duration: float) -> bool:
        """通过GPIO触发拍打器"""
        try:
            logging.info(f"触发拍打器 (GPIO {self.gpio_pin}, {duration:.1f}秒)")
            
            # 激活继电器
            if self.relay_type == "NC":
                GPIO.output(self.gpio_pin, GPIO.LOW)
            else:
                GPIO.output(self.gpio_pin, GPIO.HIGH)
            
            # 保持激活状态
            time.sleep(duration)
            
            # 断开继电器
            if self.relay_type == "NC":
                GPIO.output(self.gpio_pin, GPIO.HIGH)
            else:
                GPIO.output(self.gpio_pin, GPIO.LOW)
            
            logging.info("拍打器动作完成")
            return True
            
        except Exception as e:
            logging.error(f"拍打器触发失败: {e}")
            return False
    
    def wait_for_completion(self, timeout: float = 10.0) -> bool:
        """
        等待当前动作完成
        
        Args:
            timeout: 最大等待时间（秒）
            
        Returns:
            bool: 是否在超时前完成
        """
        if self._action_thread and self._action_thread.is_alive():
            self._action_thread.join(timeout=timeout)
            return not self._action_thread.is_alive()
        return True
    
    def test_pattern(self, count: int = 3, interval: float = 1.0):
        """
        测试拍打器（连续触发多次）
        
        Args:
            count: 触发次数
            interval: 每次触发间隔（秒）
        """
        logging.info(f"开始拍打器测试 (触发{count}次，间隔{interval}秒)")
        
        for i in range(count):
            logging.info(f"测试触发 {i+1}/{count}")
            self.trigger(duration=0.5, force_sync=True)  # 测试时强制同步
            
            if i < count - 1:
                time.sleep(interval)
        
        logging.info("拍打器测试完成")
    
    def cleanup(self):
        """清理GPIO资源"""
        # 等待异步动作完成
        if self._action_thread and self._action_thread.is_alive():
            logging.info("等待拍打器动作完成...")
            self._action_thread.join(timeout=5.0)
        
        if self.is_initialized and not self.simulation_mode:
            try:
                # 确保继电器断开
                if self.relay_type == "NC":
                    GPIO.output(self.gpio_pin, GPIO.HIGH)
                else:
                    GPIO.output(self.gpio_pin, GPIO.LOW)
                
                GPIO.cleanup(self.gpio_pin)
                logging.info("GPIO资源已释放")
                
            except Exception as e:
                logging.error(f"GPIO清理失败: {e}")
    
    def __enter__(self):
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器退出"""
        self.cleanup()
    
    def get_status(self) -> dict:
        """获取拍打器状态信息"""
        return {
            'enabled': self.enabled,
            'simulation_mode': self.simulation_mode,
            'gpio_pin': self.gpio_pin,
            'relay_type': self.relay_type,
            'duration': self.duration,
            'async_mode': self.async_mode,
            'is_initialized': self.is_initialized,
            'is_acting': self.is_acting()
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
    print("拍打器硬件接口测试 (v2.1 - 异步支持)")
    print("="*60)
    
    # 创建拍打器控制器
    with PatterController() as patter:
        # 显示状态
        status = patter.get_status()
        print(f"\n拍打器状态:")
        for key, value in status.items():
            print(f"  {key:20}: {value}")
        
        # 测试触发
        if status['enabled']:
            print(f"\n开始测试触发...")
            response = input("是否继续测试拍打器? (y/n): ")
            
            if response.lower() == 'y':
                # 测试异步触发
                print("\n测试异步触发:")
                
                def on_complete(success):
                    print(f"  回调: 拍打完成, 成功={success}")
                
                patter.trigger(duration=1.0, callback=on_complete)
                
                # 主线程可以继续执行其他操作
                for i in range(5):
                    elapsed = patter.get_action_elapsed_time()
                    if elapsed:
                        print(f"  主线程: 拍打进行中... {elapsed:.1f}秒")
                    time.sleep(0.3)
                
                # 等待完成
                patter.wait_for_completion()
                print("  异步触发测试完成")
                
                # 测试同步触发
                print("\n测试同步触发:")
                patter.test_pattern(count=2, interval=1.0)
            else:
                print("测试已取消")
        else:
            print("\n拍打器已禁用，跳过测试")
    
    print("\n测试完成")
