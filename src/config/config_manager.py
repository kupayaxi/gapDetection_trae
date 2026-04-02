import logging
import os
from pathlib import Path

import yaml

# 设置日志记录器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ConfigManager:
    """配置管理器，负责加载、保存和提供系统配置."""

    def __init__(self, config_path=None):
        """初始化配置管理器.

        Args:
            config_path: 配置文件路径，默认使用当前目录下的config.yaml
        """
        # 首先检查当前目录下的config.yaml
        if config_path is None:
            # 尝试多个可能的配置文件路径
            possible_paths = [
                Path.cwd() / "config.yaml",  # 当前工作目录
                Path(__file__).parent.parent.parent / "config.yaml",  # 相对于模块的路径
            ]

            # 找到第一个存在的配置文件
            found_path = None
            for path in possible_paths:
                if path.exists():
                    found_path = path
                    break

            # 如果找到了配置文件，使用它；否则使用默认路径
            self.config_path = found_path.resolve() if found_path else (Path.cwd() / "config.yaml").resolve()
        else:
            self.config_path = Path(config_path).resolve()

        # 记录正在使用的配置文件路径，用于调试
        logger.info(f"正在使用配置文件: {self.config_path}")

        self.config = self._load_default_config()

        # 如果配置文件存在，强制从文件加载配置，直接替换而不是合并
        if self.config_path.exists():
            try:
                with open(self.config_path, encoding="utf-8") as f:
                    loaded_config = yaml.safe_load(f)
                    if loaded_config:
                        # 记录加载的配置，用于调试
                        logger.info(f"从配置文件加载的配置: {loaded_config}")
                        self.config = loaded_config  # 直接替换整个配置字典
            except Exception as e:
                logger.error(f"加载配置文件失败: {e}")
        else:
            # 否则保存默认配置
            self.save_config()
            logger.info(f"配置文件不存在，已创建默认配置: {self.config_path}")

    def _load_default_config(self):
        """加载默认配置."""
        return {
            "video": {
                "source": 0,  # 摄像头ID或视频文件路径
                "width": 1280,
                "height": 720,
                "fps": 30,
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
                "agnostic_nms": False,
            },
            "log": {
                "file_path": "logs/detection_log.csv",
                "max_file_size": 10,  # MB
                "backup_count": 5,
            },
            "ui": {
                "show_confidence": True,
                "show_labels": True,
                "line_thickness": 2,
                "alarm_sound": True,
                "update_interval_ms": 100,  # 更新间隔（毫秒）
            },
        }

    def load_config(self):
        """从文件加载配置."""
        try:
            with open(self.config_path, encoding="utf-8") as f:
                loaded_config = yaml.safe_load(f)
                if loaded_config:
                    # 深度合并配置，保留默认值中不存在于文件中的项
                    self._merge_config(self.config, loaded_config)
            return True
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            return False

    def save_config(self):
        """保存配置到文件."""
        try:
            # 确保目录存在
            os.makedirs(self.config_path.parent, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"配置已保存到: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False

    def _merge_config(self, base, update):
        """深度合并配置字典."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._merge_config(base[key], value)
            else:
                base[key] = value

    def get(self, key_path, default=None):
        """获取配置项.

        Args:
            key_path: 配置项的路径，使用点号分隔，例如 "detection.confidence_threshold"
            default: 默认值，如果配置项不存在则返回

        Returns:
            配置项的值或默认值
        """
        keys = key_path.split(".")
        value = self.config

        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default

    def set(self, key_path, value):
        """设置配置项.

        Args:
            key_path: 配置项的路径，使用点号分隔，例如 "detection.confidence_threshold"
            value: 配置项的新值
        """
        keys = key_path.split(".")
        config = self.config

        # 导航到目标配置项的父级
        for key in keys[:-1]:
            if key not in config:
                config[key] = {}
            elif not isinstance(config[key], dict):
                # 如果中间路径不是字典，将其转换为字典
                config[key] = {}
            config = config[key]

        # 设置目标配置项的值
        config[keys[-1]] = value

    def update_config(self, new_config):
        """批量更新配置.

        Args:
            new_config: 新的配置字典
        """
        self._merge_config(self.config, new_config)
        self.save_config()


# 创建全局配置管理器实例
config_manager = ConfigManager()
