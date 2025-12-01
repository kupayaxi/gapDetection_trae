import threading
from enum import Enum

# 导入信号处理器


class SystemState(Enum):
    IDLE = 0  # 空闲状态
    CLOSING = 1  # 关门中
    CLOSED = 2  # 已关闭
    ALARM = 3  # 报警状态


class SignalHandler:
    def __init__(self):
        self._current_state = SystemState.IDLE
        self._state_lock = threading.RLock()
        self._state_change_callbacks = []
        self._alarm_callbacks = []
        self._stop_timer = None
        self._detection_active = False
        # 延迟导入避免循环导入
        self._detection_manager = None
        self._log_manager = None

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

    def _get_detection_manager(self):
        """延迟获取检测管理器."""
        if self._detection_manager is None:
            try:
                from object_detection.detection_manager import detection_manager

                self._detection_manager = detection_manager
            except ImportError:
                # 如果导入失败，尝试不同的路径
                try:
                    # 尝试直接导入（当从src目录运行时）
                    from src.object_detection.detection_manager import detection_manager

                    self._detection_manager = detection_manager
                except ImportError:
                    print("警告：无法导入detection_manager，检测功能将不可用")
        return self._detection_manager

    def _get_log_manager(self):
        """延迟获取日志管理器."""
        if self._log_manager is None:
            try:
                from logger.log_manager import log_manager

                self._log_manager = log_manager
            except ImportError:
                # 如果导入失败，尝试不同的路径
                try:
                    from src.logger.log_manager import log_manager

                    self._log_manager = log_manager
                except ImportError:
                    print("警告：无法导入log_manager，日志功能将不可用")
        return self._log_manager

    def set_state(self, new_state):
        with self._state_lock:
            if new_state != self._current_state:
                old_state = self._current_state
                self._current_state = new_state

                # 处理状态转换逻辑
                self._handle_state_transition(old_state, new_state)

                for callback in self._state_change_callbacks:
                    try:
                        callback(old_state, new_state)
                    except Exception as e:
                        print(f"状态变化回调执行失败: {e}")
                        # 使用延迟导入的日志管理器
                        log_mgr = self._get_log_manager()
                        if log_mgr:
                            log_mgr.log_error(f"状态变化回调执行失败: {e}")

    def trigger_close_command(self):
        self.set_state(SystemState.CLOSING)

    def trigger_closed_command(self):
        """收到已关闭命令，启动2秒延迟停止检测."""
        if self.get_current_state() == SystemState.CLOSING:
            self.set_state(SystemState.CLOSED)
            # 启动定时器，2秒后停止检测
            self._start_stop_detection_timer()
            self._log("信号处理", "收到已关闭命令，启动2秒延迟停止检测")

    def trigger_alarm(self, alarm_info):
        self.set_state(SystemState.ALARM)

        for callback in self._alarm_callbacks:
            try:
                callback(alarm_info)
            except Exception as e:
                print(f"报警回调执行失败: {e}")

    def _handle_state_transition(self, old_state, new_state):
        """处理状态转换时的逻辑."""
        # 从IDLE到CLOSING：开始检测
        if old_state == SystemState.IDLE and new_state == SystemState.CLOSING:
            self._start_detection()
        # 从任何状态到IDLE：停止检测并取消定时器
        elif new_state == SystemState.IDLE:
            self._stop_detection()
            self._cancel_stop_timer()
        # 从ALARM到其他状态：重置报警状态
        elif old_state == SystemState.ALARM and new_state != SystemState.ALARM:
            self._log("系统重置", "报警状态已重置")

    def _log(self, event, message):
        """记录系统事件."""
        log_mgr = self._get_log_manager()
        if log_mgr and hasattr(log_mgr, "log_system_event"):
            log_mgr.log_system_event(event, message)
        else:
            print(f"[{event}] {message}")

    def _log_error(self, message):
        """记录错误."""
        log_mgr = self._get_log_manager()
        if log_mgr and hasattr(log_mgr, "log_error"):
            log_mgr.log_error(message)
        else:
            print(f"错误: {message}")

    def _start_detection(self):
        """开始检测."""
        try:
            # 获取检测管理器
            detection_mgr = self._get_detection_manager()

            # 尝试从主窗口启动检测（如果可用）
            import os
            import sys

            # 添加项目根目录到Python路径
            sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

            # 尝试获取主窗口实例（如果存在）
            main_window = None
            try:
                from PyQt5.QtWidgets import QApplication

                if QApplication.instance():
                    for widget in QApplication.instance().allWidgets():
                        if (
                            hasattr(widget, "start_detection")
                            and hasattr(widget, "__class__")
                            and widget.__class__.__name__ == "MainWindow"
                        ):
                            main_window = widget
                            break
            except ImportError:
                pass

            # 如果找到主窗口，使用主窗口的start_detection方法
            if main_window and hasattr(main_window, "start_detection"):
                success = main_window.start_detection()
                if success:
                    self._detection_active = True
                    self._log("检测控制", "已通过主窗口开始异物检测")
                else:
                    self._log_error("通过主窗口启动检测失败")
            else:
                # 回退到直接调用检测管理器
                if detection_mgr:
                    if hasattr(detection_mgr, "start_camera_detection"):
                        detection_mgr.start_camera_detection()
                        self._detection_active = True
                        self._log("检测控制", "已开始异物检测")
                    elif hasattr(detection_mgr, "start"):
                        detection_mgr.start()
                        self._detection_active = True
                        self._log("检测控制", "已开始异物检测")
                    else:
                        self._log_error("检测管理器没有可用的启动方法")
                else:
                    self._log_error("无法获取检测管理器")

            # 确保视频捕获器已启动
            try:
                from video_capture.video_capturer import video_capturer

                if not video_capturer.is_running():
                    video_capturer.start_capture(0)
            except ImportError:
                pass
        except Exception as e:
            self._log_error(f"启动检测失败: {e}")

    def _stop_detection(self):
        """停止检测."""
        try:
            # 如果有定时器在运行，先取消
            self._cancel_stop_timer()

            # 尝试从主窗口停止检测（如果可用）
            main_window = None
            try:
                from PyQt5.QtWidgets import QApplication

                if QApplication.instance():
                    for widget in QApplication.instance().allWidgets():
                        if (
                            hasattr(widget, "stop_detection")
                            and hasattr(widget, "__class__")
                            and widget.__class__.__name__ == "MainWindow"
                        ):
                            main_window = widget
                            break
            except ImportError:
                pass

            # 如果找到主窗口，使用主窗口的stop_detection方法
            if main_window and hasattr(main_window, "stop_detection"):
                main_window.stop_detection()
                self._detection_active = False
                self._log("检测控制", "已通过主窗口停止异物检测")
            else:
                # 获取检测管理器
                detection_mgr = self._get_detection_manager()

                # 如果检测管理器有直接的停止方法，调用它
                if detection_mgr:
                    if hasattr(detection_mgr, "stop_camera_detection"):
                        detection_mgr.stop_camera_detection()
                    elif hasattr(detection_mgr, "stop"):
                        detection_mgr.stop()

                # 停止视频捕获器
                try:
                    from video_capture.video_capturer import video_capturer

                    if video_capturer.is_running():
                        video_capturer.stop_capture()
                except ImportError:
                    pass

                self._detection_active = False
                self._log("检测控制", "已停止异物检测")
        except Exception as e:
            self._log_error(f"停止检测失败: {e}")

    def _start_stop_detection_timer(self):
        """启动定时器，2秒后停止检测."""
        # 先取消已有的定时器
        self._cancel_stop_timer()

        # 创建新的定时器
        self._log("检测控制", "已启动2秒后停止检测的定时器")
        self._stop_timer = threading.Timer(2.0, self._timer_callback)
        self._stop_timer.daemon = True
        self._stop_timer.start()

    def _timer_callback(self):
        """定时器回调函数."""
        # 检查当前状态是否仍为CLOSED
        if self.get_current_state() == SystemState.CLOSED:
            self._log("检测控制", "定时器触发，正在停止检测")
            self._stop_detection()
        else:
            self._log("检测控制", "定时器触发，但状态已改变，不执行停止操作")

    def _cancel_stop_timer(self):
        """取消定时器."""
        if self._stop_timer:
            self._stop_timer.cancel()
            self._stop_timer = None

    def reset_to_idle(self):
        self.set_state(SystemState.IDLE)

    def simulate_signal(self, signal_type):
        if signal_type == "close_command":
            self.trigger_close_command()
            return True
        elif signal_type == "closed_command":
            self.trigger_closed_command()
            return True
        else:
            print(f"未知信号类型: {signal_type}")
            return False


signal_handler = SignalHandler()
