import threading
from enum import Enum

class SystemState(Enum):
    IDLE = 0          # 空闲状态
    CLOSING = 1       # 关门中
    CLOSED = 2        # 已关闭
    ALARM = 3         # 报警状态

class SignalHandler:
    def __init__(self):
        self._current_state = SystemState.IDLE
        self._state_lock = threading.RLock()
        self._state_change_callbacks = []
        self._alarm_callbacks = []
    
    def register_state_change_callback(self, callback):
        if callback not in self._state_change_callbacks:
            self._state_change_callbacks.append(callback)
    
    def unregister_state_change_callback(self, callback):
        if callback in self._state_change_callbacks:
            self._state_change_callbacks.remove(callback)
    
    def register_alarm_callback(self, callback):
        if callback not in self._alarm_callbacks:
            self._alarm_callbacks.append(callback)
    
    def unregister_alarm_callback(self, callback):
        if callback in self._alarm_callbacks:
            self._alarm_callbacks.remove(callback)
    
    def get_current_state(self):
        with self._state_lock:
            return self._current_state
    
    def set_state(self, new_state):
        with self._state_lock:
            if new_state != self._current_state:
                old_state = self._current_state
                self._current_state = new_state
                
                for callback in self._state_change_callbacks:
                    try:
                        callback(old_state, new_state)
                    except Exception as e:
                        print(f"状态变化回调执行失败: {e}")
    
    def trigger_close_command(self):
        self.set_state(SystemState.CLOSING)
    
    def trigger_closed_command(self):
        if self.get_current_state() == SystemState.CLOSING:
            self.set_state(SystemState.CLOSED)
    
    def trigger_alarm(self, alarm_info):
        self.set_state(SystemState.ALARM)
        
        for callback in self._alarm_callbacks:
            try:
                callback(alarm_info)
            except Exception as e:
                print(f"报警回调执行失败: {e}")
    
    def reset_to_idle(self):
        self.set_state(SystemState.IDLE)
    
    def simulate_signal(self, signal_type):
        if signal_type == 'close_command':
            self.trigger_close_command()
            return True
        elif signal_type == 'closed_command':
            self.trigger_closed_command()
            return True
        else:
            print(f"未知信号类型: {signal_type}")
            return False

signal_handler = SignalHandler()