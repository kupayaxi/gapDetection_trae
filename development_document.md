# 地铁屏蔽门间隙检测系统开发文档

## 1. 项目概述

### 1.1 项目背景
地铁屏蔽门间隙检测系统旨在通过计算机视觉技术自动检测地铁屏蔽门与列车之间的间隙中是否存在异物，以防止在关门过程中夹人夹物等安全事故的发生。该系统利用YOLOv5目标检测算法，结合视频流分析和信号交互，实现实时、准确的异物检测和报警功能。

### 1.2 系统功能
- 模拟/接收地铁屏蔽门的关门命令和已关闭信号
- 实时采集并分析屏蔽门视频流
- 在特定信号状态下对屏蔽门间隙区域进行异物检测
- 实现ROI（感兴趣区域）划定，仅检测屏蔽门间隙区域
- 采用连续多帧验证机制，降低误报率
- 实时显示检测结果和系统状态
- 当检测到异物时立即弹窗报警
- 记录详细的检测日志和报警信息

### 1.3 系统架构

```
地铁屏蔽门间隙检测系统
├─ 1. 信号交互模块：接收"关门命令"/"已关闭命令"（模拟+硬件接口）
├─ 2. 视频流采集模块：调用摄像头实时获取屏蔽门画面
├─ 3. 目标检测模块：YOLO V5预训练模型推理+ROI筛选
├─ 4. GUI交互模块：实时显示、报警弹窗、参数配置、日志记录
└─ 5. 日志存储模块：记录检测结果（时间、异物类型、位置、信号状态）
```

## 2. 技术栈

- **编程语言**：Python 3.8+
- **GUI框架**：PyQt5
- **目标检测**：YOLOv5
- **图像处理**：OpenCV
- **深度学习框架**：PyTorch
- **数据存储**：SQLite（轻量级）或MySQL（企业级）
- **视频采集**：OpenCV VideoCapture或PySpin（工业相机）

## 3. 详细模块设计

### 3.1 信号交互模块

#### 3.1.1 功能描述
- 提供软件模拟的关门命令和已关闭信号按钮
- 预留硬件接口，支持实际地铁信号系统的信号接入
- 维护系统当前的信号状态
- 向其他模块广播信号状态变化

#### 3.1.2 类设计
```python
class SignalManager:
    # 信号状态枚举
    class SignalState:
        IDLE = 0          # 空闲状态
        CLOSING = 1       # 关门过程中
        CLOSED = 2        # 已关闭状态
    
    def __init__(self):
        self.current_state = self.SignalState.IDLE
        self.signal_callbacks = []
    
    def register_callback(self, callback):
        """注册信号状态变化的回调函数"""
    
    def set_closing_signal(self):
        """设置关门信号"""
    
    def set_closed_signal(self):
        """设置已关闭信号"""
    
    def reset_signal(self):
        """重置信号状态"""
    
    def setup_hardware_interface(self, config):
        """配置硬件接口（预留）"""
```

### 3.2 视频流采集模块

#### 3.2.1 功能描述
- 支持多种视频源（USB摄像头、IP摄像头、视频文件等）
- 实时获取视频帧
- 提供视频源配置功能
- 支持视频流的启停控制

#### 3.2.2 类设计
```python
class VideoCaptureManager:
    def __init__(self):
        self.video_source = None
        self.capture = None
        self.running = False
        self.frame_callbacks = []
    
    def initialize(self, source=0):  # 0为默认摄像头
        """初始化视频源"""
    
    def start(self):
        """开始采集视频"""
    
    def stop(self):
        """停止采集视频"""
    
    def register_frame_callback(self, callback):
        """注册帧处理回调函数"""
    
    def process_frame(self):
        """处理单帧图像"""
    
    def set_resolution(self, width, height):
        """设置视频分辨率"""
```

### 3.3 目标检测模块

#### 3.3.1 功能描述
- 加载YOLOv5预训练模型
- 筛选与地铁场景相关的COCO数据集类别
- 实现ROI划定和区域筛选
- 执行目标检测推理
- 实现连续多帧验证规则
- 输出检测结果

