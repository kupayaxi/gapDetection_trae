import os
import sys
import threading
import subprocess
import time
import numpy as np
from collections import deque
import torch
import select  # 添加select模块用于非阻塞IO
import cv2  # 添加cv2模块
import signal
import traceback  # 添加traceback模块用于详细的错误追踪

# 添加YOLOv5项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# 导入配置管理器，使用尝试不同的导入路径
try:
    from config.config_manager import config_manager
except ImportError:
    try:
        from src.config.config_manager import config_manager
    except ImportError:
        print("警告：无法导入config_manager，使用默认配置")
        class DefaultConfigManager:
            def get(self, key, default=None):
                return default
        config_manager = DefaultConfigManager()

# 导入日志管理器
try:
    from logger.log_manager import log_manager
except ImportError:
    try:
        from src.logger.log_manager import log_manager
    except ImportError:
        print("警告：无法导入log_manager，使用简单的打印替代")
        class SimpleLogger:
            def log_error(self, msg):
                print(f"错误: {msg}")
            def log_system_event(self, event_type, details):
                print(f"{event_type}: {details}")
            def log_detection(self, detection_result, signal_state):
                pass
        log_manager = SimpleLogger()

# 导入信号处理器
try:
    from signal_handler.signal_handler import signal_handler, SystemState
except ImportError:
    try:
        from src.signal_handler.signal_handler import signal_handler, SystemState
    except ImportError:
        print("警告：无法导入signal_handler，定义简单的SystemState枚举")
        from enum import Enum
        class SystemState(Enum):
            IDLE = 0
            DOOR_CLOSING = 1
            DETECTING = 2
            DOOR_CLOSED = 3
            CLOSING = 1  # 兼容其他模块使用的CLOSING状态
            ALARM = 4    # 添加报警状态
        
        class SimpleSignalHandler:
            def __init__(self):
                self.current_state = SystemState.IDLE
                self._alarm_callbacks = []
            
            def register_alarm_callback(self, callback):
                if callback not in self._alarm_callbacks:
                    self._alarm_callbacks.append(callback)
            
            def trigger_alarm(self, alarm_info):
                print(f"报警触发（SimpleSignalHandler）: {alarm_info}")
                for callback in self._alarm_callbacks:
                    try:
                        callback(alarm_info)
                    except Exception as e:
                        print(f"报警回调执行失败: {e}")
                        
            def get_current_state(self):
                return self.current_state
                
            def set_state(self, state):
                self.current_state = state
        signal_handler = SimpleSignalHandler()


