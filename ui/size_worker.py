"""
本地目录大小后台计算线程
"""
import os
from PyQt6.QtCore import QThread, pyqtSignal


class SizeCalculatorWorker(QThread):
    """计算本地文件夹或文件大小的工作线程 (防止阻塞 UI 线程)"""
    
    # 信号: 元素索引, 计算出的字节数
    size_calculated = pyqtSignal(int, int)
    
    def __init__(self, items_to_calculate):
        """
        Args:
            items_to_calculate: 列表，每个项为 (index, path, is_dir)
        """
        super().__init__()
        self.items = items_to_calculate
        self.should_stop = False
        
    def run(self):
        for idx, path, is_dir in self.items:
            if self.should_stop:
                break
                
            if not os.path.exists(path):
                self.size_calculated.emit(idx, 0)
                continue
                
            if is_dir:
                dir_size = self.get_dir_size(path)
                self.size_calculated.emit(idx, dir_size)
            else:
                try:
                    file_size = os.path.getsize(path)
                    self.size_calculated.emit(idx, file_size)
                except Exception:
                    self.size_calculated.emit(idx, 0)
                    
    def get_dir_size(self, folder_path):
        """递归计算文件夹大小"""
        total = 0
        try:
            for entry in os.scandir(folder_path):
                if self.should_stop:
                    return 0
                try:
                    if entry.is_file(follow_symlinks=False):
                        total += entry.stat().st_size
                    elif entry.is_dir(follow_symlinks=False):
                        total += self.get_dir_size(entry.path)
                except OSError:
                    # 忽略无法访问的文件/文件夹
                    pass
        except Exception:
            pass
        return total
        
    def stop(self):
        """停止计算"""
        self.should_stop = True