#### 3.3.2 关键参数
- **相关类别筛选**：根据地铁屏蔽门夹人夹物场景特点，筛选以下COCO类别（按优先级排序）：
  
  **1. 人体相关（最高优先级，直接关联"夹人"风险）**
  - person(0) - 核心类别，检测人体（包括被夹的手、胳膊、头等肢体部位）
  
  **2. 随身行李/大型物品（高优先级，易被夹在门间隙）**
  - backpack(24) - 背包（乘客常挂在肩上，易被门夹住）
  - umbrella(25) - 雨伞（长条形，易伸出屏蔽门外被夹）
  - handbag(26) - 手提包（乘客手持，易在关门时被夹）
  - suitcase(28) - 行李箱（轮式行李，易因拖拽不及时被夹）
  
  **3. 小型手持物品（中高优先级，易掉落或被夹）**
  - bottle(39) - 水瓶/饮料瓶（乘客手持，易滑落被夹）
  - cup(41) - 杯子/保温杯（类似瓶子，小型易夹）
  - cell phone(67) - 手机（乘客低头看手机时易伸出被夹）
  
  **4. 衣物/配饰（中优先级，易被门边缘勾住）**
  - tie(27) - 领带（乘客正装佩戴，易被门夹）
  
  **5. 其他可能被夹的物品（中低优先级）**
  - teddy bear(77) - 毛绒玩具（儿童携带，易被夹）
  
- **缺失类别说明**：COCO数据集中缺少以下地铁夹物场景的高风险项，会导致漏检：
  - 细小物品：鞋带、耳机线、充电线、纸张、名片、硬币、钥匙串
  - 衣物部件：围巾、帽子、手套、衣角、裤脚
  - 特殊物品：婴儿车部件、拐杖、折叠伞（收起状态）、购物袋提手
  
- **ROI区域**：通过GUI手动划定或配置文件预设
- **连续多帧验证**：默认连续2帧检测到同一异物判定为有效
- **检测阈值**：置信度阈值默认0.4（可配置）

#### 3.3.3 类设计
```python
class DetectionManager:
    def __init__(self, weights_path="yolov5s.pt"):
        self.model = None
        self.weights_path = weights_path
        # 地铁屏蔽门夹人夹物场景相关类别ID及对应名称（按优先级排序）
        self.relevant_classes = [0, 24, 25, 26, 28, 39, 41, 67, 27, 77]  # 相关类别ID
        self.class_names = {
            # 1. 人体相关（最高优先级）
            0: 'person',          # 核心类别，检测人体（包括被夹的手、胳膊、头等肢体部位）
            
            # 2. 随身行李/大型物品（高优先级）
            24: 'backpack',       # 背包（乘客常挂在肩上，易被门夹住）
            25: 'umbrella',       # 雨伞（长条形，易伸出屏蔽门外被夹）
            26: 'handbag',        # 手提包（乘客手持，易在关门时被夹）
            28: 'suitcase',       # 行李箱（轮式行李，易因拖拽不及时被夹）
            
            # 3. 小型手持物品（中高优先级）
            39: 'bottle',         # 水瓶/饮料瓶（乘客手持，易滑落被夹）
            41: 'cup',            # 杯子/保温杯（类似瓶子，小型易夹）
            67: 'cell phone',     # 手机（乘客低头看手机时易伸出被夹）
            
            # 4. 衣物/配饰（中优先级）
            27: 'tie',            # 领带（乘客正装佩戴，易被门夹）
            
            # 5. 其他可能被夹的物品（中低优先级）
            77: 'teddy bear'      # 毛绒玩具（儿童携带，易被夹）
        }
        self.roi = None  # ROI区域 [x1, y1, x2, y2]
        self.confidence_threshold = 0.4
        self.iou_threshold = 0.45
        self.max_det = 1000
        self.augment = False
        self.agnostic_nms = False
        self.frame_validation_count = 2  # 连续验证帧数
        self.detection_history = []  # 用于多帧验证
        self.detection_callbacks = []
    
    def load_model(self):
        """加载YOLOv5模型"""
    
    def set_roi(self, roi_coordinates):
        """设置ROI区域"""
    
    def is_in_roi(self, bbox):
        """检查检测框是否在ROI区域内"""
    
    def filter_relevant_classes(self, detections):
        """筛选相关类别的检测结果"""
    
    def apply_frame_validation(self, current_detections):
        """应用连续多帧验证规则"""
    
    def detect(self, frame):
        """执行目标检测"""
        # 调用YOLOv5的run函数进行检测
        # 传入所有可配置的参数
        
        # 处理检测结果并应用ROI筛选和多帧验证
        
        # 规则优化：
        # 1. 对person类的边界框进行二次判断：若边界框边缘与屏蔽门间隙重叠（结合ROI），
        #    判定为"肢体可能被夹"
        # 2. 对小尺寸目标（面积<50x50像素），即使不属于上述类别，也标记为"疑似细小异物"
        
        # 返回最终的检测结果
    
    def register_detection_callback(self, callback):
        """注册检测结果回调函数"""
```

