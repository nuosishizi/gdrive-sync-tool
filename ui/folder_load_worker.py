"""
Google Drive 文件夹加载 Worker (QThread)
真正的异步加载，不阻塞UI
"""

from PyQt6.QtCore import QThread, pyqtSignal
import subprocess


class FolderLoadWorker(QThread):
    """异步加载文件夹的 Worker"""
    
    # 信号
    folders_loaded = pyqtSignal(list)  # 加载完成，发送文件夹列表
    load_error = pyqtSignal(str)  # 加载错误
    
    def __init__(self, rclone_wrapper, folder_id="root"):
        super().__init__()
        self.rclone_wrapper = rclone_wrapper
        self.folder_id = folder_id
        
    def run(self):
        """在后台线程执行"""
        try:
            # 构建命令
            cmd = [
                self.rclone_wrapper.rclone_path,
                "lsjson",
                "gdrive:",
                "--config", self.rclone_wrapper.config_path,
                "--max-depth", "1"
            ]
            
            if self.folder_id and self.folder_id != "root":
                cmd.extend(["--drive-root-folder-id", self.folder_id])
            
            # 执行命令（在后台线程，不阻塞UI）
            result = subprocess.run(
                cmd,
                capture_output=True,
                encoding='utf-8',
                errors='ignore',
                timeout=15
            )
            
            if result.returncode == 0:
                import json
                all_items = json.loads(result.stdout)
                # 文件夹在前，文件在后，同类按名称排序
                folders = sorted([i for i in all_items if i.get('IsDir')], key=lambda x: x.get('Name','').lower())
                files   = sorted([i for i in all_items if not i.get('IsDir')], key=lambda x: x.get('Name','').lower())
                self.folders_loaded.emit(folders + files)
            else:
                self.load_error.emit(f"Rclone 错误: {result.stderr}")
                
        except subprocess.TimeoutExpired:
            self.load_error.emit("加载超时（15秒）")
        except Exception as e:
            self.load_error.emit(str(e))
