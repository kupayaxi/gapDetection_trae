# 地铁屏蔽门间隙检测系统修复实施计划

## 1. 概述

本文档基于之前的系统分析，提供详细的修复实施计划，包括具体的代码修改方案、优先级安排和实施步骤，旨在指导开发团队系统性地解决地铁屏蔽门间隙检测系统中发现的问题。

## 2. 问题修复优先级安排

### 2.1 高优先级问题

| 问题ID | 问题描述 | 估计工作量 | 负责模块 | 影响范围 |
|--------|----------|------------|----------|----------|
| P01 | 摄像头检测进程频繁启停 | 2天 | detection_manager.py | 核心功能 |
| P02 | 摄像头帧读取失败 | 1.5天 | detect.py | 核心功能 |
| P03 | 模块导入和依赖问题 | 1天 | requirements.txt等 | 系统启动 |
| P04 | 进程资源未正确释放 | 1.5天 | detection_manager.py和detect.py | 系统稳定性 |

### 2.2 中优先级问题

| 问题ID | 问题描述 | 估计工作量 | 负责模块 | 影响范围 |
|--------|----------|------------|----------|----------|
| P05 | 完善GUI主界面 | 3天 | main_window.py | 用户体验 |
| P06 | 实现参数配置界面 | 2.5天 | detection_settings_dialog.py | 系统配置 |
| P07 | 日志查询功能增强 | 1.5天 | log_manager.py | 问题诊断 |
| P08 | 检测精度优化 | 3天 | detection_manager.py | 检测准确性 |

### 2.3 低优先级问题

| 问题ID | 问题描述 | 估计工作量 | 负责模块 | 影响范围 |
|--------|----------|------------|----------|----------|
| P09 | 实现外部信号交互接口 | 3天 | signal_handler.py | 系统集成 |
| P10 | 系统健康监控 | 2天 | 新增health_monitor.py | 系统维护 |
| P11 | 多目标检测优化 | 2.5天 | detection_manager.py | 检测准确性 |
| P12 | 中文字符处理优化 | 1天 | 多个模块 | 国际化支持 |

## 3. 详细修复方案

### 3.1 P01: 摄像头检测进程频繁启停修复

#### 问题分析
根据日志分析，检测进程存在频繁启动和意外退出的情况，退出码包括1、2和3221225786（通常表示程序崩溃）。这表明进程管理机制存在严重缺陷。

#### 修复方案

修改`src/object_detection/detection_manager.py`中的进程监控机制：

```python
# 优化_monitor_detection_process方法
def _monitor_detection_process(self):
    """
    监控检测进程状态，增强异常处理和自动重启机制
    """
    while self._detection_thread_running:
        try:
            # 检查进程是否存活
            if self._detection_process and not self._detection_process.poll() is None:
                # 进程已退出，记录退出码
                exit_code = self._detection_process.returncode
                self._log_manager.log_system_event(
                    "检测进程退出", 
                    f"进程意外退出，退出码: {exit_code}", 
                    level="ERROR"
                )
                
                # 尝试清理资源
                if self._detection_process.stdout:
                    self._detection_process.stdout.close()
                if self._detection_process.stderr:
                    self._detection_process.stderr.close()
                
                # 根据退出码判断是否需要重启
                if self._should_restart_process(exit_code):
                    self._log_manager.log_system_event(
                        "检测进程重启", 
                        "尝试重启检测进程"
                    )
                    # 延迟重启，避免立即重启导致资源占用过高
                    time.sleep(1)
                    self._start_detection_process()
                else:
                    # 停止监控
                    self._detection_thread_running = False
                    self._detection_process = None
            
            # 避免CPU占用过高
            time.sleep(0.5)
            
        except Exception as e:
            # 记录监控异常，但不终止监控线程
            self._log_manager.log_system_event(
                "进程监控异常", 
                f"监控线程发生异常: {str(e)}", 
                level="ERROR"
            )
            time.sleep(1)  # 发生异常后暂停一会儿再继续
            
    # 清理最后的进程资源
    if self._detection_process:
        try:
            # 尝试优雅终止
            self._detection_process.terminate()
            # 等待进程结束
            self._detection_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # 超时后强制终止
            self._detection_process.kill()
        finally:
            # 确保关闭管道
            if self._detection_process.stdout:
                self._detection_process.stdout.close()
            if self._detection_process.stderr:
                self._detection_process.stderr.close()
            self._detection_process = None
    
    self._log_manager.log_system_event(
        "进程监控结束", 
        "检测进程监控线程已结束"
    )

def _should_restart_process(self, exit_code):
    """
    根据退出码判断是否需要重启进程
    返回True表示需要重启，False表示不需要重启
    """
    # 定义可接受自动重启的退出码
    restartable_exit_codes = {1, 2}  # 这些退出码可能是临时错误
    
    # 检查是否超过最大重启次数
    if hasattr(self, '_restart_count'):
        self._restart_count += 1
        if self._restart_count > 5:  # 最多重启5次
            return False
    else:
        self._restart_count = 1
        
    # 返回是否可以重启
    return exit_code in restartable_exit_codes
```

