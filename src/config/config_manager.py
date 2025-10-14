import yaml
import os
from pathlib import Path


class ConfigManager:
    """配置管理器，负责加载、保存和提供系统配置"""
    
    def __init__(self, config_path=None):
        """初始化配置管理器
        
        Args:
            config_path: 配置文件路径，默认使用当前目录下的config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config.yaml"
        self.config_path = config_path
        self.config = self._load_default_config()
        
        # 如果配置文件存在，加载配置
        if os.path.exists(config_path):
            self.load_config()
        else:
            # 否则保存默认配置
            self.save_config()
    
    def _load_default_config(self):
        """加载默认配置"""
        return {
            "video": {
                "source": 0,  # 摄像头ID或视频文件路径
                "width": 1280,
                "height": 720,
                "fps": 30
            },
            "detection": {
                "weights": "yolov5s.pt",
                "confidence_threshold": 0.4,
                "iou_threshold": 0.45,
                "max_det": 1000,
                # 按优先级排序的地铁夹人夹物场景相关类别ID
                "relevant_classes": [0, 24, 25, 26, 28, 39, 41, 67, 27, 77],
                # 缺失类别的规则补充
                "enable_small_object_detection": True,
                "small_object_area_threshold": 2500,  # 小物体面积阈值（50x50像素）
                "frame_validation_count": 2,
                "roi": [300, 200, 900, 500],  # [x1, y1, x2, y2]
                "augment": False,
                "agnostic_nms": False
            },
            "log": {
                "file_path": "logs/detection_log.csv",
                "max_file_size": 10,  # MB
                "backup_count": 5
            },
            "ui": {
                "show_confidence": True,
                "show_labels": True,
                "line_thickness": 2,
                "alarm_sound": True,
                "update_interval_ms": 100  # 更新间隔（毫秒）
            }
        }
    
    def load_config(self):
        """从文件加载配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                loaded_config = yaml.safe_load(f)
                if loaded_config:
                    # 深度合并配置，保留默认值中不存在于文件中的项
                    self._merge_config(self.config, loaded_config)
            return True
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return False
    
    def save_config(self):
        """保存配置到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False
    
    def _merge_config(self, base, update):
        """深度合并配置字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value
    
    def get(self, key_path, default=None):
        """获取配置项
        
        Args:
            key_path: 配置键路径，支持点表示法，如 "detection.confidence_threshold"
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        keys = key_path.split('.')
        value = self.config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def set(self, key_path, value):
        """设置配置项
        
        Args:
            key_path: 配置键路径，支持点表示法，如 "detection.confidence_threshold"
            value: 配置值
        """
        keys = key_path.split('.')
        config = self.config
        
        # 遍历键路径，直到最后一个键
        for key in keys[:-1]:
            if key not in config or not isinstance(config[key], dict):
                config[key] = {}
            config = config[key]
        
        # 设置最后一个键的值
        config[keys[-1]] = value
    
    def update_config(self, new_config):
        """批量更新配置
        
        Args:
            new_config: 新的配置字典
        """
        self._merge_config(self.config, new_config)
        self.save_config()


# 创建全局配置管理器实例
config_manager = ConfigManager()