### 3.4 GUI交互模块

#### 3.4.1 功能描述
- 实时显示视频流和检测结果
- 提供信号模拟按钮（关门命令、已关闭命令）
- 实现ROI区域的可视化划定功能
- 提供完整的参数配置界面，支持修改以下`detect.py`中的所有检测相关参数：
  - 模型路径（weights）：选择使用的YOLOv5模型权重文件
  - 置信度阈值（conf_thres）：设置检测目标的最低置信度
  - NMS IoU阈值（iou_thres）：设置非极大值抑制的IoU阈值
  - 最大检测数量（max_det）：设置每帧最大检测目标数
  - 检测相关类别（relevant_classes）：通过复选框选择需要检测的目标类别，已按优先级预筛选地铁夹人夹物场景相关类别
  - 连续多帧验证数量（frame_validation_count）：设置连续检测帧数要求
  - 是否使用图像增强（augment）：启用/禁用增强推理
  - 是否使用类别无关的NMS（agnostic_nms）：启用/禁用类别无关的非极大值抑制
  - 线框粗细（line_thickness）：设置绘制框的粗细
  - 是否显示置信度（show_confidence）：是否在检测框上显示置信度
  - 是否显示标签（show_labels）：是否在检测框上显示类别标签
- 弹出报警窗口显示检测到的异物信息
- 显示系统状态信息
- 实时日志记录和显示

#### 3.4.2 界面布局
```
+-------------------------------------------+
| 菜单栏（文件、设置、帮助）                |
+-------------------------------------------+
|                                           |
|                                           |
|          视频显示区域                      |
|                                           |
|                                           |
+-------------------------------------------+
|                                           |
| 信号状态: [空闲/关门中/已关闭]            |
|                                           |
+-------------------------------------------+
|                                           |
| [ 关门命令 ] [ 已关闭命令 ] [ 重置 ]      |
|                                           |
+-------------------------------------------+
|                                           |
| 日志显示区域                              |
|                                           |
+-------------------------------------------+
```

