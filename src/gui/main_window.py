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
from PyQt5.QtGui import QImage, QPixmap, QFont, QPalette, QColor

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
        
        # 设置扁平化现代风格
        self.setStyleSheet("""
            /* 基础容器样式 */
            QMainWindow, QWidget {
                background-color: #f5f5f5;
                color: #333;
                font-family: 'Segoe UI', 'Arial', sans-serif;
                font-size: 14px;
            }
            
            /* 状态栏样式 */
            QStatusBar {
                background-color: #ffffff;
                color: #333;
                font-size: 13px;
                border-top: 1px solid #e0e0e0;
                padding: 4px 10px;
            }
            
            /* 分组框样式 */
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 20px;
                padding-bottom: 15px;
            }
            
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 15px;
                padding: 0 8px 0 8px;
                background-color: transparent;
                color: #333;
                font-weight: bold;
                font-size: 14px;
            }
            
            /* 按钮基础样式 */
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px 16px;
                border-radius: 4px;
                font-weight: normal;
                font-size: 14px;
                min-height: 32px;
            }
            
            QPushButton:hover {
                background-color: #1976D2;
            }
            
            QPushButton:pressed {
                background-color: #1565C0;
            }
            
            QPushButton:disabled {
                background-color: #e0e0e0;
                color: #9e9e9e;
            }
            
            /* 滑块样式 */
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
                margin: 6px 0;
            }
            
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                background: #2196F3;
                border-radius: 50%;
                margin: -5px 0;
            }
            
            QSlider::handle:horizontal:hover {
                background: #1976D2;
            }
            
            QSlider::handle:horizontal:pressed {
                background: #1565C0;
            }
            
            /* 下拉列表基础样式 */
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 6px;
                selection-background-color: #2196F3;
                selection-color: white;
                min-height: 32px;
                font-size: 14px;
            }
            
            QComboBox::drop-down {
                border: none;
                background-color: transparent;
                width: 25px;
            }
            
            QComboBox::down-arrow {
                image: url(:/icons/down-arrow.png);
                width: 10px;
                height: 10px;
                padding-right: 5px;
            }
            
            QComboBox:hover {
                border-color: #90CAF9;
            }
            
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px;
                selection-background-color: #2196F3;
                selection-color: white;
                font-size: 14px;
            }
            
            /* 复选框基础样式 */
            QCheckBox {
                spacing: 8px;
                color: #333;
                font-size: 14px;
                height: 24px;
            }
            
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border: 2px solid #e0e0e0;
                border-radius: 4px;
                background-color: white;
            }
            
            QCheckBox::indicator:hover {
                border-color: #90CAF9;
            }
            
            QCheckBox::indicator:checked {
                background-color: #2196F3;
                border-color: #2196F3;
                image: url(:/icons/check-mark.png);
            }
            
            QCheckBox::indicator:checked:hover {
                background-color: #1976D2;
                border-color: #1976D2;
            }
            
            /* 文本编辑框样式 */
            QTextEdit {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 10px;
                color: #333;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 13px;
                line-height: 1.5;
            }
            
            QTextEdit:focus {
                border-color: #2196F3;
                background-color: #ffffff;
            }
            
            /* 标签样式 */
            QLabel {
                color: #424242;
                font-size: 14px;
            }
            
            /* 分割器样式 */
            QSplitter::handle {
                background-color: #e0e0e0;
                width: 3px;
                height: 3px;
            }
            
            QSplitter::handle:hover {
                background-color: #bdbdbd;
            }
            
            /* 提示标签样式 */
            .hint-label {
                color: #757575;
                font-size: 12px;
                font-style: italic;
            }
        """)
        
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 主布局
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background-color: #e0e0e0; border-radius: 2px; }")
        
        # 左侧控制面板
        control_panel = self.create_control_panel()
        splitter.addWidget(control_panel)
        
        # 右侧显示区域
        display_area = self.create_display_area()
        splitter.addWidget(display_area)
        
        # 设置分割器比例
        splitter.setSizes([350, 830])
        
        main_layout.addWidget(splitter)
        
        # 底部状态栏
        self.statusBar().showMessage("系统就绪")
        self.statusBar().setStyleSheet("QStatusBar { background-color: #ffffff; border-top: 1px solid #e0e0e0; }")
    
    def create_control_panel(self):
        """创建控制面板"""
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # 摄像头控制组
        camera_group = QGroupBox("摄像头控制")
        camera_layout = QVBoxLayout()
        camera_layout.setContentsMargins(10, 5, 10, 10)
        camera_layout.setSpacing(10)
        
        self.camera_preview_button = QPushButton("开启摄像头预览")
        self.camera_preview_button.setStyleSheet("""
            QPushButton {
                background-color: #0097A7;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #00796B;
            }
            QPushButton:pressed {
                background-color: #00695C;
            }
        """)
        
        camera_layout.addWidget(self.camera_preview_button)
        camera_group.setLayout(camera_layout)
        
        # 信号控制组（作为唯一的控制方式，整合所有控制功能）
        signal_group = QGroupBox("信号控制")
        signal_layout = QVBoxLayout()
        signal_layout.setContentsMargins(10, 5, 10, 10)
        signal_layout.setSpacing(10)
        
        self.close_command_button = QPushButton("关门命令")
        self.close_command_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:pressed {
                background-color: #2E7D32;
            }
        """)
        
        self.closed_command_button = QPushButton("已关闭命令")
        self.closed_command_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        
        self.reset_button = QPushButton("重置系统")
        self.reset_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: white;
                border: none;
                padding: 10px;
                border-radius: 4px;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #F57C00;
            }
            QPushButton:pressed {
                background-color: #EF6C00;
            }
        """)
        
        signal_layout.addWidget(self.close_command_button)
        signal_layout.addWidget(self.closed_command_button)
        signal_layout.addWidget(self.reset_button)
        signal_group.setLayout(signal_layout)
        
        # 检测参数组
        param_group = QGroupBox("检测参数")
        param_layout = QGridLayout()
        param_layout.setContentsMargins(10, 5, 10, 10)
        param_layout.setSpacing(10)
        param_layout.setColumnStretch(0, 1)
        param_layout.setColumnStretch(1, 3)
        param_layout.setColumnStretch(2, 1)
        
        # 模型选择
        param_layout.addWidget(QLabel("检测模型:"), 0, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.model_combo = QComboBox()
        # 预定义的YOLOv5模型选项
        self.available_models = [
            "yolov5n.pt",  # 最小最快的模型
            "yolov5s.pt",  # 小型轻量模型
            "yolov5m.pt",  # 中型模型
            "yolov5l.pt",  # 大型模型
            "yolov5x.pt"   # 超大模型
        ]
        # 添加自定义模型选项（支持用户通过文件对话框选择）
        self.model_combo.addItems(self.available_models)
        self.model_combo.addItem("自定义...")
        
        # 设置模型选择下拉列表样式
        self.model_combo.setStyleSheet("""
            QComboBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 6px;
                selection-background-color: #2196F3;
                selection-color: white;
                min-height: 30px;
            }
            QComboBox::drop-down {
                border: none;
                background-color: transparent;
                width: 25px;
            }
            QComboBox::down-arrow {
                image: url(:/icons/down-arrow.png);
                width: 10px;
                height: 10px;
                padding-right: 5px;
            }
            QComboBox:hover {
                border-color: #90CAF9;
            }
            QComboBox QAbstractItemView {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 4px;
                selection-background-color: #2196F3;
                selection-color: white;
            }
        """)
        # 获取当前使用的模型
        current_model = detection_manager.weights_path.split(os.path.sep)[-1] if hasattr(detection_manager, 'weights_path') else "yolov5s.pt"
        # 尝试找到当前模型在下拉列表中的索引，如果找不到则默认选择yolov5s.pt
        try:
            model_index = self.available_models.index(current_model)
            self.model_combo.setCurrentIndex(model_index)
        except ValueError:
            # 如果是自定义模型，显示在下拉框中
            if current_model not in self.available_models:
                self.model_combo.addItem(current_model)
                self.model_combo.setCurrentText(current_model)
        param_layout.addWidget(self.model_combo, 0, 1, 1, 2)
        
        # 置信度阈值
        param_layout.addWidget(QLabel("置信度阈值:"), 1, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(10, 90)
        self.confidence_slider.setValue(50)
        self.confidence_value = QLabel("50%")
        self.confidence_value.setAlignment(Qt.AlignCenter)
        param_layout.addWidget(self.confidence_slider, 1, 1)
        param_layout.addWidget(self.confidence_value, 1, 2)
        
        # 多帧验证开关
        self.frame_validation_checkbox = QCheckBox("启用多帧验证")
        # 从detection_manager获取当前设置
        self.frame_validation_checkbox.setChecked(detection_manager.get_enable_frame_validation())
        param_layout.addWidget(self.frame_validation_checkbox, 2, 0, 1, 3)
        
        # 连续帧数
        param_layout.addWidget(QLabel("连续帧数:"), 3, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.frame_count_slider = QSlider(Qt.Horizontal)
        self.frame_count_slider.setRange(1, 5)
        # 设置滑块样式为扁平化现代风格
        self.frame_count_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 8px;
                background: #e0e0e0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 18px;
                height: 18px;
                background: #2196F3;
                border-radius: 50%;
                margin: -5px 0;
            }
            QSlider::handle:horizontal:hover {
                background: #1976D2;
            }
            QSlider::handle:horizontal:pressed {
                background: #1565C0;
            }
        """)
        
        self.frame_count_slider.setValue(2)
        self.frame_count_value = QLabel("2")
        self.frame_count_value.setAlignment(Qt.AlignCenter)
        self.frame_count_value.setStyleSheet("""
            QLabel {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 2px 8px;
                min-width: 30px;
            }
        """)
        param_layout.addWidget(self.frame_count_slider, 3, 1)
        param_layout.addWidget(self.frame_count_value, 3, 2)
        
        param_group.setLayout(param_layout)
        
        # 添加到主布局
        layout.addWidget(camera_group)
        layout.addWidget(signal_group)
        layout.addWidget(param_group)
        layout.addStretch()
        
        return panel
    
    def create_display_area(self):
        """创建显示区域"""
        area = QWidget()
        layout = QVBoxLayout(area)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 创建视频显示容器
        video_container = QGroupBox("视频显示")
        video_container.setStyleSheet("""
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 20px;
                padding-bottom: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: transparent;
                color: #333;
                font-weight: bold;
            }
        """)
        video_layout = QVBoxLayout(video_container)
        video_layout.setContentsMargins(15, 5, 15, 15)
        
        # 视频显示
        self.video_label = QLabel("视频显示区域")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(640, 480)
        self.video_label.setStyleSheet("""
            QLabel {
                background-color: #000000;
                color: #ffffff;
                border-radius: 4px;
                font-size: 16px;
            }
        """)
        
        # 为视频标签添加鼠标事件
        self.video_label.mousePressEvent = self.on_video_label_mouse_press
        self.video_label.mouseMoveEvent = self.on_video_label_mouse_move
        self.video_label.mouseReleaseEvent = self.on_video_label_mouse_release
        
        video_layout.addWidget(self.video_label)
        layout.addWidget(video_container)
        
        # 创建底部信息区域
        bottom_info_layout = QVBoxLayout()
        bottom_info_layout.setSpacing(15)
        
        # 创建一个水平布局来放置ROI设置和系统状态
        bottom_horizontal_layout = QHBoxLayout()
        bottom_horizontal_layout.setSpacing(15)
        
        # 设置统一的下拉列表样式函数
        def setup_combobox_style(combo):
            combo.setStyleSheet("""
                QComboBox {
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    padding: 6px;
                    selection-background-color: #2196F3;
                    selection-color: white;
                    min-height: 30px;
                }
                QComboBox::drop-down {
                    border: none;
                    background-color: transparent;
                    width: 25px;
                }
                QComboBox::down-arrow {
                    image: url(:/icons/down-arrow.png);
                    width: 10px;
                    height: 10px;
                    padding-right: 5px;
                }
                QComboBox:hover {
                    border-color: #90CAF9;
                }
                QComboBox QAbstractItemView {
                    background-color: #ffffff;
                    border: 1px solid #e0e0e0;
                    border-radius: 4px;
                    padding: 4px;
                    selection-background-color: #2196F3;
                    selection-color: white;
                }
            """)
        
        # ROI设置组
        roi_group = QGroupBox("ROI设置")
        roi_layout = QGridLayout()
        roi_layout.setContentsMargins(10, 5, 10, 10)
        
        # ROI设置组样式
        roi_group.setStyleSheet("""
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 20px;
                padding-bottom: 15px;
                min-width: 400px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: transparent;
                color: #333;
                font-weight: bold;
            }
        """)
        
        roi_layout.setSpacing(10)
        roi_layout.setColumnStretch(0, 1)
        roi_layout.setColumnStretch(1, 1)
        roi_layout.setColumnStretch(2, 1)
        roi_layout.setColumnStretch(3, 1)
        
        # ROI启用复选框
        self.roi_enable_checkbox = QCheckBox("启用ROI")
        self.roi_enable_checkbox.setChecked(True)  # 默认启用ROI
        roi_layout.addWidget(self.roi_enable_checkbox, 0, 0, 1, 4)
        
        # 设置复选框样式
        self.roi_enable_checkbox.setStyleSheet("""
            QCheckBox {
                color: #424242;
                font-size: 14px;
            }
        """)
        
        # ROI坐标输入
        roi_layout.addWidget(QLabel("X1:"), 1, 0, Qt.AlignRight)
        self.roi_x1_input = QComboBox()
        for i in range(0, 1280, 25):
            self.roi_x1_input.addItem(str(i))
        self.roi_x1_input.setCurrentText(str(self.roi_coords[0]))
        setup_combobox_style(self.roi_x1_input)
        roi_layout.addWidget(self.roi_x1_input, 1, 1)
        
        roi_layout.addWidget(QLabel("Y1:"), 1, 2, Qt.AlignRight)
        self.roi_y1_input = QComboBox()
        for i in range(0, 720, 25):
            self.roi_y1_input.addItem(str(i))
        self.roi_y1_input.setCurrentText(str(self.roi_coords[1]))
        setup_combobox_style(self.roi_y1_input)
        roi_layout.addWidget(self.roi_y1_input, 1, 3)
        
        roi_layout.addWidget(QLabel("X2:"), 2, 0, Qt.AlignRight)
        self.roi_x2_input = QComboBox()
        for i in range(0, 1280, 25):
            self.roi_x2_input.addItem(str(i))
        self.roi_x2_input.setCurrentText(str(self.roi_coords[2]))
        setup_combobox_style(self.roi_x2_input)
        roi_layout.addWidget(self.roi_x2_input, 2, 1)
        
        roi_layout.addWidget(QLabel("Y2:"), 2, 2, Qt.AlignRight)
        self.roi_y2_input = QComboBox()
        for i in range(0, 720, 25):
            self.roi_y2_input.addItem(str(i))
        self.roi_y2_input.setCurrentText(str(self.roi_coords[3]))
        setup_combobox_style(self.roi_y2_input)
        roi_layout.addWidget(self.roi_y2_input, 2, 3)
        
        # ROI编辑按钮
        self.roi_edit_button = QPushButton("进入ROI编辑模式")
        self.roi_edit_button.setStyleSheet("""
            QPushButton {
                background-color: #673AB7;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #512DA8;
            }
            QPushButton:pressed {
                background-color: #4527A0;
            }
        """)
        roi_layout.addWidget(self.roi_edit_button, 3, 0, 1, 2)
        
        # 应用ROI按钮
        self.apply_roi_button = QPushButton("应用ROI设置")
        self.apply_roi_button.setStyleSheet("""
            QPushButton {
                background-color: #00BCD4;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0097A7;
            }
            QPushButton:pressed {
                background-color: #00838F;
            }
        """)
        roi_layout.addWidget(self.apply_roi_button, 3, 2, 1, 2)
        
        roi_group.setLayout(roi_layout)
        
        # 系统状态组
        status_group = QGroupBox("系统状态")
        status_layout = QVBoxLayout()
        status_layout.setContentsMargins(10, 5, 10, 10)
        status_layout.setSpacing(10)
        
        # 系统状态组样式
        status_group.setStyleSheet("""
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 20px;
                padding-bottom: 15px;
                min-width: 400px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 10px;
                padding: 0 5px 0 5px;
                background-color: transparent;
                color: #333;
                font-weight: bold;
            }
        """)
        
        self.state_label = QLabel("当前状态: 空闲")
        self.state_label.setStyleSheet("font-weight: bold; color: #424242;")
        status_layout.addWidget(self.state_label)
        
        # 检测结果显示
        status_layout.addWidget(QLabel("检测结果:"))
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setFixedHeight(100)
        self.result_text.setStyleSheet("""
            QTextEdit {
                background-color: #fafafa;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 8px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
            }
        """)
        status_layout.addWidget(self.result_text)
        
        status_group.setLayout(status_layout)
        
        # 添加ROI设置和系统状态到水平布局
        bottom_horizontal_layout.addWidget(roi_group)
        bottom_horizontal_layout.addWidget(status_group)
        bottom_info_layout.addLayout(bottom_horizontal_layout)
        
        # 将底部信息区域添加到主布局
        layout.addLayout(bottom_info_layout)
        layout.addStretch()
        
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
        
        # 设置模型选择信号连接
        self.model_combo.currentIndexChanged.connect(self.on_model_selection_changed)
    
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
        
        # 设置对话框扁平化样式
        alarm_dialog.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
        """)
        
        # 设置布局
        main_layout = QVBoxLayout(alarm_dialog)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(25, 25, 25, 20)
        
        # 添加标题
        title_label = QLabel("⚠️ 检测到异物 ⚠️")
        title_label.setFont(QFont("Arial", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #F44336;
                padding: 12px;
                border-radius: 6px;
            }
        """)
        main_layout.addWidget(title_label)
        
        # 创建信息分组框
        info_group = QGroupBox("报警详细信息")
        info_group.setStyleSheet("""
            QGroupBox {
                background-color: #ffffff;
                border: 1px solid #e0e0e0;
                border-radius: 6px;
                margin-top: 5px;
                padding-top: 15px;
                padding-bottom: 5px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
                color: #333;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        info_layout = QVBoxLayout(info_group)
        info_layout.setSpacing(12)
        info_layout.setContentsMargins(15, 5, 15, 15)
        
        # 报警信息 - 兼容不同的字段名格式
        time_label = QLabel(f"<b>报警时间：</b>{current_time}")
        position = alarm_info.get('position', alarm_info.get('location', '未知'))
        object_type = alarm_info.get('object_type', alarm_info.get('type', '未知'))
        detail = alarm_info.get('detail', '')
        
        position_label = QLabel(f"<b>位置：</b>{position}")
        object_label = QLabel(f"<b>异物种类：</b>{object_type}")
        
        # 设置字体大小和对齐方式
        font = QFont("Arial", 12)
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
        warning_label.setStyleSheet("""
            QLabel {
                color: #ffffff;
                background-color: #FF5722;
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
                letter-spacing: 0.5px;
            }
        """)
        main_layout.addWidget(warning_label)
        
        # 添加确认按钮布局
        button_layout = QHBoxLayout()
        confirm_button = QPushButton("确认")
        confirm_button.setFont(QFont("Arial", 14, QFont.Bold))
        confirm_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 4px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #388E3C;
            }
            QPushButton:pressed {
                background-color: #2E7D32;
            }
        """)
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
    
    def on_model_selection_changed(self, index):
        """处理模型选择变更"""
        model_name = self.model_combo.currentText()
        
        # 如果选择的是"自定义...", 打开文件对话框
        if model_name == "自定义...":
            from PyQt5.QtWidgets import QFileDialog
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择模型文件",
                "",
                "PyTorch 模型 (*.pt);;所有文件 (*)"
            )
            
            if file_path:
                # 获取文件名
                custom_model_name = os.path.basename(file_path)
                # 检查是否已存在于下拉列表中
                if custom_model_name not in [self.model_combo.itemText(i) for i in range(self.model_combo.count())]:
                    # 移除"自定义..."临时选项
                    self.model_combo.removeItem(self.model_combo.findText("自定义..."))
                    # 添加自定义模型
                    self.model_combo.addItem(custom_model_name)
                    # 重新添加"自定义..."选项
                    self.model_combo.addItem("自定义...")
                # 设置当前选择为自定义模型
                self.model_combo.setCurrentText(custom_model_name)
                # 使用完整路径
                model_path = file_path
            else:
                # 如果取消选择，保持原来的模型
                return
        else:
            # 对于预定义模型，使用模型名
            model_path = model_name
        
        # 尝试切换模型
        self.switch_detection_model(model_path)
        
    def switch_detection_model(self, model_path):
        """切换检测模型
        
        Args:
            model_path: 模型路径或模型名称
        """
        # 显示加载状态
        model_name = os.path.basename(model_path)
        self.statusBar().showMessage(f"正在加载模型: {model_name}...")
        log_manager.log_system_event("模型切换", f"开始切换到模型: {model_path}")
        
        try:
            # 保存当前检测状态
            was_running = detection_manager.camera_detection_running
            
            # 停止当前检测进程
            if was_running:
                log_manager.log_system_event("模型切换", "停止当前检测进程")
                detection_manager.stop_camera_detection()
            
            # 更新配置
            log_manager.log_system_event("模型切换", f"更新配置中的模型路径为: {model_path}")
            config_manager.set("detection.weights", model_path)
            config_manager.save_config()
            
            # 切换模型
            log_manager.log_system_event("模型切换", "开始执行模型切换")
            if detection_manager.switch_model(model_path):
                success_msg = f"模型切换成功: {model_name}"
                self.statusBar().showMessage(success_msg)
                log_manager.log_system_event("模型切换", success_msg)
                # 如果之前检测在运行，重启检测
                if was_running:
                    log_manager.log_system_event("模型切换", "重启检测进程")
                    detection_manager.start_camera_detection()
            else:
                error_msg = f"模型切换失败: {model_name}"
                self.statusBar().showMessage(error_msg)
                log_manager.log_error(error_msg)
                QMessageBox.critical(self, "错误", f"模型切换失败:\n可能是模型文件不存在或格式不正确")
        except Exception as e:
            error_msg = f"模型切换异常: {str(e)}"
            self.statusBar().showMessage(error_msg)
            log_manager.log_error(f"模型切换异常: {str(e)}")
            log_manager.log_error(traceback.format_exc())
            QMessageBox.critical(self, "错误", f"模型切换失败:\n{str(e)}")
        
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 创建自定义消息框
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle('确认退出')
        msg_box.setText('确定要退出系统吗？')
        msg_box.setIcon(QMessageBox.Question)
        
        # 添加按钮
        yes_button = msg_box.addButton("是", QMessageBox.YesRole)
        no_button = msg_box.addButton("否", QMessageBox.NoRole)
        msg_box.setDefaultButton(no_button)
        
        # 设置扁平化样式
        msg_box.setStyleSheet("""
            QMessageBox {
                background-color: #f5f5f5;
                border-radius: 8px;
                border: 1px solid #e0e0e0;
            }
            QLabel {
                color: #333;
                font-size: 14px;
            }
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 14px;
                font-weight: normal;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        
        msg_box.exec_()
        
        if msg_box.clickedButton() == yes_button:
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