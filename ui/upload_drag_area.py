"""
自定义拖拽上传区域组件
"""
import os
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, pyqtSignal


class UploadDragArea(QFrame):
    """自定义拖拽上传区域，支持 Hover 状态高亮与点击事件"""
    
    files_dropped = pyqtSignal(list)  # 拖入的文件/文件夹路径列表
    clicked = pyqtSignal()            # 点击区域信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("UploadDragArea")
        self.init_ui()
        
    def init_ui(self):
        # 垂直布局
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        
        # 提示图标 (使用大 Emoji 或图片，这里使用大 Emoji 呈现拟物风格)
        self.icon_label = QLabel("📥")
        self.icon_label.setStyleSheet("font-size: 42pt; margin-bottom: 5px;")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)
        
        # 主提示语
        self.text_label = QLabel("将本地文件或文件夹拖拽到此处")
        self.text_label.setStyleSheet("font-size: 13pt; font-weight: bold; color: #2C3E50;")
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.text_label)
        
        # 副提示语
        self.sub_text_label = QLabel("或者 点击此处选择文件 / 文件夹")
        self.sub_text_label.setStyleSheet("font-size: 10pt; color: #7F8C8D;")
        self.sub_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.sub_text_label)
        
        # 默认样式系统 - 现代扁平设计风格与微妙的圆角投影
        self.set_default_style()
        
    def set_default_style(self):
        self.setStyleSheet("""
            #UploadDragArea {
                border: 2px dashed #BDC3C7;
                border-radius: 12px;
                background-color: #F8F9FA;
                min-height: 180px;
            }
            #UploadDragArea:hover {
                border-color: #3498DB;
                background-color: #EBF5FB;
            }
        """)
        
    def set_active_style(self):
        # 拖入文件时的激活样式 (亮蓝色，粗虚线)
        self.setStyleSheet("""
            #UploadDragArea {
                border: 3px dashed #3498DB;
                border-radius: 12px;
                background-color: #EBF5FB;
                min-height: 180px;
            }
        """)
        
    # ------------------------------------------------------------------
    # 拖拽事件处理
    # ------------------------------------------------------------------
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.set_active_style()
            
    def dragLeaveEvent(self, event):
        self.set_default_style()
        
    def dropEvent(self, event):
        self.set_default_style()
        urls = event.mimeData().urls()
        
        paths = []
        for url in urls:
            path = url.toLocalFile()
            if path and os.path.exists(path):
                paths.append(path)
                
        if paths:
            self.files_dropped.emit(paths)
            
    # ------------------------------------------------------------------
    # 点击事件处理
    # ------------------------------------------------------------------
    
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
        else:
            super().mousePressEvent(event)
