import cv2
import threading
import time

class VideoCapturer:
    def __init__(self):
        self._cap = None
        self._running = False
        self._thread = None
        self._frame_callbacks = []
        self._roi = None
        self._lock = threading.RLock()
        self._fps = 30
    
    def register_frame_callback(self, callback):
        with self._lock:
            if callback not in self._frame_callbacks:
                self._frame_callbacks.append(callback)
    
    def unregister_frame_callback(self, callback):
        with self._lock:
            if callback in self._frame_callbacks:
                self._frame_callbacks.remove(callback)
    
    def start_capture(self, source=0):
        with self._lock:
            if self._running:
                return False
            try:
                self._cap = cv2.VideoCapture(source)
                if not self._cap.isOpened():
                    return False
                self._running = True
                self._thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._thread.start()
                return True
            except Exception:
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
    
    def _capture_loop(self):
        while self._running:
            ret, frame = self._cap.read() if self._cap else (False, None)
            if not ret:
                break
            with self._lock:
                callbacks = self._frame_callbacks.copy()
            for callback in callbacks:
                try:
                    callback(frame)
                except Exception:
                    pass
            time.sleep(0.03)
    
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