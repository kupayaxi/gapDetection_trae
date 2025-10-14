import sys
import os

# 清理文件中的空字节
def clean_null_bytes(file_path):
    # 以二进制模式读取文件
    with open(file_path, 'rb') as f:
        content = f.read()
    
    # 移除空字节
    content = content.replace(b'\x00', b'')
    
    # 以二进制模式写回文件
    with open(file_path, 'wb') as f:
        f.write(content)
    
    print(f"已清理文件 {file_path} 中的空字节")

# 清理多个可能有问题的文件
files_to_clean = [
    "src/signal_handler/signal_handler.py",
    "src/video_capture/video_capturer.py",
    "src/config/config_manager.py",
    "src/logger/log_manager.py",
    "src/object_detection/detection_manager.py",
    "src/gui/main_window.py"
]

for file in files_to_clean:
    full_path = os.path.join(os.path.dirname(__file__), file)
    if os.path.exists(full_path):
        clean_null_bytes(full_path)
    else:
        print(f"文件不存在: {full_path}")

print("清理完成！")