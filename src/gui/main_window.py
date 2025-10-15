import sys
import os
import cv2
import threading
import time

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
    QPushButton, QGroupBox, QGridLayout, QSlider, QComboBox,
    QMessageBox, QSplitter, QFrame, QCheckBox, QTextEdit, QScrollArea, QDialog
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject, pyqtSlot
import threading
from PyQt5.QtGui import QImage, QPixmap, QFont

# 导入模块
from signal_handler.signal_handler import signal_handler, SystemState
from config.config_manager import config_manager
from logger.log_manager import log_manager
from video_capture.video_capturer import video_capturer
from object_detection.detection_manager import detection_manager

class UIUpdater(QObject):
    """UI更新器，用于在主线程中更新UI"""
    update_signal = pyqtSignal(dict)  # 信号，传递检测结果

class MainWindow(QMainWindow):
    """主窗口类"""
    # 添加报警信号用于线程安全的UI更新
    alarm_signal = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        # 连接信号到槽函数
        self.alarm_signal.connect(self._safe_show_alarm_dialog)
        # 初始化ROI相关变量
        self.roi_enabled = True
        # 默认ROI坐标，确保完全在画面内部(默认1280x720)
        self.roi_coords = [50, 50, 600, 125]  # 默认ROI [x1, y1, x2, y2]，位于画面中央
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
        
        # 摄像头控制组
        camera_group = QGroupBox("摄像头控制")
        camera_layout = QVBoxLayout()
        
        self.camera_preview_button = QPushButton("开启摄像头预览")
        self.camera_preview_button.setStyleSheet("background-color: #00BCD4; color: white; font-weight: bold;")
        
        camera_layout.addWidget(self.camera_preview_button)
        camera_group.setLayout(camera_layout)
        
        # 信号控制组（作为唯一的控制方式，整合所有控制功能）
        signal_group = QGroupBox("信号控制")
        signal_layout = QVBoxLayout()
        
        self.close_command_button = QPushButton("关门命令")
        self.close_command_button.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold;")
        
        self.closed_command_button = QPushButton("已关闭命令")
        self.closed_command_button.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        
        self.reset_button = QPushButton("重置系统")
        self.reset_button.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold;")
        
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
        for i in range(0, 1280, 25):
            self.roi_x1_input.addItem(str(i))
        self.roi_x1_input.setCurrentText(str(self.roi_coords[0]))
        roi_layout.addWidget(self.roi_x1_input, 1, 1)
        
        roi_layout.addWidget(QLabel("Y1:"), 1, 2)
        self.roi_y1_input = QComboBox()
        for i in range(0, 720, 25):
            self.roi_y1_input.addItem(str(i))
        self.roi_y1_input.setCurrentText(str(self.roi_coords[1]))
        roi_layout.addWidget(self.roi_y1_input, 1, 3)
        
        roi_layout.addWidget(QLabel("X2:"), 2, 0)
        self.roi_x2_input = QComboBox()
        for i in range(0, 1280, 25):
            self.roi_x2_input.addItem(str(i))
        self.roi_x2_input.setCurrentText(str(self.roi_coords[2]))
        roi_layout.addWidget(self.roi_x2_input, 2, 1)
        
        roi_layout.addWidget(QLabel("Y2:"), 2, 2)
        self.roi_y2_input = QComboBox()
        for i in range(0, 720, 25):
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
        # 摄像头预览相关连接
        self.camera_preview_button.clicked.connect(self.toggle_camera_preview)
        
        # 信号控制按钮（作为唯一的控制方式）
        self.close_command_button.clicked.connect(self.on_close_command)
        self.closed_command_button.clicked.connect(self.on_closed_command)
        self.reset_button.clicked.connect(self.on_reset_system)
        
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
        
        # 注册视频帧回调
        video_capturer.register_frame_callback(self.on_new_frame)
        
        # 注册检测结果回调
        detection_manager.register_detection_callback(self.on_detection_result)
        
        # ROI相关连接
        self.roi_enable_checkbox.stateChanged.connect(self.on_roi_enable_changed)
        self.apply_roi_button.clicked.connect(self.apply_roi_settings)
        self.roi_edit_button.clicked.connect(self.toggle_roi_editing_mode)
    
    def start_detection(self):
        """开始检测（内部方法，通过信号控制调用）"""
        self.statusBar().showMessage("开始检测...")
        
        # 首先启动视频捕获器（如果还没启动）
        if not video_capturer.is_running():
            if not video_capturer.start_capture(0):  # 使用默认摄像头
                print("无法启动摄像头，请检查设备连接")
                return False
        
        # 启动视频显示定时器（如果还没启动）
        if not self.video_timer.isActive():
            self.video_timer.start(30)  # 约33fps
        
        # 启动摄像头检测
        success = detection_manager.start_camera_detection()
        if success:
            # 更新摄像头预览按钮状态，因为现在在检测模式
            self.camera_preview_button.setText("关闭摄像头预览")
            self.camera_preview_button.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
            return True
        else:
            # 如果检测进程启动失败，停止视频捕获
            self.video_timer.stop()
            video_capturer.stop_capture()
            return False
    
    def stop_detection(self):
        """停止检测（内部方法，通过信号控制调用）"""
        self.statusBar().showMessage("停止检测...")
        
        # 停止检测线程，但保持视频捕获和预览
        detection_manager.stop_camera_detection()
        
        # 更新状态信息
        self.statusBar().showMessage("摄像头预览中（未检测）")
        self.state_label.setText("当前状态: 摄像头预览中")
        
        # 确保摄像头预览按钮状态正确
        if video_capturer.is_running():
            self.camera_preview_button.setText("关闭摄像头预览")
            self.camera_preview_button.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
    
    def start_camera_detection(self):
        """手动启动摄像头检测 - 现在通过信号控制统一管理"""
        # 这个方法现在被信号控制机制取代，调用on_close_command实现统一的控制逻辑
        self.on_close_command()
    
    def stop_camera_detection(self):
        """手动停止摄像头检测 - 现在通过信号控制统一管理"""
        # 这个方法现在被信号控制机制取代，调用on_reset_system实现统一的控制逻辑
        self.on_reset_system()
    
    def on_close_command(self):
        """处理关门命令按钮点击"""
        signal_handler.simulate_signal('close_command')
        self.statusBar().showMessage("收到关门命令，开始检测...")
        
    def on_closed_command(self):
        """处理已关闭命令按钮点击"""
        signal_handler.simulate_signal('closed_command')
        self.statusBar().showMessage("收到已关闭信号，将在2秒后停止检测...")
    
    def toggle_camera_preview(self):
        """切换摄像头预览状态"""
        if video_capturer.is_running():
            # 检查是否有检测线程在运行
            if hasattr(detection_manager, '_detection_thread') and detection_manager._detection_thread.is_alive():
                self.stop_detection()
            # 停止摄像头预览
            self.stop_camera_preview()
        else:
            # 启动摄像头预览
            self.start_camera_preview()
    
    def start_camera_preview(self):
        """启动摄像头预览（不进行检测）"""
        # 确保不在检测状态
        if hasattr(detection_manager, '_detection_thread') and detection_manager._detection_thread.is_alive():
            self.stop_detection()
        
        # 启动视频捕获器
        if not video_capturer.start_capture(0):  # 使用默认摄像头
            QMessageBox.warning(self, "警告", "无法启动摄像头，请检查设备连接")
            return False
        
        # 启动视频显示定时器
        self.video_timer.start(30)  # 约33fps
        
        # 更新按钮状态
        self.camera_preview_button.setText("关闭摄像头预览")
        self.camera_preview_button.setStyleSheet("background-color: #F44336; color: white; font-weight: bold;")
        
        # 更新状态信息
        self.statusBar().showMessage("摄像头预览已启动")
        self.state_label.setText("当前状态: 摄像头预览中")
        
        return True
    
    def stop_camera_preview(self):
        """停止摄像头预览"""
        # 停止视频显示和捕获
        self.video_timer.stop()
        video_capturer.stop_capture()
        
        # 更新按钮状态
        self.camera_preview_button.setText("开启摄像头预览")
        self.camera_preview_button.setStyleSheet("background-color: #00BCD4; color: white; font-weight: bold;")
        
        # 清除视频显示
        self.video_label.setText("视频显示区域")
        self.video_label.clear()  # 使用clear()方法代替setPixmap(None)
        
        # 更新状态信息
        self.statusBar().showMessage("系统就绪")
        self.state_label.setText("当前状态: 空闲")
        
        # 确保ROI编辑模式也被禁用
        if self.roi_editing:
            self.toggle_roi_editing_mode()
    
    def on_state_changed(self, old_state, new_state):
        """状态变化处理"""
        state_names = {
            SystemState.IDLE: "空闲",
            SystemState.CLOSING: "关门中（检测进行中）",
            SystemState.CLOSED: "已关闭（延迟停止检测）",
            SystemState.ALARM: "报警"
        }
        
        self.state_label.setText(f"当前状态: {state_names.get(new_state, '未知')}")
        
        # 更新状态栏消息
        status_messages = {
            SystemState.IDLE: "系统就绪",
            SystemState.CLOSING: "关门中，正在进行异物检测",
            SystemState.CLOSED: "已关闭，将在2秒后停止检测",
            SystemState.ALARM: "检测到异物！请立即处理！"
        }
        
        self.statusBar().showMessage(status_messages.get(new_state, "未知状态"))
        
        # 处理状态转换逻辑
        if old_state == SystemState.IDLE and new_state == SystemState.CLOSING:
            # 开始检测
            self.start_detection()
        elif new_state == SystemState.IDLE:
            # 如果进入空闲状态，停止检测但保持摄像头开启状态（如果用户希望继续预览）
            if hasattr(detection_manager, '_detection_thread') and detection_manager._detection_thread.is_alive():
                detection_manager.stop_camera_detection()
            # 不停止视频捕获，让用户可以继续预览和调整ROI
        
        # 处理从CLOSING到CLOSED的转换，设置定时器监控检测状态变化
        if old_state == SystemState.CLOSING and new_state == SystemState.CLOSED:
            # 设置一个定时器，定期检查检测状态是否已停止
            def check_detection_status():
                # 检查检测线程是否已停止
                if hasattr(detection_manager, '_detection_thread'):
                    if not detection_manager._detection_thread.is_alive():
                        # 检测已停止，但保持摄像头预览
                        self.state_label.setText("当前状态: 摄像头预览中（未检测）")
                        self.statusBar().showMessage("检测已停止，保持摄像头预览")
                        return
                        
                # 检查是否有camera_detection_running属性（在进程模式下）
                if hasattr(detection_manager, 'camera_detection_running'):
                    if not detection_manager.camera_detection_running:
                        # 检测已停止，但保持摄像头预览
                        self.state_label.setText("当前状态: 摄像头预览中（未检测）")
                        self.statusBar().showMessage("检测已停止，保持摄像头预览")
                        return
                
                # 如果检测仍在运行，500ms后再次检查
                QTimer.singleShot(500, check_detection_status)
            
            # 开始定期检查
            QTimer.singleShot(1000, check_detection_status)  # 从1秒后开始检查
    
    def on_alarm(self, alarm_info):
        """处理报警信息，使用信号槽机制确保线程安全"""
        print(f"[调试] 进入on_alarm方法，线程: {threading.current_thread().name}")
        print(f"[调试] 报警信息: {alarm_info}")
        
        # 发射信号到主线程
        self.alarm_signal.emit(alarm_info)
        
    @pyqtSlot(dict)
    def _safe_show_alarm_dialog(self, alarm_info):
        """线程安全地显示报警对话框"""
        print(f"[调试] 进入_safe_show_alarm_dialog方法，线程: {threading.current_thread().name}")
        
        # 设置状态栏消息
        self.statusBar().showMessage("检测到异物！请立即处理！")
        
        # 导入必要的组件
        from PyQt5.QtWidgets import QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QGroupBox
        from PyQt5.QtGui import QFont, QColor, QPalette
        import datetime
        
        # 获取报警时间
        current_time = alarm_info.get('timestamp', datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        # 创建自定义报警对话框
        alarm_dialog = QDialog(self)
        alarm_dialog.setWindowTitle("⚠️ 异物检测报警 ⚠️")
        # 增加对话框尺寸以确保文字完整显示
        alarm_dialog.setFixedSize(550, 400)
        alarm_dialog.setWindowModality(Qt.ApplicationModal)
        
        # 设置对话框背景颜色
        palette = alarm_dialog.palette()
        palette.setColor(QPalette.Window, QColor(255, 250, 240))  # 淡奶油色作为背景
        alarm_dialog.setPalette(palette)
        
        # 设置布局
        main_layout = QVBoxLayout(alarm_dialog)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)
        
        # 添加标题
        title_label = QLabel("⚠️ 检测到异物 ⚠️")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #E53935; background-color: #FFEBEE; padding: 8px; border-radius: 5px;")
        main_layout.addWidget(title_label)
        
        # 创建信息分组框
        info_group = QGroupBox("报警详细信息")
        info_group.setFont(QFont("Arial", 11, QFont.Bold))
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(10)
        
        # 报警信息 - 兼容不同的字段名格式
        time_label = QLabel(f"<b>报警时间：</b>{current_time}")
        position = alarm_info.get('position', alarm_info.get('location', '未知'))
        object_type = alarm_info.get('object_type', alarm_info.get('type', '未知'))
        detail = alarm_info.get('detail', '')
        
        position_label = QLabel(f"<b>位置：</b>{position}")
        object_label = QLabel(f"<b>异物种类：</b>{object_type}")
        
        # 设置字体大小和对齐方式
        font = QFont("Arial", 10)
        time_label.setFont(font)
        position_label.setFont(font)
        object_label.setFont(font)
        
        # 设置标签样式，允许自动换行
        time_label.setAlignment(Qt.AlignLeft)
        position_label.setAlignment(Qt.AlignLeft)
        object_label.setAlignment(Qt.AlignLeft)
        time_label.setWordWrap(True)
        position_label.setWordWrap(True)
        object_label.setWordWrap(True)
        
        # 添加到信息布局
        info_layout.addWidget(time_label)
        info_layout.addWidget(position_label)
        info_layout.addWidget(object_label)
        
        # 如果有详细信息，也显示出来
        if detail:
            detail_label = QLabel(f"<b>详细信息：</b>{detail}")
            detail_label.setFont(font)
            detail_label.setAlignment(Qt.AlignLeft)
            detail_label.setWordWrap(True)  # 允许详细信息自动换行
            info_layout.addWidget(detail_label)
        
        # 添加信息分组框到主布局
        main_layout.addWidget(info_group)
        
        # 添加提示信息，增加字间距和允许换行
        warning_label = QLabel("🚨 请立即检查屏蔽门间隙，确保安全！ 🚨")
        warning_label.setAlignment(Qt.AlignCenter)
        warning_label.setWordWrap(True)  # 允许警告文本自动换行
        warning_label.setStyleSheet("color: #E53935; font-size: 12px; font-weight: bold; background-color: #FFEBEE; padding: 10px; border-radius: 5px; letter-spacing: 0.5px;")
        main_layout.addWidget(warning_label)
        
        # 添加确认按钮布局
        button_layout = QHBoxLayout()
        confirm_button = QPushButton("确认")
        confirm_button.setFont(QFont("Arial", 12, QFont.Bold))
        confirm_button.setStyleSheet("background-color: #4CAF50; color: white; padding: 10px 20px; border-radius: 5px;")
        confirm_button.setMinimumWidth(120)  # 增加按钮宽度
        confirm_button.clicked.connect(alarm_dialog.accept)
        
        # 添加空间让按钮居中
        button_layout.addStretch(1)
        button_layout.addWidget(confirm_button)
        button_layout.addStretch(1)
        
        main_layout.addLayout(button_layout)
        
        # 显示对话框
        print(f"[调试] 显示报警对话框")
        alarm_dialog.exec_()
        print(f"[调试] 对话框已关闭")
        
        # 同时更新结果文本
        message = f"检测到异物！\n时间: {current_time}\n位置: {position}\n种类: {object_type}\n{detail}"
        self.result_text.append(message)
    
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
            
    def on_reset_system(self):
        """重置系统到空闲状态"""
        # 停止检测
        self.stop_detection()
        # 通过信号处理器重置状态
        signal_handler.reset_to_idle()
        # 更新UI显示
        self.state_label.setText("当前状态: 空闲")
        self.statusBar().showMessage("系统已重置")
    
    def on_new_frame(self, frame):
        """处理新的视频帧，将其发送给检测模块进行处理"""
        # 保存帧到缓存
        self.last_frame = frame
        
        # 检查是否在实际检测模式下：
        # 1. 首先检查是否有活跃的检测线程
        # 2. 如果没有，检查是否有camera_detection_running属性（进程模式）
        is_detection_active = False
        
        # 线程模式检查
        if hasattr(detection_manager, '_detection_thread') and detection_manager._detection_thread.is_alive():
            is_detection_active = True
        # 进程模式检查
        elif hasattr(detection_manager, 'camera_detection_running') and detection_manager.camera_detection_running:
            is_detection_active = True
        
        # 如果检测处于活跃状态，才发送帧进行处理
        if is_detection_active:
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
            input_x1 = int(self.roi_x1_input.currentText())
            input_y1 = int(self.roi_y1_input.currentText())
            input_x2 = int(self.roi_x2_input.currentText())
            input_y2 = int(self.roi_y2_input.currentText())
            
            # 确保坐标有效且完全在画面内部
            img_width, img_height = 1280, 720  # 假设默认分辨率
            
            # 先检查坐标顺序是否正确
            if input_x1 >= input_x2 or input_y1 >= input_y2:
                QMessageBox.warning(self, "警告", "ROI坐标无效，请确保X1<X2且Y1<Y2")
                return
            
            # 强制将坐标限制在画面内部，无论用户输入什么值
            x1 = max(0, min(input_x1, img_width - 25))  # 确保有最小宽度
            y1 = max(0, min(input_y1, img_height - 25))  # 确保有最小高度
            x2 = max(x1 + 25, min(input_x2, img_width))  # 确保有最小宽度且不超出边界
            y2 = max(y1 + 25, min(input_y2, img_height))  # 确保有最小高度且不超出边界
            
            # 如果输入的坐标被调整了，显示提示并更新输入框
            if (input_x1 != x1 or input_y1 != y1 or input_x2 != x2 or input_y2 != y2):
                # 只在真正被调整时更新输入框，避免不必要的循环调用
                self.roi_x1_input.setCurrentText(str(x1))
                self.roi_y1_input.setCurrentText(str(y1))
                self.roi_x2_input.setCurrentText(str(x2))
                self.roi_y2_input.setCurrentText(str(y2))
            
            # 更新ROI坐标（使用[x1, y1, x2, y2]格式）
            self.roi_coords = [x1, y1, x2, y2]
            # 更新ROI起始坐标，确保拖拽功能正常工作
            self.roi_start_coords = self.roi_coords.copy()
            
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
        # 检查摄像头是否运行
        if not video_capturer.is_running():
            # 如果摄像头没有运行，尝试启动预览
            if not self.start_camera_preview():
                # 如果启动失败，显示警告
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
            
            # 确保ROI完全在画面内部
            img_width, img_height = 1280, 720  # 假设默认分辨率
            x1, y1, x2, y2 = self.roi_coords
            
            # 调整坐标到画面内部
            x1 = max(0, x1)
            y1 = max(0, y1)
            x2 = min(img_width, x2)
            y2 = min(img_height, y2)
            
            # 确保调整后的坐标仍然有效
            if x1 >= x2:
                x2 = x1 + 25
            if y1 >= y2:
                y2 = y1 + 25
            
            # 更新输入框中的值
            self.roi_coords = [x1, y1, x2, y2]
            
            # 找到最接近的选项（步长25）
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