同时优化`start_camera_detection`方法，添加参数验证和异常处理：

```python
def start_camera_detection(self, camera_id=0, **kwargs):
    """
    启动摄像头检测进程，增强参数验证和异常处理
    """
    try:
        # 验证模型已加载
        if not self._model_loaded:
            error_msg = "启动摄像头检测失败: 模型未加载且重新加载失败"
            self._log_manager.log_system_event("检测启动失败", error_msg, level="ERROR")
            # 尝试重新加载模型
            if not self.load_model():
                raise RuntimeError(error_msg)
        
        # 停止现有进程
        self.stop_camera_detection()
        
        # 构建命令参数
        cmd = ['python', 'detect.py']
        cmd.extend(['--source', str(camera_id)])
        cmd.extend(['--weights', self._weights_path])
        # 添加其他参数...
        
        # 创建进程
        with self._process_lock:
            self._detection_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True  # 使用文本模式
            )
        
        # 重置重启计数器
        self._restart_count = 0
        
        # 启动监控线程
        self._detection_thread_running = True
        self._detection_thread = threading.Thread(
            target=self._monitor_detection_process,
            daemon=True
        )
        self._detection_thread.start()
        
        self._log_manager.log_system_event(
            "检测进程启动", 
            f"摄像头检测进程已启动，摄像头ID: {camera_id}"
        )
        return True
        
    except Exception as e:
        self._log_manager.log_system_event(
            "检测启动异常", 
            f"启动摄像头检测进程时发生异常: {str(e)}", 
            level="ERROR"
        )
        # 确保资源清理
        self.stop_camera_detection()
        return False
```

### 3.2 P02: 摄像头帧读取失败修复

#### 问题分析
日志中有大量"无法读取摄像头帧"的错误记录，说明摄像头访问存在稳定性问题。可能的原因包括：
1. OpenCV视频捕获后端不兼容
2. 摄像头设备驱动问题
3. 没有适当的超时和重试机制

#### 修复方案

修改`detect.py`中的摄像头访问逻辑：

