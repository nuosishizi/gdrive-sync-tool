"""
素材上传后台工作线程
"""
import os
from PyQt6.QtCore import QThread, pyqtSignal
from core.rclone_wrapper import RcloneStats


class RcloneUploadWorker(QThread):
    """素材上传工作线程 - 顺序上传队列中的所有文件/文件夹"""
    
    item_started = pyqtSignal(int)              # 当前开始上传的项索引
    item_progress = pyqtSignal(int, object)      # 单项上传进度: 索引, RcloneStats
    item_finished = pyqtSignal(int, bool, str)  # 单项上传完成: 索引, 是否成功, 状态消息
    overall_progress = pyqtSignal(float, float, float)  # 总体进度: 进度百分比(0-100), 速度(bytes/s), 剩余时间(s)
    queue_finished = pyqtSignal(bool)           # 队列上传结束: 是否全部成功
    log = pyqtSignal(str, str)                  # 日志信号: 消息, 前缀
    
    def __init__(self, rclone_wrapper, upload_items, remote_folder_id):
        """
        Args:
            rclone_wrapper: RcloneWrapper 实例
            upload_items: 待上传列表，每个元素为 dict: {
                'path': str,       # 本地绝对路径
                'is_dir': bool,    # 是否为文件夹
                'name': str,       # 显示名称
                'size': int        # 大小（字节）
            }
            remote_folder_id: GDrive 目标文件夹 ID
        """
        super().__init__()
        self.rclone_wrapper = rclone_wrapper
        self.upload_items = upload_items
        self.remote_folder_id = remote_folder_id
        
        self.should_stop = False
        
        # 总体进度计算所需变量
        self.total_bytes = sum(max(0, item['size']) for item in upload_items)
        self.completed_bytes = 0
        self.current_item_index = -1
        self.any_errors = False
        
    def run(self):
        self.log.emit("开始上传队列...", "ℹ")
        
        for idx, item in enumerate(self.upload_items):
            if self.should_stop:
                self.log.emit("上传被用户取消", "⏹")
                break
                
            self.current_item_index = idx
            self.item_started.emit(idx)
            
            local_path = item['path']
            is_dir = item['is_dir']
            item_size = max(0, item['size'])
            
            self.log.emit(f"正在上传 ({idx+1}/{len(self.upload_items)}): {item['name']}", "🔄")
            
            def on_item_progress(stats):
                if self.should_stop:
                    return
                # 单个文件进度
                self.item_progress.emit(idx, stats)
                
                # 计算整体进度
                cur_transferred = stats.bytes_transferred
                overall_transferred = self.completed_bytes + cur_transferred
                
                pct = 0.0
                if self.total_bytes > 0:
                    pct = min(100.0, (overall_transferred / self.total_bytes) * 100.0)
                else:
                    # 如果总大小为 0 (如只有空文件夹)，上传中设置为 50%
                    pct = 50.0
                
                self.overall_progress.emit(pct, stats.speed, stats.eta)
            
            # 执行底层上传
            success = self.rclone_wrapper.upload_item(
                local_path=local_path,
                remote_folder_id=self.remote_folder_id,
                is_dir=is_dir,
                progress_callback=on_item_progress,
                event_callback=self.on_rclone_event,
                stop_flag=lambda: self.should_stop,
                log_callback=lambda msg, pref: self.log.emit(msg, pref)
            )
            
            if success:
                self.completed_bytes += item_size
                self.item_finished.emit(idx, True, "已完成")
                self.log.emit(f"✓ 上传完成: {item['name']}", "✓")
            else:
                self.any_errors = True
                self.item_finished.emit(idx, False, "失败")
                self.log.emit(f"✗ 上传失败: {item['name']}", "✗")
                
            # 单个文件结束后，同步总体进度
            overall_pct = 0.0
            if self.total_bytes > 0:
                overall_pct = min(100.0, (self.completed_bytes / self.total_bytes) * 100.0)
            elif idx == len(self.upload_items) - 1:
                overall_pct = 100.0
            self.overall_progress.emit(overall_pct, 0.0, 0.0)
            
        self.queue_finished.emit(not self.any_errors)
        
    def on_rclone_event(self, event_type, message, level):
        # 传递底层详细事件
        pass
        
    def stop(self):
        """停止上传"""
        self.should_stop = True
        if self.rclone_wrapper:
            self.rclone_wrapper.stop()
