"""
新增方法存根 - 稍后实现
"""

def create_local_path_section_stub(self):
    """创建本地路径选择区域（简化版）"""
    from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
    
    group = QGroupBox("💾 本地目标")
    layout = QVBoxLayout()
    
    # 本地文件夹选择
    folder_layout = QHBoxLayout()
    folder_layout.addWidget(QLabel("保存到:"))
    self.local_folder_input = QLineEdit()
    self.local_folder_input.setPlaceholderText("选择本地文件夹...")
    folder_layout.addWidget(self.local_folder_input)
    
    browse_button = QPushButton("📁 浏览")
    browse_button.clicked.connect(self.browse_local_folder)
    folder_layout.addWidget(browse_button)
    
    layout.addLayout(folder_layout)
    group.setLayout(layout)
    return group


def create_scan_progress_section_stub(self):
    """创建扫描进度区域"""
    from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QProgressBar
    
    group = QGroupBox("📊 扫描进度")
    layout = QVBoxLayout()
    
    # 扫描状态标签
    self.scan_status_label = QLabel("等待开始...")
    layout.addWidget(self.scan_status_label)
    
    # 扫描进度条
    self.scan_progress_bar = QProgressBar()
    self.scan_progress_bar.setTextVisible(False)
    self.scan_progress_bar.setRange(0, 0)  # 不确定进度模式
    layout.addWidget(self.scan_progress_bar)
    
    group.setLayout(layout)
    group.setVisible(False)  # 默认隐藏
    return group