```python
# 优化摄像头打开和读取逻辑
def initialize_camera(source, max_retries=3):
    """
    初始化摄像头，支持多后端尝试和超时控制
    """
    # 尝试的后端列表（按优先级排序）
    backends = [cv2.CAP_DSHOW, cv2.CAP_VFW, cv2.CAP_ANY]
    
    cap = None
    retry_count = 0
    
    while retry_count < max_retries:
        for backend in backends:
            try:
                # 尝试使用指定后端打开摄像头
                cap = cv2.VideoCapture(source, backend)
                
                # 设置摄像头参数
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 减少缓冲区大小，降低延迟
                
                # 尝试读取一帧，验证摄像头是否正常工作
                ret, frame = cap.read()
                if ret:
                    log_to_csv("摄像头初始化", f"成功初始化摄像头，使用后端: {backend}")
                    return cap
                else:
                    # 读取失败，释放当前捕获对象
                    cap.release()
                    cap = None
                    log_to_csv("摄像头初始化", f"读取测试帧失败，尝试下一个后端", level="WARNING")
                    
            except Exception as e:
                # 发生异常，继续尝试下一个后端
                if cap is not None:
                    cap.release()
                    cap = None
                log_to_csv("摄像头初始化", f"使用后端{backend}初始化失败: {str(e)}", level="WARNING")
                    
        # 所有后端都尝试失败，增加重试计数
        retry_count += 1
        if retry_count < max_retries:
            wait_time = 2 * retry_count  # 指数退避等待
            log_to_csv("摄像头初始化", f"所有后端尝试失败，{wait_time}秒后重试 (尝试{retry_count}/{max_retries})")
            time.sleep(wait_time)
    
    # 所有尝试都失败
    error_msg = f"无法初始化摄像头，所有后端尝试失败 (已尝试{max_retries}次)"
    log_to_csv("摄像头初始化", error_msg, level="ERROR")
    raise RuntimeError(error_msg)

# 修改主循环中的摄像头读取逻辑
def process_video_stream(cap, timeout=30):
    """
    处理视频流，添加超时控制和错误恢复机制
    """
    last_successful_frame_time = time.time()
    frame_count = 0
    
    while True:
        try:
            # 检查摄像头是否打开
            if not cap.isOpened():
                log_to_csv("摄像头错误", "摄像头连接已断开，尝试重新连接", level="ERROR")
                # 尝试重新连接摄像头
                cap.release()
                cap = initialize_camera(0)  # 假设使用默认摄像头ID
                last_successful_frame_time = time.time()
                continue
            
            # 设置读取超时（如果支持）
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_count)  # 尝试获取最新帧
            
            # 读取帧
            ret, frame = cap.read()
            
            if ret:
                # 成功读取帧
                frame_count += 1
                last_successful_frame_time = time.time()
                
                # 处理帧...
                process_frame(frame)
                
                # 检查用户是否按下退出键
                if cv2.waitKey(1) in [ord('q'), 27]:  # q键或ESC键
                    break
                    
            else:
                # 读取失败，记录错误
                log_to_csv("摄像头错误", "无法读取摄像头帧", level="ERROR")
                
                # 检查是否超时
                current_time = time.time()
                if current_time - last_successful_frame_time > timeout:
                    log_to_csv("摄像头错误", f"摄像头读取超时 ({timeout}秒)，尝试重新连接", level="ERROR")
                    cap.release()
                    cap = initialize_camera(0)
                    last_successful_frame_time = current_time
                    
                # 短暂暂停，避免CPU占用过高
                time.sleep(0.1)
                
        except Exception as e:
            # 捕获所有异常，确保程序不会崩溃
            log_to_csv("视频处理错误", f"处理视频流时发生异常: {str(e)}", level="ERROR")
            
            # 检查是否超时
            current_time = time.time()
            if current_time - last_successful_frame_time > timeout:
                log_to_csv("摄像头错误", "视频处理异常且超时，尝试重新连接摄像头", level="ERROR")
                cap.release()
                cap = initialize_camera(0)
                last_successful_frame_time = current_time
            
            # 短暂暂停，避免CPU占用过高
            time.sleep(0.5)
```

### 3.3 P03: 模块导入和依赖问题修复

#### 问题分析
日志中出现了缺少'ultralytics'模块和utils包导入错误的情况，说明依赖管理存在问题。需要更新requirements.txt并修复模块间的依赖关系。

#### 修复方案

1. 更新`requirements.txt`：

```
# 基础依赖
numpy>=1.21.0
opencv-python>=4.5.5
pytorch>=1.10.0,<=1.13.1  # 避免使用过高版本导致兼容性问题
torchvision>=0.11.0,<=0.14.1
tqdm>=4.62.0
yaml>=0.2.5

# GUI相关
PyQt5>=5.15.0
PyQt5-sip>=12.9.0

# 可选依赖（如有需要）
# ultralytics>=8.0.0  # 注意：根据代码分析，系统使用的是自定义YOLOv5实现，可能不需要ultralytics包
matplotlib>=3.5.0  # 用于可视化
pillow>=9.0.0  # 图像处理

# 系统监控
psutil>=5.9.0  # 用于监控系统资源
```

2. 修复模块导入路径：

在`detection_manager.py`中修改导入语句：

```python
# 添加项目根目录到Python路径，确保能正确导入utils等模块
import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

# 然后导入所需模块
from utils.general import non_max_suppression
from utils.torch_utils import select_device
# 其他导入...
```

3. 实现依赖检查机制：

创建一个新文件`src/utils/dependency_check.py`：

