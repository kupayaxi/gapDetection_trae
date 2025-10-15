import csv
import os
import logging
from datetime import datetime
import sys
from pathlib import Path

# 导入配置管理器 - 使用延迟导入避免相对导入问题
_config_manager = None

def _get_config_manager():
    global _config_manager
    if _config_manager is None:
        try:
            from config.config_manager import config_manager
            _config_manager = config_manager
        except ImportError:
            try:
                from src.config.config_manager import config_manager
                _config_manager = config_manager
            except ImportError:
                print("警告：无法导入config_manager，使用默认配置")
                class DefaultConfigManager:
                    def get_log_config(self):
                        return {"log_level": "INFO", "log_file": os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "system.log")}
                    def get(self, key, default=None):
                        return default
                _config_manager = DefaultConfigManager()
    return _config_manager

class LogManager:
    """日志管理模块，负责记录系统日志和检测结果"""
    
    def __init__(self, log_file=None):
        """初始化日志管理器
        
        Args:
            log_file: 日志文件路径，如果不指定则从配置中读取
        """
        # 获取配置管理器
        config_mgr = _get_config_manager()
        
        if log_file is None:
            log_file = getattr(config_mgr, 'get', lambda key, default=None: default)("log.file_path", "logs/detection_log.csv")
        self.log_file = Path(log_file)
        self.max_file_size = getattr(config_mgr, 'get', lambda key, default=None: default)("log.max_file_size", 10)  # MB
        self.backup_count = getattr(config_mgr, 'get', lambda key, default=None: default)("log.backup_count", 5)
        
        # 确保日志目录存在
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        
        # 初始化日志文件
        self.initialize_log_file()
    
    def initialize_log_file(self):
        """初始化日志文件，创建文件并写入表头"""
        if not os.path.exists(self.log_file):
            with open(self.log_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(["时间戳", "事件类型", "详细信息"])
    
    def check_rotate_log(self):
        """检查并执行日志轮转"""
        if os.path.exists(self.log_file):
            file_size = os.path.getsize(self.log_file) / (1024 * 1024)  # 转换为MB
            if file_size >= self.max_file_size:
                # 执行日志轮转
                self.rotate_log()
    
    def rotate_log(self):
        """执行日志文件轮转"""
        # 关闭当前日志文件
        
        # 删除最旧的备份文件（如果达到备份数量上限）
        for i in range(self.backup_count - 1, 0, -1):
            old_backup = f"{self.log_file}.{i}"
            new_backup = f"{self.log_file}.{i+1}"
            if os.path.exists(old_backup):
                if os.path.exists(new_backup):
                    os.remove(new_backup)
                os.rename(old_backup, new_backup)
        
        # 将当前日志文件重命名为第一个备份
        if os.path.exists(self.log_file):
            os.rename(self.log_file, f"{self.log_file}.1")
        
        # 创建新的日志文件
        self.initialize_log_file()
    
    def log(self, event_type, details):
        """记录日志
        
        Args:
            event_type: 事件类型
            details: 详细信息
        """
        # 检查日志轮转
        self.check_rotate_log()
        
        # 获取当前时间戳
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 写入日志
        try:
            with open(self.log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow([timestamp, event_type, details])
            return True
        except Exception as e:
            print(f"写入日志失败: {e}")
            return False
    
    def log_system_event(self, event_type, details):
        """记录系统事件
        
        Args:
            event_type: 事件类型
            details: 详细信息
        """
        return self.log(event_type, details)
    
    def log_detection(self, detection_result, signal_state):
        """记录检测结果
        
        Args:
            detection_result: 检测结果字典，包含检测到的物体信息
            signal_state: 当前信号状态
        """
        # 格式化检测结果
        detected_objects = []
        for obj in detection_result.get('objects', []):
            obj_info = f"[{obj['class_name']}] 置信度:{obj['confidence']:.2f} 位置:{obj['x1']},{obj['y1']},{obj['x2']},{obj['y2']}"
            detected_objects.append(obj_info)
        
        details = f"状态:{signal_state.name} 检测到{len(detected_objects)}个对象: {'; '.join(detected_objects)}"
        return self.log("检测事件", details)
    
    def log_signal_change(self, old_state, new_state):
        """记录信号状态变化
        
        Args:
            old_state: 旧状态
            new_state: 新状态
        """
        details = f"状态从{old_state.name}变为{new_state.name}"
        return self.log("信号变化", details)
    
    def log_error(self, error_message):
        """记录错误信息
        
        Args:
            error_message: 错误信息
        """
        return self.log("错误", error_message)
    
    def export_logs(self, start_time=None, end_time=None, export_format="csv", export_path=None):
        """导出日志
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            export_format: 导出格式，目前仅支持csv
            export_path: 导出文件路径
            
        Returns:
            导出成功返回True，失败返回False
        """
        if export_format != "csv":
            print(f"不支持的导出格式: {export_format}")
            return False
        
        if export_path is None:
            export_path = f"logs/export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        try:
            # 确保导出目录存在
            os.makedirs(os.path.dirname(export_path), exist_ok=True)
            
            with open(self.log_file, 'r', encoding='utf-8') as source, \
                 open(export_path, 'w', newline='', encoding='utf-8') as dest:
                reader = csv.reader(source)
                writer = csv.writer(dest)
                
                # 写入表头
                header = next(reader)
                writer.writerow(header)
                
                # 写入数据行
                for row in reader:
                    if not row:
                        continue
                    
                    # 检查时间范围
                    if start_time or end_time:
                        row_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                        if start_time and row_time < start_time:
                            continue
                        if end_time and row_time > end_time:
                            continue
                    
                    writer.writerow(row)
            
            return True
        except Exception as e:
            print(f"导出日志失败: {e}")
            return False
    
    def query_logs(self, query_params):
        """查询日志
        
        Args:
            query_params: 查询参数字典，支持 event_type, start_time, end_time, keyword
            
        Returns:
            查询结果列表
        """
        results = []
        
        try:
            with open(self.log_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                # 跳过表头
                next(reader)
                
                for row in reader:
                    if not row:
                        continue
                    
                    # 检查事件类型
                    if 'event_type' in query_params and row[1] != query_params['event_type']:
                        continue
                    
                    # 检查时间范围
                    if 'start_time' in query_params or 'end_time' in query_params:
                        row_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
                        if 'start_time' in query_params and row_time < query_params['start_time']:
                            continue
                        if 'end_time' in query_params and row_time > query_params['end_time']:
                            continue
                    
                    # 检查关键词
                    if 'keyword' in query_params and query_params['keyword'].lower() not in row[2].lower():
                        continue
                    
                    # 添加到结果列表
                    results.append({
                        'timestamp': row[0],
                        'event_type': row[1],
                        'details': row[2]
                    })
            
            return results
        except Exception as e:
            print(f"查询日志失败: {e}")
            return []

# 创建全局日志管理器实例
log_manager = LogManager()