#### 3.4.3 类设计
```python
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signal_manager = SignalManager()
        self.video_manager = VideoCaptureManager()
        self.detection_manager = DetectionManager()
        self.log_manager = LogManager()
        self.init_ui()
        self.connect_signals()
    
    def init_ui(self):
        """初始化UI组件"""
        # 创建菜单栏
        self.create_menu_bar()
        # 创建中央视频显示区域
        self.create_video_display()
        # 创建信号控制按钮区域
        self.create_control_panel()
        # 创建状态显示区域
        self.create_status_panel()
        # 创建日志显示区域
        self.create_log_display()
    
    def create_menu_bar(self):
        """创建菜单栏，包含文件、设置、帮助等菜单"""
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        start_action = file_menu.addAction("开始检测")
        start_action.triggered.connect(self.start_system)
        stop_action = file_menu.addAction("停止检测")
        stop_action.triggered.connect(self.stop_system)
        file_menu.addSeparator()
        exit_action = file_menu.addAction("退出")
        exit_action.triggered.connect(self.close)
        
        # 设置菜单
        settings_menu = menu_bar.addMenu("设置")
        detection_settings_action = settings_menu.addAction("检测参数设置")
        detection_settings_action.triggered.connect(self.open_detection_settings_dialog)
        roi_settings_action = settings_menu.addAction("ROI区域设置")
        roi_settings_action.triggered.connect(self.open_roi_settings_dialog)
        ui_settings_action = settings_menu.addAction("界面设置")
        ui_settings_action.triggered.connect(self.open_ui_settings_dialog)
        
        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")
        about_action = help_menu.addAction("关于")
        about_action.triggered.connect(self.show_about_dialog)
    
    def create_video_display(self):
        """创建视频显示区域"""
    
    def create_control_panel(self):
        """创建信号控制按钮区域"""
    
    def create_status_panel(self):
        """创建状态显示区域"""
    
    def create_log_display(self):
        """创建日志显示区域"""
    
    def connect_signals(self):
        """连接各个模块的信号和槽"""
        # 连接视频帧回调
        self.video_manager.register_frame_callback(self.process_frame)
        # 连接信号状态变化回调
        self.signal_manager.register_callback(self.on_signal_state_change)
        # 连接检测结果回调
        self.detection_manager.register_detection_callback(self.on_detection_result)
    
    def start_system(self):
        """启动系统"""
        self.video_manager.start()
        self.log_manager.log_system_event("系统启动", "系统初始化完成")
    
    def stop_system(self):
        """停止系统"""
        self.video_manager.stop()
        self.log_manager.log_system_event("系统停止", "系统已停止运行")
    
    def on_closing_command(self):
        """处理关门命令按钮点击"""
        self.signal_manager.set_closing_signal()
    
    def on_closed_command(self):
        """处理已关闭命令按钮点击"""
        self.signal_manager.set_closed_signal()
    
    def on_reset(self):
        """处理重置按钮点击"""
        self.signal_manager.reset_signal()
    
    def process_frame(self, frame):
        """处理视频帧，进行检测并更新显示"""
        # 检查是否在关门过程中
        if self.signal_manager.current_state == self.signal_manager.SignalState.CLOSING:
            # 执行检测
            detection_result = self.detection_manager.detect(frame)
            # 在帧上绘制检测结果
            annotated_frame = self.annotate_frame(frame, detection_result)
        else:
            annotated_frame = frame
        # 更新显示
        self.update_video_display(annotated_frame)
    
    def annotate_frame(self, frame, detection_result):
        """在视频帧上绘制检测结果"""
    
    def update_video_display(self, frame):
        """更新视频显示"""
    
    def on_signal_state_change(self, old_state, new_state):
        """处理信号状态变化"""
        # 记录状态变化
        self.log_manager.log_signal_change(old_state, new_state)
        # 更新状态显示
        self.update_status_bar()
    
    def on_detection_result(self, detection_result):
        """处理检测结果"""
        if detection_result and len(detection_result) > 0:
            # 显示报警
            self.show_alarm(detection_result)
            # 记录检测结果
            for detection in detection_result:
                self.log_manager.log_detection(detection, self.signal_manager.current_state)
    
    def show_alarm(self, detection_result):
        """显示报警窗口"""
    
    def update_status_bar(self):
        """更新状态栏信息"""
    
    def draw_roi(self):
        """绘制ROI区域"""
    
    def open_detection_settings_dialog(self):
        """打开检测参数设置对话框"""
        dialog = DetectionSettingsDialog(self, self.detection_manager)
        if dialog.exec_():
            # 应用新的检测参数
            self.apply_detection_settings(dialog.get_settings())
    
    def open_roi_settings_dialog(self):
        """打开ROI区域设置对话框"""
    
    def open_ui_settings_dialog(self):
        """打开界面设置对话框"""
        dialog = UISettingsDialog(self)
        if dialog.exec_():
            # 应用新的界面参数
            self.apply_ui_settings(dialog.get_settings())
    
    def apply_detection_settings(self, settings):
        """应用检测参数设置"""
        # 更新检测管理器的参数
        if "weights" in settings:
            self.detection_manager.weights_path = settings["weights"]
            # 重新加载模型
            self.detection_manager.load_model()
        if "confidence_threshold" in settings:
            self.detection_manager.confidence_threshold = settings["confidence_threshold"]
        if "iou_threshold" in settings:
            self.detection_manager.iou_threshold = settings["iou_threshold"]
        if "max_det" in settings:
            self.detection_manager.max_det = settings["max_det"]
        if "relevant_classes" in settings:
            self.detection_manager.relevant_classes = settings["relevant_classes"]
        if "frame_validation_count" in settings:
            self.detection_manager.frame_validation_count = settings["frame_validation_count"]
        if "augment" in settings:
            self.detection_manager.augment = settings["augment"]
        if "agnostic_nms" in settings:
            self.detection_manager.agnostic_nms = settings["agnostic_nms"]
        
        # 记录设置更改
        self.log_manager.log_system_event("参数更新", f"检测参数已更新: {settings}")
    
    def apply_ui_settings(self, settings):
        """应用界面参数设置"""
        # 更新界面设置
        # 实际实现时，这些设置会影响显示效果、更新频率等
        
        # 记录设置更改
        self.log_manager.log_system_event("界面更新", f"界面参数已更新: {settings}")
    
    def show_about_dialog(self):
        """显示关于对话框"""

class DetectionSettingsDialog(QDialog):
    """检测参数设置对话框，用于配置所有与YOLOv5检测相关的参数"""
    def __init__(self, parent, detection_manager):
        super().__init__(parent)
        self.detection_manager = detection_manager
        self.setWindowTitle("检测参数设置")
        self.resize(500, 600)
        self.init_ui()
        self.load_current_settings()
    
    def init_ui(self):
        """初始化对话框UI"""
        layout = QVBoxLayout(self)
        
        # 创建标签页控件
        tab_widget = QTabWidget()
        
        # 创建基本参数标签页
        basic_tab = QWidget()
        basic_layout = QFormLayout(basic_tab)
        
        # 模型路径
        self.weights_edit = QLineEdit()
        weights_button = QPushButton("浏览...")
        weights_button.clicked.connect(self.browse_weights_file)
        weights_layout = QHBoxLayout()
        weights_layout.addWidget(self.weights_edit)
        weights_layout.addWidget(weights_button)
        basic_layout.addRow("模型路径:", weights_layout)
        
        # 置信度阈值
        self.conf_threshold_slider = QSlider(Qt.Horizontal)
        self.conf_threshold_slider.setRange(1, 100)
        self.conf_threshold_spinbox = QDoubleSpinBox()
        self.conf_threshold_spinbox.setRange(0.01, 1.0)
        self.conf_threshold_spinbox.setSingleStep(0.01)
        # 连接滑动条和数值框
        self.conf_threshold_slider.valueChanged.connect(
            lambda value: self.conf_threshold_spinbox.setValue(value / 100))
        self.conf_threshold_spinbox.valueChanged.connect(
            lambda value: self.conf_threshold_slider.setValue(int(value * 100)))
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(self.conf_threshold_slider)
        conf_layout.addWidget(self.conf_threshold_spinbox)
        basic_layout.addRow("置信度阈值:", conf_layout)
        
        # IOU阈值
        self.iou_threshold_slider = QSlider(Qt.Horizontal)
        self.iou_threshold_slider.setRange(1, 100)
        self.iou_threshold_spinbox = QDoubleSpinBox()
        self.iou_threshold_spinbox.setRange(0.01, 1.0)
        self.iou_threshold_spinbox.setSingleStep(0.01)
        # 连接滑动条和数值框
        self.iou_threshold_slider.valueChanged.connect(
            lambda value: self.iou_threshold_spinbox.setValue(value / 100))
        self.iou_threshold_spinbox.valueChanged.connect(
            lambda value: self.iou_threshold_slider.setValue(int(value * 100)))
        iou_layout = QHBoxLayout()
        iou_layout.addWidget(self.iou_threshold_slider)
        iou_layout.addWidget(self.iou_threshold_spinbox)
        basic_layout.addRow("IOU阈值:", iou_layout)
        
        # 最大检测数量
        self.max_det_spinbox = QSpinBox()
        self.max_det_spinbox.setRange(1, 10000)
        self.max_det_spinbox.setSingleStep(10)
        basic_layout.addRow("最大检测数量:", self.max_det_spinbox)
        
        # 连续多帧验证数量
        self.frame_validation_spinbox = QSpinBox()
        self.frame_validation_spinbox.setRange(1, 10)
        self.frame_validation_spinbox.setSingleStep(1)
        basic_layout.addRow("连续多帧验证数量:", self.frame_validation_spinbox)
        
        # 添加基本参数标签页
        tab_widget.addTab(basic_tab, "基本参数")
        
        # 创建高级参数标签页
        advanced_tab = QWidget()
        advanced_layout = QFormLayout(advanced_tab)
        
        # 图像增强
        self.augment_checkbox = QCheckBox()
        advanced_layout.addRow("使用图像增强:", self.augment_checkbox)
        
        # 类别无关NMS
        self.agnostic_nms_checkbox = QCheckBox()
        advanced_layout.addRow("使用类别无关NMS:", self.agnostic_nms_checkbox)
        
        # 添加高级参数标签页
        tab_widget.addTab(advanced_tab, "高级参数")
        
        # 创建类别选择标签页
        classes_tab = QWidget()
        classes_layout = QVBoxLayout(classes_tab)
        
        # 创建类别选择列表
        self.classes_group = QGroupBox("选择检测类别")
        classes_group_layout = QVBoxLayout(self.classes_group)
        self.class_checkboxes = {}
        
        # 创建滚动区域以容纳所有类别
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # 添加全选按钮
        select_all_button = QPushButton("全选")
        select_all_button.clicked.connect(self.select_all_classes)
        deselect_all_button = QPushButton("全不选")
        deselect_all_button.clicked.connect(self.deselect_all_classes)
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(select_all_button)
        buttons_layout.addWidget(deselect_all_button)
        scroll_layout.addLayout(buttons_layout)
        
        # 添加类别复选框
        for class_id, class_name in self.detection_manager.class_names.items():
            checkbox = QCheckBox(f"{class_id}: {class_name}")
            self.class_checkboxes[class_id] = checkbox
            scroll_layout.addWidget(checkbox)
        
        scroll_widget.setLayout(scroll_layout)
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        classes_group_layout.addWidget(scroll_area)
        classes_layout.addWidget(self.classes_group)
        
        # 添加类别选择标签页
        tab_widget.addTab(classes_tab, "类别选择")
        
        # 添加标签页控件到主布局
        layout.addWidget(tab_widget)
        
        # 创建按钮框
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def load_current_settings(self):
        """加载当前设置到对话框"""
        # 加载基本参数
        self.weights_edit.setText(self.detection_manager.weights_path)
        self.conf_threshold_slider.setValue(int(self.detection_manager.confidence_threshold * 100))
        self.conf_threshold_spinbox.setValue(self.detection_manager.confidence_threshold)
        self.iou_threshold_slider.setValue(int(self.detection_manager.iou_threshold * 100))
        self.iou_threshold_spinbox.setValue(self.detection_manager.iou_threshold)
        self.max_det_spinbox.setValue(self.detection_manager.max_det)
        self.frame_validation_spinbox.setValue(self.detection_manager.frame_validation_count)
        
        # 加载高级参数
        self.augment_checkbox.setChecked(self.detection_manager.augment)
        self.agnostic_nms_checkbox.setChecked(self.detection_manager.agnostic_nms)
        
        # 加载类别选择
        for class_id, checkbox in self.class_checkboxes.items():
            checkbox.setChecked(class_id in self.detection_manager.relevant_classes)
    
    def browse_weights_file(self):
        """浏览模型文件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件", ".", "Model Files (*.pt);;All Files (*)")
        if file_path:
            self.weights_edit.setText(file_path)
    
    def select_all_classes(self):
        """全选类别"""
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(True)
    
    def deselect_all_classes(self):
        """全不选类别"""
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(False)
    
    def get_settings(self):
        """获取设置"""
        settings = {}
        settings["weights"] = self.weights_edit.text()
        settings["confidence_threshold"] = self.conf_threshold_spinbox.value()
        settings["iou_threshold"] = self.iou_threshold_spinbox.value()
        settings["max_det"] = self.max_det_spinbox.value()
        settings["frame_validation_count"] = self.frame_validation_spinbox.value()
        settings["augment"] = self.augment_checkbox.isChecked()
        settings["agnostic_nms"] = self.agnostic_nms_checkbox.isChecked()
        
        # 获取选中的类别
        selected_classes = [class_id for class_id, checkbox in self.class_checkboxes.items() 
                           if checkbox.isChecked()]
        settings["relevant_classes"] = selected_classes
        
        return settings

class UISettingsDialog(QDialog):
    """界面设置对话框，用于配置界面相关的参数"""
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle("界面设置")
        self.resize(400, 300)
        self.init_ui()
        self.load_current_settings()
    
    def init_ui(self):
        """初始化对话框UI"""
        layout = QVBoxLayout(self)
        
        # 创建显示参数布局
        display_group = QGroupBox("显示设置")
        display_layout = QFormLayout(display_group)
        
        # 显示置信度
        self.show_confidence_checkbox = QCheckBox()
        display_layout.addRow("显示置信度:", self.show_confidence_checkbox)
        
        # 显示标签
        self.show_labels_checkbox = QCheckBox()
        display_layout.addRow("显示标签:", self.show_labels_checkbox)
        
        # 线框粗细
        self.line_thickness_spinbox = QSpinBox()
        self.line_thickness_spinbox.setRange(1, 10)
        self.line_thickness_spinbox.setSingleStep(1)
        display_layout.addRow("线框粗细:", self.line_thickness_spinbox)
        
        # 更新间隔
        self.update_interval_spinbox = QSpinBox()
        self.update_interval_spinbox.setRange(10, 1000)
        self.update_interval_spinbox.setSingleStep(10)
        display_layout.addRow("更新间隔(毫秒):", self.update_interval_spinbox)
        
        # 添加到主布局
        layout.addWidget(display_group)
        
        # 创建报警设置布局
        alarm_group = QGroupBox("报警设置")
        alarm_layout = QFormLayout(alarm_group)
        
        # 报警声音
        self.alarm_sound_checkbox = QCheckBox()
        alarm_layout.addRow("启用报警声音:", self.alarm_sound_checkbox)
        
        # 添加到主布局
        layout.addWidget(alarm_group)
        
        # 创建按钮框
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def load_current_settings(self):
        """加载当前设置到对话框"""
        # 从配置文件或默认值加载设置
        # 这里使用默认值，实际实现时应当从配置文件加载
        self.show_confidence_checkbox.setChecked(True)
        self.show_labels_checkbox.setChecked(True)
        self.line_thickness_spinbox.setValue(2)
        self.update_interval_spinbox.setValue(100)
        self.alarm_sound_checkbox.setChecked(True)
    
    def get_settings(self):
        """获取设置"""
        settings = {}
        settings["show_confidence"] = self.show_confidence_checkbox.isChecked()
        settings["show_labels"] = self.show_labels_checkbox.isChecked()
        settings["line_thickness"] = self.line_thickness_spinbox.value()
        settings["update_interval_ms"] = self.update_interval_spinbox.value()
        settings["alarm_sound"] = self.alarm_sound_checkbox.isChecked()
        
        return settings
```