```python
import importlib
import sys
import subprocess
import pkg_resources

def check_dependencies():
    """
    检查必需的依赖是否已安装，如未安装则尝试安装
    返回所有成功安装的包列表和失败的包列表
    """
    # 必需的包列表
    required_packages = [
        'numpy>=1.21.0',
        'opencv-python>=4.5.5',
        'pytorch>=1.10.0',
        'torchvision>=0.11.0',
        'PyQt5>=5.15.0',
        'psutil>=5.9.0',
        'tqdm>=4.62.0',
        'yaml>=0.2.5'
    ]
    
    installed = []
    missing = []
    
    for package in required_packages:
        # 提取包名（去掉版本信息）
        package_name = package.split('>=')[0].split('<=')[0].split('==')[0]
        
        try:
            # 检查包是否已安装
            pkg_resources.require(package)
            installed.append(package)
        except pkg_resources.DistributionNotFound:
            # 包未安装
            missing.append(package)
        except pkg_resources.VersionConflict:
            # 版本不匹配
            missing.append(package)
    
    # 尝试安装缺失的包
    if missing:
        print(f"发现{len(missing)}个缺失的依赖，正在尝试安装...")
        for package in missing:
            try:
                print(f"安装 {package}...")
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package])
                installed.append(package)
                # 从missing列表中移除
                missing.remove(package)
            except subprocess.CalledProcessError:
                print(f"安装 {package} 失败")
    
    return installed, missing

# 在main.py中调用
def main():
    # 检查依赖
    installed, missing = check_dependencies()
    
    if missing:
        print(f"警告: 以下依赖安装失败，可能会影响程序功能:")
        for package in missing:
            print(f"  - {package}")
        print("请手动安装这些依赖后再运行程序")
    else:
        print("所有依赖检查通过")
    
    # 继续程序执行...
```

### 3.4 P04: 进程资源未正确释放修复

#### 问题分析
检测进程意外退出后，相关资源（如文件描述符、网络连接等）可能没有被正确释放，导致资源泄漏。需要确保在所有情况下都能正确释放资源。

#### 修复方案

在`detection_manager.py`中增强资源管理：

```python
# 优化stop_camera_detection方法
def stop_camera_detection(self):
    """
    安全停止摄像头检测进程，确保所有资源被正确释放
    """
    with self._process_lock:
        # 停止监控线程
        self._detection_thread_running = False
        
        # 等待监控线程结束
        if hasattr(self, '_detection_thread') and self._detection_thread.is_alive():
            self._detection_thread.join(timeout=5)  # 最多等待5秒
        
        # 终止进程
        if hasattr(self, '_detection_process') and self._detection_process is not None:
            try:
                # 首先尝试优雅终止
                self._detection_process.terminate()
                
                # 等待进程结束
                try:
                    self._detection_process.wait(timeout=5)
                    self._log_manager.log_system_event(
                        "检测进程停止", 
                        "摄像头检测进程已成功终止"
                    )
                except subprocess.TimeoutExpired:
                    # 超时后强制终止
                    self._log_manager.log_system_event(
                        "检测进程强制终止", 
                        "进程终止超时，正在强制终止", 
                        level="WARNING"
                    )
                    self._detection_process.kill()
                    
                # 确保关闭所有管道
                for pipe in [self._detection_process.stdout, self._detection_process.stderr]:
                    if pipe:
                        try:
                            pipe.close()
                        except Exception as e:
                            # 记录关闭管道时的异常，但不影响后续操作
                            self._log_manager.log_system_event(
                                "资源清理警告", 
                                f"关闭进程管道时发生异常: {str(e)}", 
                                level="WARNING"
                            )
                            
            except Exception as e:
                self._log_manager.log_system_event(
                    "进程终止异常", 
                    f"停止检测进程时发生异常: {str(e)}", 
                    level="ERROR"
                )
            finally:
                # 无论如何都将进程对象设置为None
                self._detection_process = None
```

在`detect.py`中使用上下文管理器确保资源释放：

