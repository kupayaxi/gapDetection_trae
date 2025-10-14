import sys
import cv2
import threading
import time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGroupBox, QGridLayout, QSlider, QComboBox,
    QMessageBox, QSplitter, QFrame, QCheckBox, QTextEdit, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt5.QtGui import QImage, QPixmap, QFont

# 实际的视频捕获器类
class VideoCapturer:
    def __init__(self):
        self._cap = None
        self._running = False
        self._thread = None
        self._frame_callbacks = []
        self._roi = None
        self._lock = threading.RLock()
    
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
                    raise Exception(f"无法打开视频源: {source}")
                
                self._running = True
                self._thread = threading.Thread(target=self._capture_loop, daemon=True)
                self._thread.start()
                return True
            except Exception as e:
                print(f"启动视频捕获失败: {str(e)}")
                self._cap = None
                self._running = False
                return False
    
    def _capture_loop(self):
        while self._running and self._cap:
            try:
                ret, frame = self._cap.read()
                if ret:
                    # 不要在这里裁剪画面，传递完整的帧给回调函数
                    # ROI过滤应该在DetectionManager中进行
                    
                    # 调用所有注册的回调函数
                    with self._lock:
                        callbacks = self._frame_callbacks.copy()
                    for callback in callbacks:
                        try:
                            callback(frame)
                        except Exception as e:
                            print(f"执行帧回调失败: {str(e)}")
                else:
                    # 如果无法读取帧，暂停一下
                    time.sleep(0.1)
            except Exception as e:
                print(f"捕获帧失败: {str(e)}")
                time.sleep(0.1)
    
    def stop_capture(self):
        with self._lock:
            if not self._running:
                return
            self._running = False
        
        # 等待线程结束
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        # 释放摄像头
        if self._cap:
            self._cap.release()
            self._cap = None
    
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

# 创建全局视频捕获器实例
video_capturer = VideoCapturer()

from ..signal_handler.signal_handler import signal_handler, SystemState
from ..config.config_manager import config_manager
from ..logger.log_manager import log_manager
from ..object_detection.detection_manager import detection_manager

class UIUpdater(QObject):
    """UI更新器，用于在主线程中更新UI"""
    update_signal = pyqtSignal(dict)  # 信号，传递检测结果