### 3.5 日志存储模块

#### 3.5.1 功能描述
- 记录系统运行日志
- 记录检测到的异物信息（时间、类型、位置、置信度、信号状态）
- 提供日志查询和导出功能
- 支持日志文件轮转

#### 3.5.2 日志格式
```
时间戳 | 事件类型 | 详细信息
2023-01-01 12:30:45 | 系统启动 | 系统初始化完成
2023-01-01 12:31:00 | 信号变化 | 状态从IDLE变为CLOSING
2023-01-01 12:31:05 | 检测报警 | 检测到[person]，置信度:0.85，位置:x1,y1,x2,y2
2023-01-01 12:31:10 | 信号变化 | 状态从CLOSING变为CLOSED
```

#### 3.5.3 类设计
```python
class LogManager:
    def __init__(self, log_file="detection_log.csv"):
        self.log_file = log_file
        self.initialize_log_file()
    
    def initialize_log_file(self):
        """初始化日志文件"""
    
    def log_system_event(self, event_type, details):
        """记录系统事件"""
    
    def log_detection(self, detection_result, signal_state):
        """记录检测结果"""
    
    def log_signal_change(self, old_state, new_state):
        """记录信号状态变化"""
    
    def export_logs(self, start_time=None, end_time=None, export_format="csv"):
        """导出日志"""
    
    def query_logs(self, query_params):
        """查询日志"""
```