```python
# 创建上下文管理器用于安全管理摄像头资源
class CameraContext:
    def __init__(self, source):
        self.source = source
        self.cap = None
        
    def __enter__(self):
        # 初始化摄像头
        self.cap = initialize_camera(self.source)
        return self.cap
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 确保摄像头被释放
        if self.cap is not None:
            try:
                self.cap.release()
                log_to_csv("资源清理", "摄像头资源已成功释放")
            except Exception as e:
                log_to_csv("资源清理错误", f"释放摄像头时发生异常: {str(e)}", level="WARNING")

# 在main函数中使用上下文管理器
def main():
    # 解析参数
    opt = parse_opt()
    
    try:
        # 加载模型
        model = load_model(opt.weights)
        
        # 使用上下文管理器安全管理摄像头资源
        with CameraContext(opt.source) as cap:
            # 设置窗口
            cv2.namedWindow('地铁屏蔽门间隙检测', cv2.WINDOW_NORMAL)
            cv2.resizeWindow('地铁屏蔽门间隙检测', 800, 600)
            
            # 处理视频流
            process_video_stream(cap)
            
    except Exception as e:
        log_to_csv("程序异常", f"主程序发生异常: {str(e)}", level="ERROR")
        print(f"错误: {str(e)}")
    finally:
        # 确保关闭所有窗口
        cv2.destroyAllWindows()
        log_to_csv("程序结束", "程序已正常退出")
```

### 3.5 P05: 完善GUI主界面

#### 问题分析
当前GUI主界面实现不完整，缺少实时视频显示和控制功能，需要完善主窗口的实现。

#### 修复方案

更新`src/gui/main_window.py`，实现基本的GUI功能：