class MainWindow(QMainWindow):
    """主窗口类"""
    
    def __init__(self):
        super().__init__()
        # 初始化ROI相关变量
        self.roi_enabled = True
        self.roi_coords = [300, 200, 900, 500]  # 默认ROI [x1, y1, x2, y2]
        self.roi_editing = False
        self.roi_dragging = False
        self.drag_handle = None  # 1:左上, 2:右上, 3:左下, 4:右下, 5:中间
        self.drag_start_pos = (0, 0)
        self.roi_start_coords = [0, 0, 0, 0]
        self.init_ui()
        self.setup_connections()
        # 视频更新定时器
        self.video_timer = QTimer(self)
        self.video_timer.timeout.connect(self.update_video_display)
        # 最后一帧图像缓存
        self.last_frame = None
        # 最后检测结果缓存
        self.last_detection_result = None
        # 创建一个信号对象用于跨线程更新UI
        self.ui_updater = UIUpdater()
        self.ui_updater.update_signal.connect(self._update_ui_with_result)
    
    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle("地铁屏蔽门间隙检测系统")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧控制面板
        control_panel = self.create_control_panel()
        splitter.addWidget(control_panel)
        
        # 右侧显示区域
        display_area = self.create_display_area()
        splitter.addWidget(display_area)
        
        # 设置分割器比例
        splitter.setSizes([300, 900])
        
        main_layout.addWidget(splitter)
        
        # 底部状态栏
        self.statusBar().showMessage("系统就绪")
    
    def create_control_panel(self):
        """创建控制面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        
        # 系统控制组
        system_group = QGroupBox("系统控制")
        system_layout = QVBoxLayout()
        
        self.start_button = QPushButton("启动检测")
        self.stop_button = QPushButton("停止检测")
        self.stop_button.setEnabled(False)
        
        system_layout.addWidget(self.start_button)
        system_layout.addWidget(self.stop_button)
        system_group.setLayout(system_layout)
        
        # 摄像头控制组
        camera_group = QGroupBox("摄像头控制")
        camera_layout = QVBoxLayout()
        
        self.start_camera_button = QPushButton("启动摄像头检测")
        self.stop_camera_button = QPushButton("停止摄像头检测")
        self.stop_camera_button.setEnabled(False)
        
        camera_layout.addWidget(self.start_camera_button)
        camera_layout.addWidget(self.stop_camera_button)
        camera_group.setLayout(camera_layout)
        
        # 信号模拟组
        signal_group = QGroupBox("信号模拟")
        signal_layout = QVBoxLayout()
        
        self.close_command_button = QPushButton("关门命令")
        self.closed_command_button = QPushButton("已关闭命令")
        self.reset_button = QPushButton("重置系统")
        
        signal_layout.addWidget(self.close_command_button)
        signal_layout.addWidget(self.closed_command_button)
        signal_layout.addWidget(self.reset_button)
        signal_group.setLayout(signal_layout)
        
        # ROI设置组
        roi_group = QGroupBox("ROI设置")
        roi_layout = QGridLayout()
        
        # ROI启用复选框
        self.roi_enable_checkbox = QCheckBox("启用ROI检测")
        self.roi_enable_checkbox.setChecked(True)
        roi_layout.addWidget(self.roi_enable_checkbox, 0, 0, 1, 3)
        
        # ROI坐标输入
        roi_layout.addWidget(QLabel("X1:"), 1, 0)
        self.roi_x1_input = QComboBox()
        for i in range(0, 1280, 50):
            self.roi_x1_input.addItem(str(i))
        self.roi_x1_input.setCurrentText(str(self.roi_coords[0]))
        roi_layout.addWidget(self.roi_x1_input, 1, 1)
        
        roi_layout.addWidget(QLabel("Y1:"), 1, 2)
        self.roi_y1_input = QComboBox()
        for i in range(0, 720, 50):
            self.roi_y1_input.addItem(str(i))
        self.roi_y1_input.setCurrentText(str(self.roi_coords[1]))
        roi_layout.addWidget(self.roi_y1_input, 1, 3)
        
        roi_layout.addWidget(QLabel("X2:"), 2, 0)
        self.roi_x2_input = QComboBox()
        for i in range(0, 1280, 50):
            self.roi_x2_input.addItem(str(i))
        self.roi_x2_input.setCurrentText(str(self.roi_coords[2]))
        roi_layout.addWidget(self.roi_x2_input, 2, 1)
        
        roi_layout.addWidget(QLabel("Y2:"), 2, 2)
        self.roi_y2_input = QComboBox()
        for i in range(0, 720, 50):
            self.roi_y2_input.addItem(str(i))
        self.roi_y2_input.setCurrentText(str(self.roi_coords[3]))
        roi_layout.addWidget(self.roi_y2_input, 2, 3)
        
        # ROI编辑按钮
        self.roi_edit_button = QPushButton("进入ROI编辑模式")
        roi_layout.addWidget(self.roi_edit_button, 3, 0, 1, 4)
        
        # 应用ROI按钮
        self.apply_roi_button = QPushButton("应用ROI设置")
        roi_layout.addWidget(self.apply_roi_button, 4, 0, 1, 4)
        
        roi_group.setLayout(roi_layout)
        
        # 检测参数组
        param_group = QGroupBox("检测参数")
        param_layout = QGridLayout()
        
        # 置信度阈值
        param_layout.addWidget(QLabel("置信度阈值:"), 0, 0)
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(10, 90)
        self.confidence_slider.setValue(50)
        self.confidence_value = QLabel("50%")
        param_layout.addWidget(self.confidence_slider, 0, 1)
        param_layout.addWidget(self.confidence_value, 0, 2)
        
        # 多帧验证开关
        self.frame_validation_checkbox = QCheckBox("启用多帧验证")
        # 从detection_manager获取当前设置
        self.frame_validation_checkbox.setChecked(detection_manager.get_enable_frame_validation())
        param_layout.addWidget(self.frame_validation_checkbox, 1, 0, 1, 3)
        
        # 连续帧数
        param_layout.addWidget(QLabel("连续帧数:"), 2, 0)
        self.frame_count_slider = QSlider(Qt.Horizontal)
        self.frame_count_slider.setRange(1, 5)
        self.frame_count_slider.setValue(2)
        self.frame_count_value = QLabel("2")
        param_layout.addWidget(self.frame_count_slider, 2, 1)
        param_layout.addWidget(self.frame_count_value, 2, 2)
        
        param_group.setLayout(param_layout)
        
        # 状态显示
        status_group = QGroupBox("系统状态")
        status_layout = QVBoxLayout()
        
        self.state_label = QLabel("当前状态: 空闲")
        status_layout.addWidget(self.state_label)
        
        # 检测结果显示
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFixedHeight(100)
        status_layout.addWidget(QLabel("检测结果:"))
        status_layout.addWidget(self.result_text)
        
        status_group.setLayout(status_layout)
        
        # 添加到主布局
        layout.addWidget(system_group)
        layout.addWidget(camera_group)
        layout.addWidget(signal_group)
        layout.addWidget(roi_group)
        layout.addWidget(param_group)
        layout.addWidget(status_group)
        layout.addStretch()
        
        return panel
    
    def create_display_area(self):
        """创建显示区域"""
        area = QWidget()
        layout = QVBoxLayout(area)
        
        # 视频显示
        self.video_label = QLabel("视频显示区域")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.video_label.setMinimumSize(640, 480)
        
        # 为视频标签添加鼠标事件
        self.video_label.mousePressEvent = self.on_video_label_mouse_press
        self.video_label.mouseMoveEvent = self.on_video_label_mouse_move
        self.video_label.mouseReleaseEvent = self.on_video_label_mouse_release
        
        layout.addWidget(self.video_label)
        
        return area
    
    def setup_connections(self):
        """设置信号连接"""
        # 系统控制按钮
        self.start_button.clicked.connect(self.start_detection)
        self.stop_button.clicked.connect(self.stop_detection)
        
        # 信号模拟按钮
        self.close_command_button.clicked.connect(lambda: signal_handler.simulate_signal('close_command'))
        self.closed_command_button.clicked.connect(lambda: signal_handler.simulate_signal('closed_command'))
        self.reset_button.clicked.connect(signal_handler.reset_to_idle)
        
        # 参数滑块
        self.confidence_slider.valueChanged.connect(lambda value: self.confidence_value.setText(f"{value}%"))
        self.confidence_slider.valueChanged.connect(lambda value: config_manager.set("detection.confidence_threshold", value / 100))
        
        # 多帧验证开关
        self.frame_validation_checkbox.stateChanged.connect(lambda state: 
            detection_manager.set_enable_frame_validation(state == Qt.Checked))
        
        self.frame_count_slider.valueChanged.connect(lambda value: self.frame_count_value.setText(str(value)))
        self.frame_count_slider.valueChanged.connect(lambda value: config_manager.set("detection.frame_validation_count", value))
        
        # 注册状态变化回调
        signal_handler.register_state_change_callback(self.on_state_changed)
        
        # 注册报警回调
        signal_handler.register_alarm_callback(self.on_alarm)
        
        # 摄像头控制按钮连接
        self.start_camera_button.clicked.connect(self.start_camera_detection)
        self.stop_camera_button.clicked.connect(self.stop_camera_detection)
        
        # 注册视频帧回调
        video_capturer.register_frame_callback(self.on_new_frame)
        
        # 注册检测结果回调
        detection_manager.register_detection_callback(self.on_detection_result)
        
        # ROI相关连接
        self.roi_enable_checkbox.stateChanged.connect(self.on_roi_enable_changed)
        self.apply_roi_button.clicked.connect(self.apply_roi_settings)
        self.roi_edit_button.clicked.connect(self.toggle_roi_editing_mode)
    
    def start_detection(self):
        """开始检测"""
        self.statusBar().showMessage("开始检测...")
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        
        # 首先启动视频捕获器
        if not video_capturer.is_running():
            if not video_capturer.start_capture(0):  # 使用默认摄像头
                QMessageBox.warning(self, "警告", "无法启动摄像头，请检查设备连接")
                return
        
        # 启动视频显示定时器
        self.video_timer.start(30)  # 约33fps
        
        # 启动摄像头检测
        success = detection_manager.start_camera_detection()
        if success:
            self.start_camera_button.setEnabled(False)
            self.stop_camera_button.setEnabled(True)
            QMessageBox.information(self, "提示", "检测功能已启动")
        else:
            # 如果检测进程启动失败，停止视频捕获
            self.video_timer.stop()
            video_capturer.stop_capture()
            QMessageBox.warning(self, "警告", "摄像头检测启动失败")
    
    def stop_detection(self):
        """停止检测"""
        self.statusBar().showMessage("停止检测...")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        
        # 停止视频显示和捕获
        self.video_timer.stop()
        video_capturer.stop_capture()
        
        # 停止摄像头检测
        detection_manager.stop_camera_detection()
        self.start_camera_button.setEnabled(True)
        self.stop_camera_button.setEnabled(False)
        QMessageBox.information(self, "提示", "检测功能已停止")
    
    def start_camera_detection(self):
        """手动启动摄像头检测"""
        # 首先启动视频捕获器
        if not video_capturer.is_running():
            if not video_capturer.start_capture(0):  # 使用默认摄像头
                QMessageBox.warning(self, "警告", "无法启动摄像头，请检查设备连接")
                return
        
        # 启动视频显示定时器
        self.video_timer.start(30)  # 约33fps
        
        # 然后启动检测进程
        success = detection_manager.start_camera_detection()
        if success:
            self.start_camera_button.setEnabled(False)
            self.stop_camera_button.setEnabled(True)
            self.statusBar().showMessage("摄像头检测已启动")
            QMessageBox.information(self, "提示", "摄像头检测已启动")
        else:
            # 如果检测进程启动失败，停止视频捕获
            self.video_timer.stop()
            video_capturer.stop_capture()
            QMessageBox.warning(self, "警告", "摄像头检测启动失败")
    
    def stop_camera_detection(self):
        """手动停止摄像头检测"""
        # 停止检测进程
        detection_manager.stop_camera_detection()
        
        # 停止视频显示和捕获
        self.video_timer.stop()
        video_capturer.stop_capture()
        
        self.start_camera_button.setEnabled(True)
        self.stop_camera_button.setEnabled(False)
        self.statusBar().showMessage("摄像头检测已停止")
        QMessageBox.information(self, "提示", "摄像头检测已停止")
    
    def on_state_changed(self, old_state, new_state):
        """状态变化处理"""
        state_names = {
            SystemState.IDLE: "空闲",
            SystemState.CLOSING: "关门中",
            SystemState.CLOSED: "已关闭",
            SystemState.ALARM: "报警"
        }
        
        self.state_label.setText(f"当前状态: {state_names.get(new_state, '未知')}")
        self.statusBar().showMessage(f"系统状态: {state_names.get(new_state, '未知')}")
    
    def on_alarm(self, alarm_info):
        """报警处理"""
        # 确保这是在主线程中运行
        if threading.current_thread().name != 'MainThread':
            # 对于复杂类型，使用定时器在主线程中执行
            QTimer.singleShot(0, lambda: self.on_alarm(alarm_info))
            return
        
        # 显示报警信息
        message = f"检测到异物！\n类型: {alarm_info.get('type', '未知')}\n位置: {alarm_info.get('location', '未知')}"
        self.result_text.append(message)
        
        # 弹出报警对话框
        QMessageBox.warning(self, "报警", message)
    
    def on_detection_result(self, result):
        """处理检测结果（可能在检测线程中被调用）"""
        # 确保这是在主线程中被调用，如果不是，通过信号发送
        if threading.current_thread().name == 'MainThread':
            # 直接在主线程中处理
            self._update_ui_with_result(result)
        else:
            # 保存检测结果
            self.last_detection_result = result
            # 使用信号将更新发送到主线程
            self.ui_updater.update_signal.emit(result)
    
    def _update_ui_with_result(self, result):
        """在主线程中更新UI显示（由信号触发）"""
        # 确保这是在主线程中运行
        if threading.current_thread().name != 'MainThread':
            # 对于复杂类型，使用定时器在主线程中执行
            QTimer.singleShot(0, lambda: self._update_ui_with_result(result))
            return
        
        # 提取检测到的物体信息
        if result and 'objects' in result and result['objects']:
            detected_objects = []
            for obj in result['objects']:
                obj_type = obj.get('class_name', '未知')
                confidence = obj.get('confidence', 0)
                detected_objects.append(f"{obj_type} (置信度: {confidence:.2f})")
            
            # 更新结果文本区域
            result_text = "检测到物体: " + ", ".join(detected_objects)
            
            # 更新状态栏和结果文本框
            self.statusBar().showMessage(result_text)
            self.result_text.append(result_text)
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        reply = QMessageBox.question(
            self, '确认退出', '确定要退出系统吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # 停止检测等清理工作
            self.video_timer.stop()
            video_capturer.unregister_frame_callback(self.on_new_frame)
            # 移除检测结果回调
            try:
                detection_manager.unregister_detection_callback(self.on_detection_result)
            except Exception as e:
                print(f"移除检测回调失败: {str(e)}")
            self.stop_detection()
            event.accept()
        else:
            event.ignore()
    
    def on_new_frame(self, frame):
        """处理新的视频帧，将其发送给检测模块进行处理"""
        # 保存帧到缓存
        self.last_frame = frame
        
        # 直接调用处理函数，让检测模块在自己的线程中处理
        # 避免每次创建新线程导致的资源浪费和潜在问题
        try:
            # 将帧复制后传入检测管理器
            detection_manager.detect_frame(frame.copy())
        except Exception as e:
            print(f"帧处理发送失败: {str(e)}")
    
    # 移除_process_frame_for_detection方法，避免线程创建问题
    
    def update_video_display(self):
        """更新视频显示，并在图像上绘制检测结果和ROI"""
        # 确保这是在主线程中运行
        if threading.current_thread().name != 'MainThread':
            # 对于复杂类型，使用定时器在主线程中执行
            QTimer.singleShot(0, self.update_video_display)
            return
            
        if self.last_frame is None:
            return
        
        try:
            # 创建帧的副本
            display_frame = self.last_frame.copy()
            
            # 绘制ROI矩形
            if self.roi_enabled and self.roi_coords:
                roi_color = (0, 0, 255) if self.roi_editing else (255, 0, 0)
                thickness = 2
                x1, y1, x2, y2 = self.roi_coords
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), roi_color, thickness)
                
                # 在编辑模式下，绘制拖拽点和提示
                if self.roi_editing:
                    # 绘制四个角的拖拽点
                    points = [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]
                    for point in points:
                        cv2.circle(display_frame, point, 5, (0, 255, 255), -1)
                    
                    # 添加提示文本
                    cv2.putText(display_frame, "拖拽调整ROI区域", (x1, y1 - 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
            
            # 在图像上绘制检测结果
            if self.last_detection_result and 'objects' in self.last_detection_result:
                for obj in self.last_detection_result['objects']:
                    # 获取边界框坐标
                    x1, y1, x2, y2 = int(obj.get('x1')), int(obj.get('y1')), int(obj.get('x2')), int(obj.get('y2'))
                    # 绘制边界框
                    cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    
                    # 添加标签和置信度
                    label = f"{obj.get('class_name', 'Unknown')} {obj.get('confidence', 0):.2f}"
                    cv2.putText(display_frame, label, (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            
            # 将OpenCV的BGR格式转换为RGB格式
            rgb_image = cv2.cvtColor(display_frame, cv2.COLOR_BGR2RGB)
            
            # 转换为QImage
            height, width, channel = rgb_image.shape
            bytes_per_line = 3 * width
            q_image = QImage(rgb_image.data, width, height, bytes_per_line, QImage.Format_RGB888)
            
            # 缩放到标签大小
            pixmap = QPixmap.fromImage(q_image)
            scaled_pixmap = pixmap.scaled(
                self.video_label.size(), 
                Qt.KeepAspectRatio, 
                Qt.SmoothTransformation
            )
            
            # 设置到标签
            self.video_label.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"更新视频显示失败: {str(e)}")
            # 只记录错误，不中断程序
    
    def on_roi_enable_changed(self, state):
        """处理ROI启用状态变化"""
        self.roi_enabled = (state == Qt.Checked)
        self.apply_roi_settings()
    
    def apply_roi_settings(self):
        """应用ROI设置"""
        try:
            # 从输入框获取坐标
            x1 = int(self.roi_x1_input.currentText())
            y1 = int(self.roi_y1_input.currentText())
            x2 = int(self.roi_x2_input.currentText())
            y2 = int(self.roi_y2_input.currentText())
            
            # 确保坐标有效
            if x1 >= x2 or y1 >= y2:
                QMessageBox.warning(self, "警告", "ROI坐标无效，请确保X1<X2且Y1<Y2")
                return
            
            # 更新ROI坐标（使用[x1, y1, x2, y2]格式）
            self.roi_coords = [x1, y1, x2, y2]
            
            # 保存到配置管理器
            config_manager.set("detection.roi", self.roi_coords if self.roi_enabled else None)
            
            # 更新检测管理器的ROI设置
            detection_manager.roi = self.roi_coords if self.roi_enabled else None
            
            # 更新状态栏提示
            self.statusBar().showMessage(f"ROI设置已应用: {self.roi_coords}")
            
            # 立即更新视频显示以反映ROI变化
            self.update_video_display()
            
        except ValueError:
            QMessageBox.warning(self, "警告", "请输入有效的坐标值")
        except Exception as e:
            print(f"应用ROI设置失败: {str(e)}")
            QMessageBox.warning(self, "警告", f"应用ROI设置失败: {str(e)}")
    
    def toggle_roi_editing_mode(self):
        """切换ROI编辑模式"""
        if not video_capturer.is_running():
            QMessageBox.warning(self, "警告", "请先启动摄像头再进入ROI编辑模式")
            return
            
        if self.roi_editing:
            # 退出编辑模式
            self.roi_editing = False
            self.roi_edit_button.setText("进入ROI编辑模式")
            self.video_label.setCursor(Qt.ArrowCursor)
            
            # 应用ROI设置
            self.apply_roi_settings()
            
            # 确保下次编辑时可以正确开始
            self.roi_start_coords = self.roi_coords.copy()
            self.roi_dragging = False
            self.drag_handle = None
            
            self.statusBar().showMessage("ROI编辑模式已禁用")
        else:
            # 进入编辑模式
            self.roi_editing = True
            self.roi_edit_button.setText("退出ROI编辑模式")
            self.video_label.setCursor(Qt.CrossCursor)
            
            # 确保拖拽起始坐标正确
            self.roi_start_coords = self.roi_coords.copy()
            self.roi_dragging = False
            self.drag_handle = None
            
            self.statusBar().showMessage("ROI编辑模式已启用，可拖拽调整ROI区域")
    
    def on_video_label_mouse_press(self, event):
        """处理视频标签的鼠标按下事件"""
        if not self.roi_editing:
            # 调用原始的鼠标事件处理
            super(QLabel, self.video_label).mousePressEvent(event)
            return
        
        # 获取鼠标在标签上的位置
        label_pos = event.pos()
        
        # 将标签位置映射到实际图像坐标
        if self.last_frame is None:
            return
            
        img_height, img_width = self.last_frame.shape[:2]
        label_width = self.video_label.width()
        label_height = self.video_label.height()
        
        # 计算缩放比例
        scale_x = img_width / label_width
        scale_y = img_height / label_height
        
        # 转换为图像坐标
        img_x = int(label_pos.x() * scale_x)
        img_y = int(label_pos.y() * scale_y)
        
        # 检查是否点击了ROI的拖拽点
        x1, y1, x2, y2 = self.roi_coords
        
        # 定义拖拽区域的大小
        handle_size = 10
        
        # 检查是否点击了四个角
        if (abs(img_x - x1) <= handle_size and abs(img_y - y1) <= handle_size):
            self.roi_dragging = True
            self.drag_handle = 1  # 左上
        elif (abs(img_x - x2) <= handle_size and abs(img_y - y1) <= handle_size):
            self.roi_dragging = True
            self.drag_handle = 2  # 右上
        elif (abs(img_x - x1) <= handle_size and abs(img_y - y2) <= handle_size):
            self.roi_dragging = True
            self.drag_handle = 3  # 左下
        elif (abs(img_x - x2) <= handle_size and abs(img_y - y2) <= handle_size):
            self.roi_dragging = True
            self.drag_handle = 4  # 右下
        elif (x1 <= img_x <= x2 and y1 <= img_y <= y2):
            # 点击在ROI内部，移动整个ROI
            self.roi_dragging = True
            self.drag_handle = 5  # 中间
        
        if self.roi_dragging:
            self.drag_start_pos = (img_x, img_y)
            self.roi_start_coords = self.roi_coords.copy()
    
    def on_video_label_mouse_move(self, event):
        """处理视频标签的鼠标移动事件"""
        if not self.roi_dragging:
            # 调用原始的鼠标事件处理
            super(QLabel, self.video_label).mouseMoveEvent(event)
            return
        
        # 获取鼠标在标签上的位置
        label_pos = event.pos()
        
        # 将标签位置映射到实际图像坐标
        if self.last_frame is None:
            return
            
        img_height, img_width = self.last_frame.shape[:2]
        label_width = self.video_label.width()
        label_height = self.video_label.height()
        
        # 计算缩放比例
        scale_x = img_width / label_width
        scale_y = img_height / label_height
        
        # 转换为图像坐标
        img_x = int(label_pos.x() * scale_x)
        img_y = int(label_pos.y() * scale_y)
        
        # 计算移动距离
        dx = img_x - self.drag_start_pos[0]
        dy = img_y - self.drag_start_pos[1]
        
        # 根据拖拽的手柄更新ROI坐标
        x1, y1, x2, y2 = self.roi_start_coords
        
        if self.drag_handle == 1:  # 左上
            x1 = max(0, min(x2 - 10, x1 + dx))
            y1 = max(0, min(y2 - 10, y1 + dy))
        elif self.drag_handle == 2:  # 右上
            x2 = min(img_width, max(x1 + 10, x2 + dx))
            y1 = max(0, min(y2 - 10, y1 + dy))
        elif self.drag_handle == 3:  # 左下
            x1 = max(0, min(x2 - 10, x1 + dx))
            y2 = min(img_height, max(y1 + 10, y2 + dy))
        elif self.drag_handle == 4:  # 右下
            x2 = min(img_width, max(x1 + 10, x2 + dx))
            y2 = min(img_height, max(y1 + 10, y2 + dy))
        elif self.drag_handle == 5:  # 中间（移动整个ROI）
            # 计算新的坐标
            new_x1 = x1 + dx
            new_y1 = y1 + dy
            new_x2 = x2 + dx
            new_y2 = y2 + dy
            
            # 检查边界
            if new_x1 >= 0 and new_y1 >= 0 and new_x2 <= img_width and new_y2 <= img_height:
                x1, y1, x2, y2 = new_x1, new_y1, new_x2, new_y2
        
        # 更新ROI坐标
        self.roi_coords = [x1, y1, x2, y2]
    
    def on_video_label_mouse_release(self, event):
        """处理视频标签的鼠标释放事件"""
        if self.roi_dragging:
            self.roi_dragging = False
            self.drag_handle = None
            
            # 更新输入框中的值
            x1, y1, x2, y2 = self.roi_coords
            
            # 找到最接近的选项
            def find_nearest_option(combo, value):
                options = [int(combo.itemText(i)) for i in range(combo.count())]
                nearest = min(options, key=lambda x: abs(x - value))
                return nearest
            
            # 更新组合框
            nearest_x1 = find_nearest_option(self.roi_x1_input, x1)
            nearest_y1 = find_nearest_option(self.roi_y1_input, y1)
            nearest_x2 = find_nearest_option(self.roi_x2_input, x2)
            nearest_y2 = find_nearest_option(self.roi_y2_input, y2)
            
            self.roi_x1_input.setCurrentText(str(nearest_x1))
            self.roi_y1_input.setCurrentText(str(nearest_y1))
            self.roi_x2_input.setCurrentText(str(nearest_x2))
            self.roi_y2_input.setCurrentText(str(nearest_y2))
            
            # 更新ROI坐标为最近的选项
            self.roi_coords = [nearest_x1, nearest_y1, nearest_x2, nearest_y2]
            
            # 更新ROI起始坐标，确保下次拖拽可以正确开始
            self.roi_start_coords = self.roi_coords.copy()
            
            # 立即更新视频显示以反映ROI变化
            self.update_video_display()
        else:
            # 调用原始的鼠标事件处理
            super(QLabel, self.video_label).mouseReleaseEvent(event)