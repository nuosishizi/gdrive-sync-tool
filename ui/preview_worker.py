"""
Preview Worker - 异步预览文件列表
防止大文件夹崩溃
"""

from PyQt6.QtCore import QThread, pyqtSignal
import subprocess
import json


class PreviewWorker(QThread):
    """异步预览文件Worker"""
    
    # 信号
    files_loaded = pyqtSignal(list, int, int)  # 文件列表, 总数, 总大小
    progress_update = pyqtSignal(str)  # 进度消息
    error_occurred = pyqtSignal(str)  # 错误消息
    
    def __init__(self, rclone_wrapper, folder_id, max_files=1000):
        super().__init__()
        self.rclone_wrapper = rclone_wrapper
        self.folder_id = folder_id
        self.max_files = max_files
        self.should_stop = False
        
    def run(self):
        """在后台线程执行"""
        try:
            self.progress_update.emit("正在扫描文件夹...")
            
            # 构建命令 - 只列出文件，不递归子文件夹
            cmd = [
                self.rclone_wrapper.rclone_path,
                "lsjson",
                "gdrive:",
                "--files-only",  # 只显示文件
                "--config", self.rclone_wrapper.config_path,
                "--max-depth", "1"  # 不递归
            ]
            
            if self.folder_id and self.folder_id != "root":
                cmd.extend(["--drive-root-folder-id", self.folder_id])
            
            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30
            )
            
            if result.returncode == 0:
                files = json.loads(result.stdout)
                total_count = len(files)
                total_size = sum(f.get('Size', 0) for f in files)
                
                # 限制显示数量
                if total_count > self.max_files:
                    self.progress_update.emit(f"文件过多，只显示前 {self.max_files} 个")
                    files = files[:self.max_files]
                
                # 发送结果
                self.files_loaded.emit(files, total_count, total_size)
            else:
                self.error_occurred.emit(f"预览失败: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            self.error_occurred.emit("预览超时（30秒）")
        except Exception as e:
            self.error_occurred.emit(f"预览错误: {e}")