class DetectionManager:
    """目标检测模块，负责使用YOLOv5模型进行目标检测"""
    
    def __init__(self, weights_path=None):
        """初始化检测管理器"""
        # 模型相关参数
        self.model = None
        # 如果提供了weights_path参数则使用，否则从配置中读取
        # 解析模型路径为绝对路径
        self.weights_path = weights_path if weights_path else config_manager.get("detection.weights", "yolov5s.pt")
        
        # 检查本地模型文件，优先使用项目根目录和src目录下的模型
        possible_paths = [
            self.weights_path,
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), self.weights_path),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), self.weights_path)
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self.weights_path = os.path.abspath(path)
                break
        self.confidence_threshold = config_manager.get("detection.confidence_threshold", 0.4)
        self.iou_threshold = config_manager.get("detection.iou_threshold", 0.45)
        self.max_det = config_manager.get("detection.max_det", 1000)
        
        # 地铁屏蔽门夹人夹物场景相关类别ID及对应名称（按优先级排序）
        self.relevant_classes = config_manager.get("detection.relevant_classes", 
                                                 [0, 24, 25, 26, 28, 39, 41, 67, 27, 77])
        # 默认的COCO数据集类别名称
        self.class_names = {
            0: 'person', 1: 'bicycle', 2: 'car', 3: 'motorcycle', 4: 'airplane',
            5: 'bus', 6: 'train', 7: 'truck', 8: 'boat', 9: 'traffic light',
            10: 'fire hydrant', 11: 'stop sign', 12: 'parking meter', 13: 'bench',
            14: 'bird', 15: 'cat', 16: 'dog', 17: 'horse', 18: 'sheep',
            19: 'cow', 20: 'elephant', 21: 'bear', 22: 'zebra', 23: 'giraffe',
            24: 'backpack', 25: 'umbrella', 26: 'handbag', 27: 'tie', 28: 'suitcase',
            29: 'frisbee', 30: 'skis', 31: 'snowboard', 32: 'sports ball', 33: 'kite',
            34: 'baseball bat', 35: 'baseball glove', 36: 'skateboard', 37: 'surfboard',
            38: 'tennis racket', 39: 'bottle', 40: 'wine glass', 41: 'cup', 42: 'fork',
            43: 'knife', 44: 'spoon', 45: 'bowl', 46: 'banana', 47: 'apple',
            48: 'sandwich', 49: 'orange', 50: 'broccoli', 51: 'carrot', 52: 'hot dog',
            53: 'pizza', 54: 'donut', 55: 'cake', 56: 'chair', 57: 'couch',
            58: 'potted plant', 59: 'bed', 60: 'dining table', 61: 'toilet', 62: 'tv',
            63: 'laptop', 64: 'mouse', 65: 'remote', 66: 'keyboard', 67: 'cell phone',
            68: 'microwave', 69: 'oven', 70: 'toaster', 71: 'sink', 72: 'refrigerator',
            73: 'book', 74: 'clock', 75: 'vase', 76: 'scissors', 77: 'teddy bear',
            78: 'hair drier', 79: 'toothbrush'
        }
        
        # ROI区域
        self.roi = config_manager.get("detection.roi", [300, 200, 900, 500])  # [x1, y1, x2, y2]
        
        # 多帧验证相关
        self.frame_validation_count = config_manager.get("detection.frame_validation_count", 2)
        self.enable_frame_validation = config_manager.get("detection.enable_frame_validation", False)  # 默认关闭多帧验证
        self.detection_history = deque(maxlen=self.frame_validation_count)
        
        # 其他参数
        self.augment = config_manager.get("detection.augment", False)
        self.agnostic_nms = config_manager.get("detection.agnostic_nms", False)
        
        # 小物体检测参数
        self.enable_small_object_detection = config_manager.get("detection.enable_small_object_detection", True)
        self.small_object_area_threshold = config_manager.get("detection.small_object_area_threshold", 2500)  # 50x50像素
        
        # 线程安全锁
        self.lock = threading.RLock()
        
        # 检测回调
        self.detection_callbacks = []
        # 回调锁，确保线程安全
        self.callback_lock = threading.RLock()
        
        # 进程管理相关
        self.camera_detection_process = None
        self.camera_detection_running = False
        self.python_exe = sys.executable  # 获取当前Python解释器路径
        self.monitor_thread = None
        self.monitor_stop_event = threading.Event()
        
        # 加载模型
        self.load_model()
    
    def register_detection_callback(self, callback):
        """注册检测结果回调函数
        
        Args:
            callback: 回调函数，接收检测结果作为参数
        """
        with self.callback_lock:
            if callback not in self.detection_callbacks:
                self.detection_callbacks.append(callback)
    
    def unregister_detection_callback(self, callback):
        """移除检测结果回调函数
        
        Args:
            callback: 要移除的回调函数
        """
        with self.callback_lock:
            if callback in self.detection_callbacks:
                self.detection_callbacks.remove(callback)
    
    def load_model(self):
        """加载YOLOv5模型
        
        Returns:
            bool: 是否加载成功
        """
        # 尝试加载模型
        try:
            with self.lock:
                # 确保使用项目中已有的YOLOv5代码
                from models.experimental import attempt_load
                from utils.general import non_max_suppression, scale_coords
                from utils.dataloaders import letterbox
                from utils.torch_utils import select_device
                
                # 保存函数引用
                self.non_max_suppression = non_max_suppression
                self.scale_coords = scale_coords  # 使用scale_coords而不是scale_boxes
                self.letterbox = letterbox
                
                # 选择设备
                self.device = select_device('')  # 自动选择设备
                
                # 加载模型
                self.model = attempt_load(self.weights_path, device=self.device)
                
                # 获取模型输入尺寸
                self.img_size = 640
                
                # 确保模型处于评估模式
                self.model.eval()
                
                log_manager.log_system_event("模型加载", f"成功加载模型: {self.weights_path}")
                return True
        except Exception as e:
            log_manager.log_error(f"加载模型失败: {str(e)}")
            log_manager.log_error(traceback.format_exc())  # 添加详细的堆栈跟踪
            self.model = None
            return False
    
    # 注意：register_detection_callback和unregister_detection_callback方法已经在文件开头定义，并使用了锁确保线程安全
    
    def start_camera_detection(self):
        """启动摄像头实时检测进程
        
        Returns:
            bool: 是否启动成功
        """
        try:
            # 停止已有的检测进程
            self.stop_camera_detection()
            
            log_manager.log_system_event("摄像头检测", "准备启动摄像头检测进程")
            
            # 构建命令行参数
            detect_script_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                "detect.py"
            )
            
            # 检查脚本是否存在
            if not os.path.exists(detect_script_path):
                error_msg = f"检测脚本不存在: {detect_script_path}"
                log_manager.log_error(error_msg)
                return False
            
            cmd = [
                self.python_exe,
                detect_script_path,
                "--source", "0",  # 使用默认摄像头
                "--weights", self.weights_path,
                "--conf-thres", str(self.confidence_threshold),
                "--iou-thres", str(self.iou_threshold),
                "--view-img"  # 显示检测结果窗口
            ]
            
            # 添加相关类别过滤
            if self.relevant_classes:
                cmd.extend(["--classes"] + [str(c) for c in self.relevant_classes])
            
            log_manager.log_system_event("摄像头检测", f"开始摄像头实时检测，命令: {' '.join(cmd)}")
            
            # 启动新的检测进程
            self.camera_detection_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=None,
                creationflags=subprocess.CREATE_NEW_CONSOLE  # 在Windows上创建新控制台
            )
            
            self.camera_detection_running = True
            
            # 启动监控线程
            self.monitor_stop_event.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_detection_process)
            self.monitor_thread.daemon = True
            self.monitor_thread.start()
            
            log_manager.log_system_event("摄像头检测", "摄像头检测进程已成功启动")
            return True
        except Exception as e:
            error_msg = f"启动摄像头检测失败: {str(e)}"
            log_manager.log_error(error_msg)
            log_manager.log_error(traceback.format_exc())  # 添加详细的堆栈跟踪
            # 确保状态被正确重置
            self.camera_detection_process = None
            self.camera_detection_running = False
            return False
            
    def _monitor_detection_process(self):
        """监控检测进程的运行状态"""
        while not self.monitor_stop_event.is_set():
            if self.camera_detection_process:
                try:
                    # 检查进程是否仍然运行
                    return_code = self.camera_detection_process.poll()
                    if return_code is not None:
                        # 进程已退出
                        if return_code == 0:
                            log_manager.log_system_event("摄像头检测", f"摄像头检测进程正常退出，退出码: {return_code}")
                        else:
                            log_manager.log_error(f"摄像头检测进程意外退出，退出码: {return_code}")
                            
                            # 尝试读取进程的标准输出和错误输出
                            try:
                                stdout = self.camera_detection_process.stdout.read().decode('utf-8', errors='ignore')
                                stderr = self.camera_detection_process.stderr.read().decode('utf-8', errors='ignore')
                                if stdout:
                                    log_manager.log_error(f"进程输出: {stdout}")
                                if stderr:
                                    log_manager.log_error(f"进程错误: {stderr}")
                            except Exception as read_error:
                                log_manager.log_error(f"读取进程输出失败: {str(read_error)}")
                        
                        # 重置状态
                        with self.lock:
                            self.camera_detection_running = False
                            self.camera_detection_process = None
                        break
                except Exception as e:
                    log_manager.log_error(f"监控检测进程失败: {str(e)}")
                    try:
                        with self.lock:
                            self.camera_detection_running = False
                            self.camera_detection_process = None
                    except Exception:
                        pass
            
            # 每隔1秒检查一次
            time.sleep(1)
    
    def stop_camera_detection(self):
        """停止摄像头实时检测进程
        
        Returns:
            bool: 是否停止成功
        """
        try:
            # 使用锁确保线程安全
            with self.lock:
                # 停止监控线程
                self.monitor_stop_event.set()
                if self.monitor_thread and self.monitor_thread.is_alive():
                    try:
                        self.monitor_thread.join(timeout=2.0)
                    except Exception as thread_join_error:
                        log_manager.log_error(f"等待监控线程结束失败: {str(thread_join_error)}")
                
                # 停止检测进程
                if self.camera_detection_process:
                    log_manager.log_system_event("摄像头检测", "尝试停止摄像头检测进程")
                    
                    # 尝试优雅地终止进程
                    try:
                        if os.name == 'nt':  # Windows系统
                            # 在Windows上，使用terminate()
                            self.camera_detection_process.terminate()
                            # 等待进程终止，最多等待2秒
                            self.camera_detection_process.wait(timeout=2.0)
                        else:  # Unix系统
                            # 先尝试SIGTERM
                            os.kill(self.camera_detection_process.pid, signal.SIGTERM)
                            # 等待进程终止，最多等待2秒
                            self.camera_detection_process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        # 如果超时，强制终止
                        log_manager.log_system_event("摄像头检测", "强制终止摄像头检测进程")
                        try:
                            if os.name == 'nt':
                                self.camera_detection_process.kill()
                            else:
                                os.kill(self.camera_detection_process.pid, signal.SIGKILL)
                        except Exception as kill_error:
                            log_manager.log_error(f"强制终止进程失败: {str(kill_error)}")
                    except Exception as terminate_error:
                        log_manager.log_error(f"终止进程失败: {str(terminate_error)}")
                    
                    # 关闭管道以防止资源泄漏
                    try:
                        self.camera_detection_process.stdout.close()
                        self.camera_detection_process.stderr.close()
                    except Exception as close_error:
                        log_manager.log_error(f"关闭进程管道失败: {str(close_error)}")
                    
                    log_manager.log_system_event("摄像头检测", "摄像头检测进程已停止")
                    self.camera_detection_process = None
                
                self.camera_detection_running = False
                
                # 清空检测历史
                self.detection_history.clear()
            
            return True
        except Exception as e:
            log_manager.log_error(f"停止摄像头检测失败: {str(e)}")
            log_manager.log_error(traceback.format_exc())  # 添加详细的堆栈跟踪
            try:
                with self.lock:
                    self.camera_detection_running = False
                    self.camera_detection_process = None
            except Exception:
                pass
            return False
    
    def detect(self, frame):
        """执行目标检测
        
        Args:
            frame: 输入图像帧
            
        Returns:
            dict: 检测结果，包含检测到的物体信息
        """
        # 为了兼容原API，调用detect_frame方法
        return self.detect_frame(frame)
    
    def detect_frame(self, frame):
        """执行单帧目标检测（新增方法，更清晰地表明是处理单帧）
        
        Args:
            frame: 输入图像帧
            
        Returns:
            dict: 检测结果，包含检测到的物体信息
        """
        if self.model is None:
            log_manager.log_error("检测失败: 模型未加载")
            return {"objects": []}
        
        try:
            # 准备图像（调整大小、归一化等）
            img = self._prepare_image(frame)
            
            # 执行推理
            with torch.no_grad():
                pred = self.model(img, augment=self.augment)[0]
            
            # 应用非极大值抑制
            pred = self.non_max_suppression(
                pred, 
                conf_thres=self.confidence_threshold, 
                iou_thres=self.iou_threshold, 
                classes=self.relevant_classes if self.relevant_classes else None,
                agnostic=self.agnostic_nms,
                max_det=self.max_det
            )
            
            # 处理检测结果
            detection_result = self._process_detection_results(pred, frame)
            
            # 应用ROI筛选
            detection_result = self._apply_roi_filtering(detection_result, frame)
            
            # 根据配置决定是否应用连续多帧验证
            if self.enable_frame_validation:
                detection_result = self._apply_frame_validation(detection_result)
            
            # 规则优化：
            # 1. 对person类的边界框进行二次判断：若边界框边缘与屏蔽门间隙重叠（结合ROI），
            #    判定为"肢体可能被夹"
            # 2. 对小尺寸目标（面积<50x50像素），即使不属于上述类别，也标记为"疑似细小异物"
            detection_result = self._apply_rule_optimization(detection_result, frame)
            
            # 触发检测结果回调，使用回调锁确保线程安全
            with self.callback_lock:
                callbacks = self.detection_callbacks.copy()
            
            for callback in callbacks:
                try:
                    callback(detection_result)
                except Exception as e:
                    log_manager.log_error(f"检测回调执行失败: {e}")
            
            # 检查是否检测到物体并且在ROI内
            try:
                if detection_result['objects'] and signal_handler and hasattr(signal_handler, 'get_current_state'):
                    current_state = signal_handler.get_current_state()
                    
                    # 只在关门中和已关闭状态下进行检测（已关闭状态会在2秒后由signal_handler自动停止）
                    if current_state in [SystemState.CLOSING, SystemState.CLOSED]:
                        # 筛选出ROI内的物体
                        roi_objects = []
                        if self.roi:
                            roi_x1, roi_y1, roi_x2, roi_y2 = self.roi
                            for obj in detection_result['objects']:
                                # 检查物体是否在ROI内或与ROI相交
                                obj_x1, obj_y1, obj_x2, obj_y2 = obj['x1'], obj['y1'], obj['x2'], obj['y2']
                                
                                # 计算物体中心
                                obj_center_x = (obj_x1 + obj_x2) // 2
                                obj_center_y = (obj_y1 + obj_y2) // 2
                                
                                # 检查物体中心是否在ROI内，或者物体与ROI相交
                                if (roi_x1 <= obj_center_x <= roi_x2 and roi_y1 <= obj_center_y <= roi_y2) or \
                                   not (obj_x2 < roi_x1 or obj_x1 > roi_x2 or obj_y2 < roi_y1 or obj_y1 > roi_y2):
                                    roi_objects.append(obj)
                        else:
                            # 没有设置ROI时，所有物体都有效
                            roi_objects = detection_result['objects']
                        
                        # 只有当ROI内有物体时才触发报警
                        if roi_objects:
                            # 整合检测到的物体信息
                            detected_objects_info = []
                            primary_object = None
                            
                            # 优先显示人员或最可能造成危险的物体
                            for obj in roi_objects:
                                obj_info = {
                                    "type": obj['class_name'],
                                    "confidence": obj['confidence'],
                                    "position": f"({obj['x1']}, {obj['y1']})-({obj['x2']}, {obj['y2']})"
                                }
                                detected_objects_info.append(obj_info)
                                
                                # 优先选择人员作为主要物体，其次是其他高风险物体
                                if primary_object is None:
                                    if obj['class_id'] == 0:  # person
                                        primary_object = obj
                                    elif 'special_note' in obj:
                                        primary_object = obj
                                    else:
                                        primary_object = obj
                            
                            # 格式化位置信息 - 使用ROI中心作为位置标识
                            roi_center_x = (self.roi[0] + self.roi[2]) // 2 if self.roi else 0
                            roi_center_y = (self.roi[1] + self.roi[3]) // 2 if self.roi else 0
                            
                            # 构建位置描述（根据ROI坐标）
                            if self.roi:
                                roi_x1, roi_y1, roi_x2, roi_y2 = self.roi
                                position = f"屏蔽门间隙区域 [X:{roi_x1}-{roi_x2}, Y:{roi_y1}-{roi_y2}] (中心点: {roi_center_x}, {roi_center_y})"
                            else:
                                position = "全画面"
                            
                            # 获取主要物体的类型
                            object_type = primary_object['class_name'] if primary_object else "未知物体"
                            # 添加特殊标记
                            if primary_object and 'special_note' in primary_object:
                                object_type += f" ({primary_object['special_note']})"
                            
                            # 统计各类物体数量
                            type_counts = {}
                            for obj in roi_objects:
                                type_name = obj['class_name']
                                if 'special_note' in obj:
                                    type_name += f" ({obj['special_note']})"
                                type_counts[type_name] = type_counts.get(type_name, 0) + 1
                            
                            # 构建更详细的异物种类描述
                            detailed_object_types = "、".join([f"{t}({count}个)" for t, count in type_counts.items()])
                            
                            # 构建符合UI需求的报警信息格式
                            alarm_info = {
                                "alarm_type": "异物检测",
                                "position": position,  # 使用位置字段名
                                "object_type": detailed_object_types,  # 使用详细异物种类字段名
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),  # 直接生成时间戳
                                "objects": detected_objects_info,  # 详细物体信息
                                "detail": f"检测到{len(roi_objects)}个物体",
                                # 兼容旧格式
                                "location": position,
                                "type": detailed_object_types
                            }
                        
                        if hasattr(signal_handler, 'trigger_alarm'):
                            signal_handler.trigger_alarm(alarm_info)
                            log_manager.log_system_event("报警触发", f"检测到异物并触发报警: {object_type} 在 {position}")
            except Exception as alarm_error:
                log_manager.log_error(f"触发报警失败: {str(alarm_error)}")
                log_manager.log_error(traceback.format_exc())
            
            return detection_result
        
        except Exception as e:
            log_manager.log_error(f"检测过程错误: {e}")
            return {"objects": []}
    
    def _prepare_image(self, frame):
        """准备图像用于模型推理
        
        Args:
            frame: 原始图像
            
        Returns:
            torch.Tensor: 处理后的图像张量
        """
        # 使用从load_model中保存的letterbox函数
        # 调整图像大小
        img = self.letterbox(frame, self.img_size)[0]
        
        # 转换颜色通道 BGR -> RGB
        img = img[:, :, ::-1].transpose(2, 0, 1)  # HWC to CHW
        img = np.ascontiguousarray(img)
        
        # 转换为张量并归一化
        img = torch.from_numpy(img).to(self.device)
        img = img.float()
        img /= 255.0
        
        # 添加批次维度
        if img.ndimension() == 3:
            img = img.unsqueeze(0)
        
        return img
    
    def _process_detection_results(self, pred, frame):
        """处理检测结果
        
        Args:
            pred: 模型输出的预测结果
            frame: 原始图像
            
        Returns:
            dict: 处理后的检测结果
        """
        objects = []
        
        # 处理每个预测
        for i, det in enumerate(pred):
            if det is not None and len(det):
                # 获取原始图像尺寸
                h, w = frame.shape[:2]
                
                # 直接使用scale_coords函数将预测结果从模型尺寸映射回原始图像尺寸
                det[:, :4] = self.scale_coords((self.img_size, self.img_size), det[:, :4], (h, w)).round()
                
                # 提取检测到的物体信息
                for *xyxy, conf, cls in reversed(det):
                    x1, y1, x2, y2 = map(int, xyxy)
                    class_id = int(cls)
                    confidence = float(conf)
                    
                    # 获取类别名称
                    class_name = self.class_names.get(class_id, f'class_{class_id}')
                    
                    # 计算物体面积
                    area = (x2 - x1) * (y2 - y1)
                    
                    # 添加到结果列表
                    objects.append({
                        'class_id': class_id,
                        'class_name': class_name,
                        'confidence': confidence,
                        'x1': x1,
                        'y1': y1,
                        'x2': x2,
                        'y2': y2,
                        'area': area
                    })
        
        return {"objects": objects}
    
    def _scale_coords(self, img_size, coords, img0_shape):
        """将坐标从模型尺寸缩放回原始图像尺寸
        
        Args:
            img_size: 模型输入尺寸
            coords: 坐标
            img0_shape: 原始图像尺寸
            
        Returns:
            缩放后的坐标
        """
        # 使用scale_coords函数（已在load_model中保存的引用）
        return self.scale_coords(img_size, coords, img0_shape)
    
    def _clip_coords(self, coords, img_shape):
        """裁剪坐标到图像边界内
        
        Args:
            coords: 坐标
            img_shape: 图像尺寸
            
        Returns:
            裁剪后的坐标
        """
        coords[:, 0].clamp_(0, img_shape[1])  # x1
        coords[:, 1].clamp_(0, img_shape[0])  # y1
        coords[:, 2].clamp_(0, img_shape[1])  # x2
        coords[:, 3].clamp_(0, img_shape[0])  # y2
        
        return coords
    
    def _apply_roi_filtering(self, detection_result, frame):
        """应用ROI筛选，只保留ROI区域内的检测结果
        
        Args:
            detection_result: 检测结果
            frame: 原始图像
            
        Returns:
            筛选后的检测结果
        """
        if not self.roi:
            return detection_result
        
        roi_x1, roi_y1, roi_x2, roi_y2 = self.roi
        filtered_objects = []
        
        for obj in detection_result['objects']:
            obj_x1, obj_y1, obj_x2, obj_y2 = obj['x1'], obj['y1'], obj['x2'], obj['y2']
            
            # 对于地铁屏蔽门间隙检测场景，使用更严格的ROI判断逻辑
            # 检查物体中心点是否在ROI内或物体大部分在ROI内
            obj_center_x = (obj_x1 + obj_x2) / 2
            obj_center_y = (obj_y1 + obj_y2) / 2
            
            # 计算物体与ROI的交集
            intersect_x1 = max(obj_x1, roi_x1)
            intersect_y1 = max(obj_y1, roi_y1)
            intersect_x2 = min(obj_x2, roi_x2)
            intersect_y2 = min(obj_y2, roi_y2)
            
            # 检查是否有交集
            if intersect_x1 < intersect_x2 and intersect_y1 < intersect_y2:
                # 计算交集面积占物体面积的比例
                obj_area = (obj_x2 - obj_x1) * (obj_y2 - obj_y1)
                intersect_area = (intersect_x2 - intersect_x1) * (intersect_y2 - intersect_y1)
                overlap_ratio = intersect_area / obj_area
                
                # 对于地铁屏蔽门场景，我们对人员和小物体采用不同的判断标准
                # 人员（class_id=0）和小物体需要更严格的检测，只要部分在ROI内就保留
                if obj['class_id'] == 0 or obj['area'] < self.small_object_area_threshold:
                    # 人员或小物体，重叠比例>0.2就保留
                    if overlap_ratio > 0.2:
                        # 记录物体在ROI中的位置信息
                        obj['roi_position'] = f"中心点({int(obj_center_x)}, {int(obj_center_y)})"
                        filtered_objects.append(obj)
                else:
                    # 其他物体，重叠比例>0.5才保留
                    if overlap_ratio > 0.5:
                        obj['roi_position'] = f"中心点({int(obj_center_x)}, {int(obj_center_y)})"
                        filtered_objects.append(obj)
        
        log_manager.log_system_event("ROI筛选", f"原始检测到{len(detection_result['objects'])}个物体，ROI内保留{len(filtered_objects)}个物体")
        return {"objects": filtered_objects}
    
    def set_enable_frame_validation(self, enable):
        """设置是否启用多帧验证
        
        Args:
            enable: 是否启用多帧验证
        """
        self.enable_frame_validation = enable
        if not enable:
            # 如果禁用多帧验证，清空历史记录
            self.detection_history.clear()
            log_manager.log_system_event("多帧验证设置", "多帧验证已禁用")
        else:
            log_manager.log_system_event("多帧验证设置", "多帧验证已启用，需要连续{}帧检测到同一物体".format(self.frame_validation_count))
            
    def get_enable_frame_validation(self):
        """获取当前是否启用多帧验证
        
        Returns:
            bool: 是否启用多帧验证
        """
        return self.enable_frame_validation
        
    def _apply_frame_validation(self, detection_result):
        """应用连续多帧验证
        
        Args:
            detection_result: 当前帧的检测结果
            
        Returns:
            验证后的检测结果
        """
        # 将当前检测结果添加到历史记录
        self.detection_history.append(detection_result['objects'])
        
        # 如果历史记录不足，则直接返回当前结果
        if len(self.detection_history) < self.frame_validation_count:
            return detection_result
        
        # 统计每个物体在连续帧中的出现次数
        object_counts = {}
        
        for frame_objects in self.detection_history:
            for obj in frame_objects:
                # 使用类别ID和位置信息生成物体的唯一标识
                obj_key = (obj['class_id'], obj['x1'], obj['y1'], obj['x2'], obj['y2'])
                object_counts[obj_key] = object_counts.get(obj_key, 0) + 1
        
        # 只保留在连续帧中出现次数达到阈值的物体
        validated_objects = []
        current_objects = {}
        
        # 为当前帧的物体创建索引
        for obj in detection_result['objects']:
            obj_key = (obj['class_id'], obj['x1'], obj['y1'], obj['x2'], obj['y2'])
            current_objects[obj_key] = obj
        
        # 验证物体
        for obj_key, count in object_counts.items():
            if count >= self.frame_validation_count and obj_key in current_objects:
                validated_objects.append(current_objects[obj_key])
        
        return {"objects": validated_objects}
    
    def _apply_rule_optimization(self, detection_result, frame):
        """应用规则优化
        
        Args:
            detection_result: 检测结果
            frame: 原始图像
            
        Returns:
            优化后的检测结果
        """
        optimized_objects = []
        
        for obj in detection_result['objects']:
            # 1. 对person类的边界框进行二次判断：若边界框边缘与屏蔽门间隙重叠（结合ROI），
            #    判定为"肢体可能被夹"
            if obj['class_id'] == 0:  # person类
                if self.roi and self._is_near_roi_edge(obj, self.roi):
                    obj['special_note'] = "肢体可能被夹"
            
            # 2. 对小尺寸目标（面积<50x50像素），标记为"疑似细小异物"
            if self.enable_small_object_detection and obj['area'] < self.small_object_area_threshold:
                if 'special_note' not in obj:
                    obj['special_note'] = "疑似细小异物"
                else:
                    obj['special_note'] += "; 疑似细小异物"
            
            optimized_objects.append(obj)
        
        # 额外的小物体检测逻辑可以在这里添加
        # 例如，对原始图像进行处理，检测可能被漏检的小物体
        
        return {"objects": optimized_objects}
    
    def _is_near_roi_edge(self, obj, roi, threshold=20):
        """检查物体是否靠近ROI边缘
        
        Args:
            obj: 物体信息
            roi: ROI区域坐标 [x1, y1, x2, y2]
            threshold: 距离阈值
            
        Returns:
            bool: 是否靠近ROI边缘
        """
        roi_x1, roi_y1, roi_x2, roi_y2 = roi
        obj_x1, obj_y1, obj_x2, obj_y2 = obj['x1'], obj['y1'], obj['x2'], obj['y2']
        
        # 检查物体是否靠近ROI的左右边缘
        near_left_edge = obj_x1 <= roi_x1 + threshold
        near_right_edge = obj_x2 >= roi_x2 - threshold
        
        # 对于地铁屏蔽门场景，我们更关注左右边缘（门的间隙）
        return near_left_edge or near_right_edge
    
    def update_settings(self, settings):
        """更新检测设置
        
        Args:
            settings: 设置参数字典
        """
        with self.lock:
            # 更新基本参数
            if "weights" in settings:
                self.weights_path = settings["weights"]
                self.load_model()  # 重新加载模型
            
            if "confidence_threshold" in settings:
                self.confidence_threshold = settings["confidence_threshold"]
            
            if "iou_threshold" in settings:
                self.iou_threshold = settings["iou_threshold"]
            
            if "max_det" in settings:
                self.max_det = settings["max_det"]
            
            if "relevant_classes" in settings:
                self.relevant_classes = settings["relevant_classes"]
            
            if "frame_validation_count" in settings:
                self.frame_validation_count = settings["frame_validation_count"]
                # 更新历史记录队列大小
                self.detection_history = deque(self.detection_history, maxlen=self.frame_validation_count)
            
            if "augment" in settings:
                self.augment = settings["augment"]
            
            if "agnostic_nms" in settings:
                self.agnostic_nms = settings["agnostic_nms"]
            
            if "roi" in settings:
                self.roi = settings["roi"]
            
            if "enable_small_object_detection" in settings:
                self.enable_small_object_detection = settings["enable_small_object_detection"]
            
            if "small_object_area_threshold" in settings:
                self.small_object_area_threshold = settings["small_object_area_threshold"]
        
        log_manager.log_system_event("检测参数更新", f"已更新检测参数: {settings}")


# 创建全局检测管理器实例
detection_manager = DetectionManager()