## 4. 系统工作流程

### 4.1 初始化流程
1. 系统启动，初始化各模块
2. 加载YOLOv5预训练模型
3. 初始化视频源
4. 设置默认ROI区域
5. 连接各模块的信号和回调函数
6. 启动视频采集线程

### 4.2 检测流程
1. 信号交互模块接收"关门命令"信号
2. 系统状态切换为"关门中"
3. 目标检测模块开始执行检测
   - 获取当前视频帧
   - 应用ROI区域筛选
   - 执行目标检测推理
   - 筛选相关类别
   - 应用连续多帧验证规则
4. 如果检测到有效异物：
   - 触发报警（GUI弹窗、声音提示等）
   - 记录报警日志
5. 信号交互模块接收"已关闭命令"信号
6. 系统状态切换为"已关闭"
7. 停止检测过程

## 5. 关键技术实现

### 5.1 YOLOv5模型集成
- 使用YOLOv5预训练模型，通过`detect.py`脚本进行检测
- 封装模型调用，支持自定义参数传递
- 优化模型加载和推理性能

### 5.2 ROI实现
- 使用OpenCV的矩形选择功能实现ROI手动划定
- 保存ROI坐标到配置文件，支持下次启动自动加载
- 实现ROI区域内的目标检测结果筛选