```python
import sys
import cv2
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QStatusBar, QTextEdit, QSplitter, QMessageBox, QAction, QMenu, QMenuBar
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QImage, QPixmap

from src.signal_handler.signal_handler import SignalHandler
from src.object_detection.detection_manager import DetectionManager
from src.logger.log_manager import LogManager

class VideoProcessingThread(QThread):
    """
    视频处理线程，用于在后台处理视频流，避免阻塞UI线程
    """
    frame_processed = pyqtSignal(QImage)
    
    def __init__(self, detection_manager, signal_handler):
        super().__init__()
        self.detection_manager = detection_manager
        self.signal_handler = signal_handler
        self.running = False
        self.cap = None
        
    def run(self):
        # 这里应该实现视频捕获和处理逻辑
        # 为简化示例，仅实现基本框架
        pass

class MainWindow(QMainWindow):
    """
    主窗口类，实现系统的GUI界面
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("地铁屏蔽门间隙检测系统")
        self.resize(1024, 768)
        
        # 初始化管理器
        self.signal_handler = SignalHandler()
        self.detection_manager = DetectionManager()
        self.log_manager = LogManager()
        
        # 注册回调
        self.signal_handler.register_callback(self.on_signal_state_changed)
        self.detection_manager.register_detection_callback(self.on_detection_result)
        
        # 初始化视频处理线程
        self.video_thread = VideoProcessingThread(self.detection_manager, self.signal_handler)
        self.video_thread.frame_processed.connect(self.update_video_display)
        
        # 初始化UI
        self.init_ui()
        
        # 初始化状态栏
        self.statusBar = QStatusBar()
        self.setStatusBar(self.statusBar)
        self.update_status_bar()
    
    def init_ui(self):
        """
        初始化UI组件
        """
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # 创建主布局
        main_layout = QVBoxLayout(central_widget)
        
        # 创建菜单栏
        self.create_menu_bar()
        
        # 创建视频显示区域
        self.video_label = QLabel("视频显示区域")
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setStyleSheet("background-color: #000000; color: #ffffff")
        
        # 创建控制面板
        control_layout = QHBoxLayout()
        
        self.start_button = QPushButton("开始检测")
        self.start_button.clicked.connect(self.start_detection)
        
        self.stop_button = QPushButton("停止检测")
        self.stop_button.clicked.connect(self.stop_detection)
        self.stop_button.setEnabled(False)
        
        self.closing_command_button = QPushButton("关门命令")
        self.closing_command_button.clicked.connect(self.on_closing_command)
        
        self.closed_command_button = QPushButton("已关闭命令")
        self.closed_command_button.clicked.connect(self.on_closed_command)
        
        self.reset_button = QPushButton("重置")
        self.reset_button.clicked.connect(self.on_reset)
        
        control_layout.addWidget(self.start_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.closing_command_button)
        control_layout.addWidget(self.closed_command_button)
        control_layout.addWidget(self.reset_button)
        
        # 创建状态标签
        self.state_label = QLabel("信号状态: 空闲")
        self.state_label.setStyleSheet("font-weight: bold")
        
        # 创建日志显示区域
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        self.log_text_edit.setMaximumHeight(200)
        
        # 添加组件到主布局
        main_layout.addWidget(self.video_label)
        main_layout.addLayout(control_layout)
        main_layout.addWidget(self.state_label)
        main_layout.addWidget(self.log_text_edit)
    
    def create_menu_bar(self):
        """
        创建菜单栏
        """
        menu_bar = self.menuBar()
        
        # 文件菜单
        file_menu = menu_bar.addMenu("文件")
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # 设置菜单
        settings_menu = menu_bar.addMenu("设置")
        
        detection_settings_action = QAction("检测参数设置", self)
        detection_settings_action.triggered.connect(self.open_detection_settings)
        settings_menu.addAction(detection_settings_action)
        
        roi_settings_action = QAction("ROI区域设置", self)
        roi_settings_action.triggered.connect(self.open_roi_settings)
        settings_menu.addAction(roi_settings_action)
        
        # 帮助菜单
        help_menu = menu_bar.addMenu("帮助")
        
        about_action = QAction("关于", self)
        about_action.triggered.connect(self.show_about_dialog)
        help_menu.addAction(about_action)
    
    def start_detection(self):
        """
        开始检测
        """
        try:
            # 加载模型
            if not self.detection_manager.load_model():
                QMessageBox.warning(self, "警告", "无法加载检测模型")
                return
            
            # 启动视频处理线程
            self.video_thread.running = True
            self.video_thread.start()
            
            # 更新按钮状态
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            
            # 记录日志
            self.log_manager.log_system_event("系统操作", "检测已开始")
            self.log_text_edit.append(f"[{self.log_manager.get_current_time()}] 检测已开始")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"启动检测失败: {str(e)}")
            self.log_manager.log_system_event("系统错误", f"启动检测失败: {str(e)}", level="ERROR")
    
    def stop_detection(self):
        """
        停止检测
        """
        try:
            # 停止视频处理线程
            self.video_thread.running = False
            self.video_thread.wait()
            
            # 停止摄像头检测
            self.detection_manager.stop_camera_detection()
            
            # 更新按钮状态
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            
            # 记录日志
            self.log_manager.log_system_event("系统操作", "检测已停止")
            self.log_text_edit.append(f"[{self.log_manager.get_current_time()}] 检测已停止")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"停止检测失败: {str(e)}")
            self.log_manager.log_system_event("系统错误", f"停止检测失败: {str(e)}", level="ERROR")
    
    def on_closing_command(self):
        """
        处理关门命令
        """
        self.signal_handler.set_state_to_closing()
    
    def on_closed_command(self):
        """
        处理已关闭命令
        """
        self.signal_handler.set_state_to_closed()
    
    def on_reset(self):
        """
        重置信号状态
        """
        self.signal_handler.set_state_to_idle()
    
    def on_signal_state_changed(self, old_state, new_state):
        """
        信号状态变化回调
        """
        # 更新状态显示
        state_text = {"IDLE": "空闲", "CLOSING": "关门中", "CLOSED": "已关闭", "ALARM": "报警"}
        self.state_label.setText(f"信号状态: {state_text.get(new_state, '未知')}")
        
        # 记录日志
        old_state_text = state_text.get(old_state, '未知')
        new_state_text = state_text.get(new_state, '未知')
        self.log_manager.log_system_event("状态变化", f"从{old_state_text}变为{new_state_text}")
        self.log_text_edit.append(f"[{self.log_manager.get_current_time()}] 状态从{old_state_text}变为{new_state_text}")
        
        # 更新状态栏
        self.update_status_bar()
    
    def on_detection_result(self, detection_result):
        """
        检测结果回调
        """
        if detection_result and len(detection_result) > 0:
            # 显示报警
            self.show_alarm(detection_result)
            
            # 记录日志
            for detection in detection_result:
                self.log_manager.log_detection(detection, self.signal_handler.current_state)
                class_name = detection.get('class_name', '未知')
                confidence = detection.get('confidence', 0)
                self.log_text_edit.append(
                    f"[{self.log_manager.get_current_time()}] 检测到 {class_name}，置信度: {confidence:.2f}"
                )
    
    def update_video_display(self, image):
        """
        更新视频显示
        """
        self.video_label.setPixmap(QPixmap.fromImage(image))
    
    def update_status_bar(self):
        """
        更新状态栏
        """
        state_text = {"IDLE": "空闲", "CLOSING": "关门中", "CLOSED": "已关闭", "ALARM": "报警"}
        self.statusBar.showMessage(f"系统状态: {state_text.get(self.signal_handler.current_state, '未知')}")
    
    def show_alarm(self, detection_result):
        """
        显示报警对话框
        """
        # 收集检测结果信息
        alarm_text = "检测到以下异物:\n\n"
        for detection in detection_result:
            class_name = detection.get('class_name', '未知')
            confidence = detection.get('confidence', 0)
            alarm_text += f"- {class_name} (置信度: {confidence:.2f})\n"
        
        # 显示警告对话框
        QMessageBox.warning(self, "报警 - 检测到异物", alarm_text)
    
    def open_detection_settings(self):
        """
        打开检测参数设置对话框
        """
        # 这里应该打开检测参数设置对话框
        # 由于实现较复杂，此处仅显示占位消息
        QMessageBox.information(self, "提示", "检测参数设置对话框将在此处打开")
    
    def open_roi_settings(self):
        """
        打开ROI区域设置对话框
        """
        # 这里应该打开ROI设置对话框
        QMessageBox.information(self, "提示", "ROI区域设置对话框将在此处打开")
    
    def show_about_dialog(self):
        """
        显示关于对话框
        """
        QMessageBox.about(self, "关于", "地铁屏蔽门间隙检测系统 v1.0\n\n用于检测地铁屏蔽门间隙中的异物，保障乘客安全。")
    
    def closeEvent(self, event):
        """
        窗口关闭事件处理
        """
        # 确保停止检测
        self.stop_detection()
        event.accept()

# 主函数
if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
```

