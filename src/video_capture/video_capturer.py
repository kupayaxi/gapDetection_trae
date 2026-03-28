import os
import sys
import threading
import time

import cv2

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 导入信号处理器
try:
    from logger.log_manager import log_manager
    from object_detection.detection_manager import detection_manager
    from signal_handler.signal_handler import SystemState, signal_handler
except ImportError:
    # 如果直接导入失败，尝试使用src前缀
    try:
        from src.logger.log_manager import log_manager
        from src.object_detection.detection_manager import detection_manager
        from src.signal_handler.signal_handler import SystemState, signal_handler
    except ImportError as e:
        print(f"导入失败: {e}")
        raise


class VideoCapturer:
    def __init__(self):
        self._cap = None
        self._running = False
        self._thread = None
        self._frame_callbacks = []
        self._roi = None
        self._lock = threading.RLock()
        self._fps = 30
        self._should_be_running = False  # 表示系统期望的运行状态

        # 注册状态变化回调
        signal_handler.register_state_change_callback(self._on_state_changed)

    def register_frame_callback(self, callback):
        with self._lock:
            if callback not in self._frame_callbacks:
                self._frame_callbacks.append(callback)

    def unregister_frame_callback(self, callback):
        with self._lock:
            if callback in self._frame_callbacks:
                self._frame_callbacks.remove(callback)

    def _on_state_changed(self, old_state, new_state):
        """响应系统状态变化."""
        try:
            # 在CLOSING或CLOSED状态时启动视频捕获
            if new_state in [SystemState.CLOSING, SystemState.CLOSED]:
                self._should_be_running = True
                if not self._running:
                    log_manager.log_system_event("视频捕获", "系统状态变化，开始视频捕获")
                    self.start_capture()
            # 在IDLE状态时停止视频捕获
            elif new_state == SystemState.IDLE:
                self._should_be_running = False
                if self._running:
                    log_manager.log_system_event("视频捕获", "系统状态变化，停止视频捕获")
                    self.stop_capture()
        except Exception as e:
            log_manager.log_error(f"处理状态变化时出错: {e}")

    def start_capture(self, source=0):
        with self._lock:
            if self._running:
                log_manager.log_system_event("视频捕获", "视频捕获已经在运行中")
                return False
            try:
                self._cap = cv2.VideoCapture(source)
                if not self._cap.isOpened():
                    log_manager.log_error("无法打开摄像头")
                    return False
                self._running = True
                self._thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._thread.start()
                log_manager.log_system_event("视频捕获", f"已启动视频捕获，源: {source}")
                return True
            except Exception as e:
                log_manager.log_error(f"启动视频捕获失败: {e}")
                self._cap = None
                self._running = False
                return False

    def stop_capture(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        if self._cap:
            self._cap.release()
            self._cap = None
        log_manager.log_system_event("视频捕获", "视频捕获已停止")

    def _capture_loop(self):
        frame_count = 0
        start_time = time.time()

        while self._running:
            ret, frame = self._cap.read() if self._cap else (False, None)
            if not ret:
                log_manager.log_error("无法读取视频帧")
                break

            # 处理帧
            try:
                # 获取当前系统状态
                current_state = signal_handler.get_current_state()

                # 仅在CLOSING状态下进行检测（已关闭状态只延迟停止捕获，但不再进行检测）
                if current_state == SystemState.CLOSING:
                    # 直接将帧传递给检测管理器
                    detection_manager.detect_frame(frame)

                # 计算FPS
                frame_count += 1
                if time.time() - start_time >= 1.0:
                    fps = frame_count / (time.time() - start_time)
                    frame_count = 0
                    start_time = time.time()
                    # 每秒记录一次FPS
                    if frame_count % 30 == 0:
                        log_manager.log_system_event("视频捕获", f"当前FPS: {fps:.2f}")

                # 调用所有回调函数
                with self._lock:
                    callbacks = self._frame_callbacks.copy()
                for callback in callbacks:
                    try:
                        callback(frame)
                    except Exception as e:
                        log_manager.log_error(f"帧回调执行失败: {e}")
            except Exception as e:
                log_manager.log_error(f"处理视频帧时出错: {e}")

            # 控制帧率
            time.sleep(1.0 / self._fps)

    def is_running(self):
        with self._lock:
            return self._running

    def start(self, source=None):
        if source is not None:
            return self.start_capture(source)
        return self.start_capture()

    def stop(self):
        return self.stop_capture()

    def set_roi(self, roi):
        with self._lock:
            self._roi = roi

    def get_roi(self):
        with self._lock:
            return self._roi


video_capturer = VideoCapturer()
