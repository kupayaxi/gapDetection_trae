import os
import sys
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 导入信号处理器
try:
    from src.signal_handler.signal_handler import signal_handler
except ImportError:
    print("无法导入signal_handler，请确保路径正确")
    sys.exit(1)

print("测试报警功能...")
print("3秒后将触发模拟报警...")
time.sleep(3)

# 创建报警信息
alarm_info = {
    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    "position": "屏蔽门1号间隙",
    "object_type": "不明物体",
    "detail": "模拟测试报警，确认弹窗显示",
}

# 触发报警
try:
    signal_handler.trigger_alarm(alarm_info)
    print("报警已触发，请检查是否显示报警弹窗")
except Exception as e:
    print(f"触发报警失败: {e}")

print("测试完成")