### 3.6 P06: 实现参数配置界面

#### 问题分析
当前缺少参数配置界面，无法动态调整检测参数，需要实现一个完整的检测参数配置对话框。

#### 修复方案

创建`src/gui/detection_settings_dialog.py`文件：

```python
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                           QLabel, QLineEdit, QPushButton, QFileDialog, 
                           QSlider, QDoubleSpinBox, QSpinBox, QTabWidget, 
                           QWidget, QGroupBox, QCheckBox, QScrollArea, 
                           QDialogButtonBox)
from PyQt5.QtCore import Qt

class DetectionSettingsDialog(QDialog):
    """
    检测参数设置对话框，用于配置所有与YOLOv5检测相关的参数
    """
    def __init__(self, parent=None, detection_manager=None):
        super().__init__(parent)
        self.detection_manager = detection_manager
        self.setWindowTitle("检测参数设置")
        self.resize(500, 600)
        
        # 初始化UI
        self.init_ui()
        
        # 如果提供了detection_manager，加载当前设置
        if self.detection_manager:
            self.load_current_settings()
    
    def init_ui(self):
        """
        初始化对话框UI
        """
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
        
        # 地铁场景相关的类别
        self.relevant_classes = {
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
        
        # 添加类别复选框
        for class_id, class_name in self.relevant_classes.items():
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
        """
        从detection_manager加载当前设置
        """
        if not self.detection_manager:
            return
            
        # 加载基本参数
        self.weights_edit.setText(getattr(self.detection_manager, '_weights_path', 'yolov5s.pt'))
        self.conf_threshold_slider.setValue(int(getattr(self.detection_manager, '_confidence_threshold', 0.4) * 100))
        self.conf_threshold_spinbox.setValue(getattr(self.detection_manager, '_confidence_threshold', 0.4))
        self.iou_threshold_slider.setValue(int(getattr(self.detection_manager, '_iou_threshold', 0.45) * 100))
        self.iou_threshold_spinbox.setValue(getattr(self.detection_manager, '_iou_threshold', 0.45))
        self.max_det_spinbox.setValue(getattr(self.detection_manager, '_max_det', 1000))
        self.frame_validation_spinbox.setValue(getattr(self.detection_manager, '_frame_validation_count', 2))
        
        # 加载高级参数
        self.augment_checkbox.setChecked(getattr(self.detection_manager, '_augment', False))
        self.agnostic_nms_checkbox.setChecked(getattr(self.detection_manager, '_agnostic_nms', False))
        
        # 加载类别选择
        relevant_classes = getattr(self.detection_manager, '_relevant_classes', [])
        for class_id, checkbox in self.class_checkboxes.items():
            checkbox.setChecked(class_id in relevant_classes)
    
    def browse_weights_file(self):
        """
        浏览模型文件
        """
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择模型文件", ".", "Model Files (*.pt);;All Files (*)")
        if file_path:
            self.weights_edit.setText(file_path)
    
    def select_all_classes(self):
        """
        全选类别
        """
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(True)
    
    def deselect_all_classes(self):
        """
        全不选类别
        """
        for checkbox in self.class_checkboxes.values():
            checkbox.setChecked(False)
    
    def get_settings(self):
        """
        获取设置
        """
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
```