### 5.3 连续多帧验证
- 维护检测历史队列
- 对检测到的目标进行匹配和计数
- 当连续帧数达到设定阈值时才判定为有效检测

### 5.4 模块化通信
- 采用回调函数机制实现模块间松耦合通信
- 定义标准化的数据结构传递检测结果
- 使用事件机制处理状态变化

## 6. 配置文件设计

```yaml
# 系统配置文件 (config.yaml)

# 视频源配置
video:
  source: 0  # 摄像头ID或视频文件路径
  width: 1280
  height: 720
  fps: 30

# 检测配置
detection:
  weights: "yolov5s.pt"
  confidence_threshold: 0.4
  iou_threshold: 0.45
  max_det: 1000
  # 按优先级排序的地铁夹人夹物场景相关类别ID
  relevant_classes: [0, 24, 25, 26, 28, 39, 41, 67, 27, 77]
  # 缺失类别的规则补充
  enable_small_object_detection: true  # 是否启用小物体检测
  small_object_area_threshold: 2500  # 小物体面积阈值（50x50像素）
  frame_validation_count: 2
  roi: [300, 200, 900, 500]  # [x1, y1, x2, y2]
  augment: false
  agnostic_nms: false

# 日志配置
log:
  file_path: "logs/detection_log.csv"
  max_file_size: 10  # MB
  backup_count: 5

# 界面配置
ui:
  show_confidence: true
  show_labels: true
  line_thickness: 2
  alarm_sound: true
  update_interval_ms: 100  # 更新间隔（毫秒）
```

