import sys
import logging
import threading
import signal
import os
import traceback
import time

# 配置根日志记录器
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("application.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# 确保src目录在Python路径中
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 定义系统退出处理函数
def handle_system_exit(sig, frame):
    """处理系统退出信号"""
    logger.info("收到退出信号，正在关闭系统...")
    sys.exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, handle_system_exit)
signal.signal(signal.SIGTERM, handle_system_exit)

def main():
    """主函数"""
    try:
        logger.info("开始导入系统模块...")
        
        # 导入配置管理器
        from src.config.config_manager import config_manager
        logger.info("config_manager 导入成功")
        
        # 确保配置文件存在
        if not os.path.exists(config_manager.config_path):
            logger.info(f"配置文件不存在，创建默认配置: {config_manager.config_path}")
            config_manager.save_config()
        
        # 导入日志管理器
        from src.logger.log_manager import log_manager
        logger.info("log_manager 导入成功")
        log_manager.log_system_event("系统启动", "地铁屏蔽门间隙检测系统正在启动...")
        
        # 导入信号处理器
        from src.signal_handler.signal_handler import signal_handler, SystemState
        logger.info("signal_handler 导入成功")
        
        # 导入视频捕获器
        from src.video_capture.video_capturer import video_capturer
        logger.info("video_capturer 导入成功")
        
        # 导入检测管理器
        from src.object_detection.detection_manager import detection_manager
        logger.info("detection_manager 导入成功")
        
        # 导入GUI主窗口
        from src.gui.main_window import MainWindow
        logger.info("MainWindow 导入成功")
        
        # 注册状态变化回调函数，控制摄像头检测
        def state_change_callback(old_state, new_state):
            """处理系统状态变化，控制摄像头检测"""
            log_manager.log_system_event("状态变化", f"从 {old_state} 切换到 {new_state}")
            
            # 当系统进入关门状态时，启动摄像头检测
            if new_state == SystemState.CLOSING:
                log_manager.log_system_event("检测控制", "收到关门命令，开始摄像头实时检测")
                # 启动视频捕获器（如果尚未启动）
                if not video_capturer.is_running():
                    video_capturer.start_capture(0)  # 使用默认摄像头
                # 启动摄像头检测
                detection_manager.start_camera_detection()
            # 当系统从关门状态切换到已关闭状态时，延迟2秒后停止检测
            elif old_state == SystemState.CLOSING and new_state == SystemState.CLOSED:
                log_manager.log_system_event("检测控制", "收到已关闭信号，将在2秒后停止检测")
                
                def delayed_stop_detection():
                    """延迟停止检测的线程函数"""
                    time.sleep(2)
                    log_manager.log_system_event("检测控制", "延迟时间到，停止摄像头实时检测")
                    detection_manager.stop_camera_detection()
                    # 不再停止视频捕获，保持摄像头预览功能
                    # if video_capturer.is_running():
                    #     video_capturer.stop_capture()
                
                # 创建并启动延迟停止线程
                stop_thread = threading.Thread(target=delayed_stop_detection, daemon=True)
                stop_thread.start()
            # 其他情况下的处理
            elif new_state == SystemState.IDLE:
                # 确保检测已停止
                if detection_manager.camera_detection_running:
                    detection_manager.stop_camera_detection()
                if video_capturer.is_running():
                    video_capturer.stop_capture()
        
        # 注册状态变化回调
        signal_handler.register_state_change_callback(state_change_callback)
        
        logger.info("所有模块导入成功，准备启动GUI...")
        
        # 创建PyQt应用
        from PyQt5.QtWidgets import QApplication
        
        app = QApplication(sys.argv)
        
        # 初始化主窗口
        main_window = MainWindow()
        main_window.show()
        
        logger.info("GUI已启动")
        
        # 运行应用
        sys.exit(app.exec_())
        
    except Exception as e:
        logger.error(f"系统启动失败: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)

if __name__ == "__main__":
    main()