### 3.7 P07-P12: 其他问题修复方案

针对剩余的中低优先级问题，此处提供简要的修复方案概述，详细实现可根据项目进度和资源情况逐步完成。

#### P07: 日志查询功能增强
- 为`LogManager`类添加更丰富的查询方法，支持按时间范围、事件类型和关键词筛选
- 实现日志统计功能，生成每日/每周检测报告
- 优化日志文件轮转机制，支持按日期创建新文件

#### P08: 检测精度优化
- 优化`_apply_rule_optimization`方法，提高肢体被夹判断和细小异物标记的准确性
- 实现更智能的ROI边缘检测，适应不同场景下的屏蔽门间隙
- 添加图像预处理步骤，提高在不同光线条件下的检测效果

#### P09: 实现外部信号交互接口
- 创建`hardware_interface.py`，实现与地铁控制系统的串口通信
- 定义标准的信号协议，包括信号类型、格式和校验方式
- 实现信号状态的实时同步和异常处理

#### P10: 系统健康监控
- 创建`health_monitor.py`，实现CPU、内存、GPU使用率监控
- 添加摄像头连接状态和视频流质量监控
- 实现系统性能预警机制

#### P11: 多目标检测优化
- 优化NMS算法，提高多目标场景下的检测准确性
- 实现目标跟踪，关联连续帧中的同一目标
- 优化小目标检测算法，提高对细小物体的检测能力

#### P12: 中文字符处理优化
- 统一使用UTF-8编码处理所有文本数据
- 在文件读写和字符串操作中显式指定编码
- 优化路径处理，确保在不同操作系统下兼容中文路径

## 4. 修复实施步骤

### 4.1 准备阶段
1. 环境准备：确保开发环境包含所有必要的依赖
2. 代码备份：在进行修改前备份所有源代码
3. 搭建测试环境：准备测试摄像头和模拟场景

### 4.2 实施阶段
1. 首先修复高优先级问题（P01-P04）
   - 修复进程管理问题
   - 解决摄像头访问问题
   - 修复依赖问题
   - 优化资源管理
2. 实施中优先级问题（P05-P08）
   - 完善GUI界面
   - 实现参数配置功能
   - 增强日志管理
   - 优化检测精度
3. 处理低优先级问题（P09-P12）
   - 实现外部信号接口
   - 添加系统监控
   - 优化多目标检测
   - 改进中文字符处理

### 4.3 测试阶段
1. 单元测试：对每个修复的模块进行独立测试
2. 集成测试：测试模块间的交互是否正常
3. 系统测试：测试整个系统在不同场景下的表现
4. 性能测试：测试系统在长时间运行下的稳定性和性能

### 4.4 部署阶段
1. 更新文档：修改用户手册和部署文档
2. 构建安装包：创建可分发的安装包
3. 部署测试：在实际环境中进行部署测试
4. 正式部署：将修复后的系统部署到生产环境

## 5. 结论

本文档提供了地铁屏蔽门间隙检测系统的详细修复实施计划，包括具体的代码修改方案、优先级安排和实施步骤。通过系统性地解决已发现的问题，特别是进程管理、摄像头访问和资源管理等核心问题，可以显著提高系统的稳定性和可靠性，为地铁安全运行提供更有效的保障。

在实施过程中，应严格遵循测试-修改-验证的流程，确保每个修复都能达到预期效果，同时不引入新的问题。此外，应建立完善的问题反馈和监控机制，及时发现和解决系统运行过程中的新问题。