## 7. 开发和部署计划

### 7.1 开发计划
- **阶段1**: 基础框架搭建（GUI界面、模块结构）
- **阶段2**: 视频采集和显示功能实现
- **阶段3**: YOLOv5模型集成和基本检测功能
- **阶段4**: ROI划定和连续多帧验证实现
- **阶段5**: 信号交互模块和报警功能
- **阶段6**: 日志存储和查询功能
- **阶段7**: 系统测试和优化

### 7.2 部署要求
- Python 3.8+
- PyTorch 1.7+
- CUDA环境（推荐，用于GPU加速）
- PyQt5
- OpenCV
- 其他依赖：requirements.txt

### 7.3 性能优化
- 使用GPU加速推理
- 优化视频流处理
- 实现多线程处理（UI线程、视频采集线程、检测线程）
- 减少不必要的图像转换和复制操作

## 8. 测试计划

### 8.1 功能测试
- 视频源连接和显示测试
- ROI区域划定和保存测试
- 模拟信号触发测试
- 目标检测准确性测试
- 连续多帧验证功能测试
- 报警功能测试
- 日志记录和查询测试

### 8.2 性能测试
- 检测延迟测试（从帧获取到检测结果输出）
- 系统资源占用监控
- 长时间运行稳定性测试

### 8.3 场景测试
- 不同光线条件下的检测性能
- 不同距离的目标检测
- 多目标同时出现的场景
- 模拟各种异物情况

## 9. 扩展功能展望

- 支持多摄像头同时监控
- 实现目标轨迹跟踪
- 集成深度学习模型自动学习ROI区域
- 添加语音播报报警信息
- 支持远程监控和报警通知
- 提供API接口与其他系统集成
- 开发移动端查看和配置功能

---

本开发文档提供了地铁屏蔽门间隙检测系统的详细设计方案，系统采用模块化设计，具有良好的扩展性和可维护性。在实际开发过程中，可根据具体需求和环境进行适当调整和优化。