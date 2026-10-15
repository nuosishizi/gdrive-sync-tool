"""
主窗口 - Google Drive 同步工具
"""
import sys
import os
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QProgressBar, QTextEdit, QGroupBox, QFileDialog,
    QComboBox, QMessageBox, QLineEdit, QTabWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QListWidget,
    QListWidgetItem
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QBrush
from datetime import datetime
from ui.folder_browser import GDriveFolderBrowser
from database.models import SyncTask
from ui.upload_drag_area import UploadDragArea
from ui.upload_worker import RcloneUploadWorker
from ui.size_worker import SizeCalculatorWorker


def _get_item_icon(is_dir: bool, mime: str = "") -> str:
    """Return emoji icon for a Google Drive item based on type."""
    if is_dir:
        return "📁"
    if not mime:
        return "📄"
    if "spreadsheet" in mime or "excel" in mime:
        return "📊"
    if "document" in mime or "word" in mime:
        return "📄"
    if "presentation" in mime or "powerpoint" in mime:
        return "📑"
    if "pdf" in mime:
        return "📋"
    if "image" in mime:
        return "🖼"
    if "video" in mime:
        return "🎬"
    if "audio" in mime:
        return "🎵"
    if "zip" in mime or "compress" in mime:
        return "🗜"
    return "📄"


class RcloneSyncWorker(QThread):
    """Rclone同步工作线程"""
    progress = pyqtSignal(object)  # RcloneStats
    finished = pyqtSignal(bool)  # success
    log = pyqtSignal(str, str)  # message, prefix
    file_event = pyqtSignal(str, str, str)  # type, message, level
    
    def __init__(self, rclone_wrapper, remote_path, local_path):
        super().__init__()
        self.rclone_wrapper = rclone_wrapper
        self.remote_path = remote_path
        self.local_path = local_path
        self.should_stop = False
        self.is_paused = False
    
    def run(self):
        """执行同步"""
        try:
            self.log.emit("🔄 正在扫描云端文件...", "ℹ")
            
            # 执行同步
            success = self.rclone_wrapper.sync_folder(
                remote_path=self.remote_path,
                local_path=self.local_path,
                progress_callback=self.on_progress,
                event_callback=self.on_event,
                stop_flag=lambda: self.should_stop,
                log_callback=lambda msg, prefix: self.log.emit(msg, prefix)
            )
            
            self.finished.emit(success)
        except Exception as e:
            self.log.emit(f"同步异常: {e}", "✗")
            import traceback
            traceback.print_exc()
            self.finished.emit(False)
    
    def on_event(self, type, message, level):
        """处理文件事件"""
        self.file_event.emit(type, message, level)
    
    def on_progress(self, stats):
        """进度回调"""
        if not self.is_paused:
            self.progress.emit(stats)
    
    def stop(self):
        """停止同步"""
        self.should_stop = True
        if self.rclone_wrapper:
            self.rclone_wrapper.stop()
    
    def pause(self):
        """暂停同步（停止进程，稍后可恢复）"""
        self.is_paused = True
        self.log.emit("⏸ 正在暂停同步...", "ℹ")
        if self.rclone_wrapper:
            self.rclone_wrapper.stop()
    
    def resume(self):
        """恢复同步（重新启动，Rclone会跳过已下载文件）"""
        self.is_paused = False
        self.log.emit("▶ 正在恢复同步...", "ℹ")
        # 注意：恢复需要重新创建worker并启动


class MainWindow(QMainWindow):
    """主窗口"""
    
    def __init__(self):
        super().__init__()
        self.gdrive_client = None
        self.db = None
        self.sync_engine = None
        self.rclone_wrapper = None  # 新增：Rclone包装器
        self.current_task_id = None
        self.sync_worker = None
        
        # 统计变量
        self.total_files = 0
        self.completed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        
        # 选中的 Google Drive 文件夹
        self.selected_gdrive_folder_id = ""
        self.selected_gdrive_folder_name = ""
        
        # 配置文件路径
        self.config_file = "config/app_config.json"
        
        self.init_ui()
        self.load_settings()  # 加载设置
        
        # 延迟初始化Rclone，确保UI先显示出来，进度条才不会卡死
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(100, self.init_rclone)
        
        # 启动自动更新检查器（静默后台，8秒后首次检查）
        from core.auto_updater import AutoUpdater
        self._auto_updater = AutoUpdater(self)
        self._auto_updater.start()
    
    def init_rclone(self):
        """初始化Rclone包装器"""
        try:
            from core.rclone_wrapper import RcloneWrapper
            
            # 检测rclone.exe路径
            if getattr(sys, 'frozen', False):
                # 打包环境下
                # 1. 优先检查 exe 同级目录 (方便用户替换 rclone)
                exe_dir = os.path.dirname(sys.executable)
                rclone_path = os.path.join(exe_dir, "rclone.exe")
                
                if not os.path.exists(rclone_path):
                    # 2. 检查临时目录 (如果打包进去了)
                    if hasattr(sys, '_MEIPASS'):
                        rclone_path_temp = os.path.join(sys._MEIPASS, "rclone.exe")
                        if os.path.exists(rclone_path_temp):
                            rclone_path = rclone_path_temp
            else:
                # 开发环境下
                rclone_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rclone.exe")
            
            # 不提前判断是否存在，直接初始化，让RcloneWrapper去处理自动下载
            self.log(f"正在初始化并在必要时自动部署 Rclone...", "⚙")
            
            from PyQt6.QtWidgets import QProgressDialog, QApplication
            from PyQt6.QtCore import Qt
            
            progress_dialog = None
            
            def download_cb(status, current, total):
                nonlocal progress_dialog
                if not progress_dialog:
                    progress_dialog = QProgressDialog("正在为您首次下载依赖 (rclone)...", "取消", 0, total, self)
                    progress_dialog.setWindowTitle("下载必要组件")
                    progress_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
                    progress_dialog.setMinimumDuration(0)
                    progress_dialog.show()

                if status == "downloading":
                    if total > 0:
                        progress_dialog.setMaximum(total)
                        progress_dialog.setValue(current)
                elif status == "extracting":
                    progress_dialog.setLabelText("正在解压组件，请稍候...")
                    progress_dialog.setMaximum(0)
                    progress_dialog.setValue(0)
                    
                QApplication.processEvents()
            
            self.rclone_wrapper = RcloneWrapper(
                rclone_path=rclone_path,
                config_path="config/rclone.conf",
                download_callback=download_cb
            )
            
            if progress_dialog:
                progress_dialog.close()
                
            version = self.rclone_wrapper.get_version()
            self.log(f"Rclone已就绪: {version}", "✓")
            self.log(f"Rclone路径: {self.rclone_wrapper.rclone_path}", "ℹ")
            
            # 检查是否已有配置（不测试连接，避免超时）
            if os.path.exists(self.rclone_wrapper.config_path):
                self.log("✓ Rclone 配置已存在", "✓")
                
                # 获取用户信息（快速）
                user_info = self.rclone_wrapper.get_user_info("gdrive")
                email = user_info.get("email", "")
                
                if email:
                    self.log(f"✓ 已授权账号: {email}", "✓")
                    self.auth_status_label.setText(f"● 已连接: {email}")
                    self.auth_status_label.setStyleSheet("color: green; font-weight: bold;")
                else:
                    self.log("配置存在但无用户信息", "⚠")
                    self.auth_status_label.setText("● 已配置（未验证）")
                    self.auth_status_label.setStyleSheet("color: orange;")
                
                # 直接启用所有功能（不测试连接）
                self.start_button.setEnabled(True)
                self.preview_button.setEnabled(True)
                self.rclone_auth_button.setText("🔄 重新授权")
            else:
                self.log("未找到 Rclone 配置，请先授权", "ℹ")
                
        except Exception as e:
            self.log(f"Rclone初始化失败: {e}", "✗")
            import traceback
            traceback.print_exc()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("Google Drive 同步与上传工具")
        self.setGeometry(100, 100, 1200, 700)
        
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局 - 包含 QSplitter
        main_layout = QHBoxLayout()
        main_widget.setLayout(main_layout)
        
        from PyQt6.QtWidgets import QSplitter
        from PyQt6.QtCore import Qt
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # === 左侧面板 - 来源和目标 === (常驻显示)
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        # 1. 授权状态
        auth_group = self.create_auth_section()
        left_layout.addWidget(auth_group)
        
        # 2. Google Drive 来源树
        gdrive_tree_group = self.create_gdrive_tree_panel()
        left_layout.addWidget(gdrive_tree_group, 1)  # 拉伸占据剩余空间
        
        # 3. 本地目标路径与任务管理
        local_group = self.create_local_path_section()
        left_layout.addWidget(local_group)
        
        # === 右侧面板 - 标签页 ===
        self.tab_widget = QTabWidget()
        
        # --- Tab 1. 下载同步 ---
        download_tab = QWidget()
        download_layout = QVBoxLayout()
        download_tab.setLayout(download_layout)
        
        # 1. 同步控制
        control_group = self.create_control_section()
        download_layout.addWidget(control_group)
        
        # 2. 扫描进度
        scan_progress_group = self.create_scan_progress_section()
        download_layout.addWidget(scan_progress_group)
        
        # 3. 传输进度
        transfer_progress_group = self.create_progress_section()
        download_layout.addWidget(transfer_progress_group)
        
        # 4. 日志
        log_group = self.create_log_section()
        download_layout.addWidget(log_group, 1)  # 拉伸占据剩余空间
        
        self.tab_widget.addTab(download_tab, "📥 下载同步")
        
        # --- Tab 2. 素材上传 ---
        # 初始化素材上传变量
        self.upload_queue = []
        self.upload_worker = None
        self.size_workers = []
        self.selected_upload_gdrive_folder_id = "root"
        self.selected_upload_gdrive_folder_name = "我的云端硬盘"
        
        upload_tab = self.create_upload_tab()
        self.tab_widget.addTab(upload_tab, "📤 素材上传")
        
        # 将左侧面板和右侧标签页添加到水平分割器中
        splitter.addWidget(left_panel)
        splitter.addWidget(self.tab_widget)
        splitter.setSizes([450, 750])  # 左侧小一点，右侧大一点


    def create_auth_section(self):
        """创建授权区域"""
        group = QGroupBox("授权状态")
        status_layout = QHBoxLayout()
        
        # Rclone 授权状态
        self.auth_status_label = QLabel("● Rclone: 未授权")
        self.auth_status_label.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.auth_status_label)
        status_layout.addStretch()
        
        
        # 统一授权按钮（Rclone 完成所有功能）
        self.rclone_auth_button = QPushButton("🔑 授权 Google Drive")
        self.rclone_auth_button.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.rclone_auth_button.clicked.connect(self.authorize_rclone)
        status_layout.addWidget(self.rclone_auth_button)
        
        group.setLayout(status_layout)
        return group
    
    def create_config_section(self):
        """创建同步配置区域"""
        group = QGroupBox("同步配置")
        layout = QVBoxLayout()
        
        # Google Drive 来源路径显示
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Google Drive 来源:"))
        self.gdrive_source_label = QLabel("未选择")
        self.gdrive_source_label.setStyleSheet("color: gray; font-style: italic;")
        source_layout.addWidget(self.gdrive_source_label, 1)
        layout.addLayout(source_layout)
        
        # 本地文件夹
        local_layout = QHBoxLayout()
        local_layout.addWidget(QLabel("本地目标文件夹:"))
        self.local_folder_input = QLineEdit()
        self.local_folder_input.setPlaceholderText("选择本地文件夹...")
        local_layout.addWidget(self.local_folder_input)
        self.browse_local_button = QPushButton("浏览本地...")
        self.browse_local_button.clicked.connect(self.browse_local_folder)
        local_layout.addWidget(self.browse_local_button)
        layout.addLayout(local_layout)
        
        # 任务选择
        task_layout = QHBoxLayout()
        task_layout.addWidget(QLabel("当前任务:"))
        self.task_combo = QComboBox()
        self.task_combo.addItem("默认任务")
        self.task_combo.currentIndexChanged.connect(self.on_task_changed)
        task_layout.addWidget(self.task_combo)
        self.task_manager_button = QPushButton("任务管理")
        self.task_manager_button.clicked.connect(self.open_task_manager)
        task_layout.addWidget(self.task_manager_button)
        layout.addLayout(task_layout)
        
        group.setLayout(layout)
        return group
    
    def create_control_section(self):
        """创建同步控制区域"""
        group = QGroupBox("同步控制")
        layout = QHBoxLayout()
        
        self.start_button = QPushButton("▶ 开始同步")
        self.start_button.clicked.connect(self.start_sync)
        self.start_button.setEnabled(False)
        
        self.pause_button = QPushButton("⏸ 暂停")
        self.pause_button.clicked.connect(self.pause_sync)
        self.pause_button.setEnabled(False)
        
        self.stop_button = QPushButton("⏹ 停止")
        self.stop_button.clicked.connect(self.stop_sync)
        self.stop_button.setEnabled(False)
        
        self.preview_button = QPushButton("📋 预览")
        self.preview_button.clicked.connect(self.preview_sync)
        self.preview_button.setEnabled(False)
        
        self.settings_button = QPushButton("⚙ 设置")
        self.settings_button.clicked.connect(self.open_settings)
        
        layout.addWidget(self.start_button)
        layout.addWidget(self.pause_button)
        layout.addWidget(self.stop_button)
        layout.addWidget(self.preview_button)
        layout.addWidget(self.settings_button)
        layout.addStretch()
        
        group.setLayout(layout)
        return group
    
    def create_progress_section(self):
        """创建进度显示区域 (高级版 - 强制更新)"""
        from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QProgressBar, QTextEdit, QHBoxLayout
        from PyQt6.QtCore import Qt
        
        group = QGroupBox("📈 详细传输进度")
        layout = QVBoxLayout()
        
        # 1. 顶部状态栏 (速度 | 剩余时间)
        status_layout = QHBoxLayout()
        self.status_label = QLabel("准备就绪")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        self.speed_label = QLabel("🚀 0.0 MB/s")
        self.speed_label.setStyleSheet("font-weight: bold; color: #2196F3;")
        status_layout.addWidget(self.speed_label)
        layout.addLayout(status_layout)
        
        # 2. 总体进度条
        self.current_progress = QProgressBar()
        self.current_progress.setFixedHeight(15)
        self.current_progress.setTextVisible(True)
        self.current_progress.setFormat("%p%")
        layout.addWidget(self.current_progress)
        
        # 2.5 详细统计信息 (新增)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(15)
        
        self.stats_total_files = QLabel("📂 总文件: -")
        self.stats_total_size = QLabel("💾 总大小: -")
        self.stats_completed = QLabel("✅ 已完成: -")
        self.stats_failed = QLabel("❌ 失败: -")
        self.stats_failed.setStyleSheet("color: #C62828;")
        
        stats_layout.addWidget(self.stats_total_files)
        stats_layout.addWidget(self.stats_total_size)
        stats_layout.addWidget(self.stats_completed)
        stats_layout.addWidget(self.stats_failed)
        stats_layout.addStretch()
        
        layout.addLayout(stats_layout)
        
        # 3. 正在传输列表 (QTableWidget)
        layout.addWidget(QLabel("正在传输的文件:"))
        
        from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView
        
        self.file_table = QTableWidget()
        self.file_table.setRowCount(10)
        self.file_table.setColumnCount(5)
        self.file_table.setHorizontalHeaderLabels(["文件名", "大小", "进度", "速度", "状态"])
        
        # 样式设置
        self.file_table.verticalHeader().setVisible(False) # 隐藏行号
        self.file_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection) # 禁止选择
        self.file_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers) # 禁止编辑
        self.file_table.setFocusPolicy(Qt.FocusPolicy.NoFocus) # 禁止焦点
        self.file_table.setAlternatingRowColors(True) # 交替行颜色
        
        # 列表高度固定
        row_height = 25
        header_height = 25
        # 10行 + 表头 + 少量边距
        total_height = (row_height * 10) + header_height + 2
        self.file_table.setFixedHeight(total_height)
        
        # 列宽设置 (固定比例)
        # 总宽假设 ~680 (在700的右侧面板里)
        # 文件名(300), 大小(80), 进度(80), 速度(100), 状态(80)
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch) # 文件名自适应
        self.file_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.file_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.file_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.file_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        
        self.file_table.setColumnWidth(1, 80)
        self.file_table.setColumnWidth(2, 60)
        self.file_table.setColumnWidth(3, 90)
        self.file_table.setColumnWidth(4, 80)
        
        # 预填充空行以保持稳定
        for r in range(10):
            self.file_table.setRowHeight(r, row_height)
            for c in range(5):
                item = QTableWidgetItem("")
                self.file_table.setItem(r, c, item)
            
        self.file_table.setStyleSheet("""
            QTableWidget {
                background-color: white;
                border: 1px solid #ddd;
                font-family: 'Segoe UI', sans-serif;
                font-size: 9pt;
            }
            QHeaderView::section {
                background-color: #f0f0f0;
                padding: 4px;
                border: none;
                border-bottom: 1px solid #ddd;
                font-weight: bold;
                color: #333;
            }
        """)
        
        layout.addWidget(self.file_table)
        
        # 4. 传输日志 (列表控件，支持滚动)
        layout.addWidget(QLabel("传输事件日志 (最近1000条):"))
        from PyQt6.QtWidgets import QListWidget
        self.transfer_log = QListWidget()
        self.transfer_log.setUniformItemSizes(True) # 优化性能
        self.transfer_log.setMinimumHeight(200)
        self.transfer_log.setStyleSheet("""
            QListWidget { 
                font-family: 'Consolas', monospace; 
                font-size: 9pt;
                background-color: #fafafa;
                border: 1px solid #ddd;
            }
            QListWidget::item {
                border-bottom: 1px solid #eee;
                padding: 2px;
            }
        """)
        layout.addWidget(self.transfer_log)
        
        group.setLayout(layout)
        return group
    
    def create_log_section(self):
        """创建日志区域"""
        group = QGroupBox("日志")
        layout = QVBoxLayout()
        
        # 日志文本框
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        layout.addWidget(self.log_text)
        
        # 导出按钮
        export_layout = QHBoxLayout()
        export_layout.addStretch()
        self.export_log_button = QPushButton("导出 CSV")
        self.export_log_button.clicked.connect(self.export_log)
        export_layout.addWidget(self.export_log_button)
        layout.addLayout(export_layout)
        
        group.setLayout(layout)
        return group
    
    def set_components(self, gdrive_client, db, sync_engine):
        """设置组件（从外部注入）"""
        self.gdrive_client = gdrive_client
        self.db = db
        self.sync_engine = sync_engine
        
        # 自动检查授权状态
        self.check_auth_status()
    
    def check_auth_status(self):
        """检查授权状态"""
        try:
            if self.gdrive_client and os.path.exists(self.gdrive_client.token_path):
                # 尝试静默认证
                if self.gdrive_client.authenticate():
                    user_info = self.gdrive_client.get_user_info()
                    email = user_info.get('emailAddress', '未知用户')
                    self.auth_status_label.setText(f"● 已连接: {email}")
                    self.auth_status_label.setStyleSheet("color: green; font-weight: bold;")
                    if hasattr(self, 'browse_gdrive_button'):
                        self.browse_gdrive_button.setEnabled(True)
                    self.start_button.setEnabled(True)
                    self.preview_button.setEnabled(True)
                    self.log(f"自动加载授权: {email}", "✓")
                    
                    # 自动生成Rclone配置（如果不存在）
                    if self.rclone_wrapper and not os.path.exists(self.rclone_wrapper.config_path):
                        self.log("正在生成Rclone配置...", "⚙")
                        if self.rclone_wrapper.auto_setup_from_gdrive_client(self.gdrive_client):
                            self.log("Rclone配置生成成功", "✓")
        except Exception as e:
            # 静默失败，用户可以手动授权
            print(f"自动授权检查失败: {e}")
    
    def load_settings(self):
        """加载设置"""
        try:
            if os.path.exists(self.config_file):
                import json
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 恢复上次的文件夹设置
                folder_id = config.get('gdrive_folder', '')
                folder_name = config.get('gdrive_folder_name', folder_id) # 兼容
                
                if folder_id:
                    self.selected_gdrive_folder_id = folder_id
                    self.selected_gdrive_folder_name = folder_name
                    self.selected_upload_gdrive_folder_id = folder_id
                    self.selected_upload_gdrive_folder_name = folder_name
                    
                    if folder_id == "root":
                        display = "📁 我的云端硬盘（整个网盘）"
                    else:
                        display = f"📁 {folder_name}"
                        
                    if hasattr(self, 'gdrive_source_label'):
                        self.gdrive_source_label.setText(display)
                        self.gdrive_source_label.setStyleSheet("color: green; font-weight: bold;")
                        
                    if hasattr(self, 'upload_target_label'):
                        self.upload_target_label.setText(display)
                        self.upload_target_label.setStyleSheet("color: green; font-weight: bold;")


                self.local_folder_input.setText(config.get('local_folder', ''))
                
                print(f"已加载上次的配置")
        except Exception as e:
            print(f"加载配置失败: {e}")
    
    def save_settings(self):
        """保存设置"""
        try:
            import json
            config = {
                'gdrive_folder': getattr(self, 'selected_gdrive_folder_id', ''),
                'gdrive_folder_name': getattr(self, 'selected_gdrive_folder_name', ''),
                'local_folder': self.local_folder_input.text()
            }
            
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")
    
    def log(self, message: str, prefix: str = "ℹ"):
        """添加日志"""
        from datetime import datetime # Ensure datetime is imported for this method
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = f"[{timestamp}] {prefix} {message}"
        self.log_text.append(log_entry)
    
    def on_authenticate(self):
        """Google API 授权（用于浏览文件夹）"""
        try:
            if not self.gdrive_client:
                QMessageBox.warning(self, "提示", "GDrive 客户端未初始化")
                return
            
            self.log("正在启动 Google API OAuth2 授权...", "🔑")
            
            if self.gdrive_client.authenticate():
                user_info = self.gdrive_client.get_user_info()
                email = user_info.get('emailAddress', '未知用户')
                
                self.log(f"✓ Google API 授权成功: {email}", "✓")
                
                if hasattr(self, 'browse_gdrive_button'):
                    self.browse_gdrive_button.setEnabled(True)
                self.preview_button.setEnabled(True)
                
                QMessageBox.information(
                    self, "授权成功", 
                    f"Google API 授权成功！\n账号: {email}\n\n现在可以浏览云端文件夹了。"
                )
            else:
                self.log("✗ Google API 授权失败", "✗")
                QMessageBox.warning(self, "授权失败", "Google API 授权失败，请重试")
                
        except Exception as e:
            self.log(f"✗ 授权异常: {e}", "✗")
            QMessageBox.critical(self, "错误", f"授权异常:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def browse_gdrive_folder(self):
        """浏览 Google Drive 文件夹（使用树形结构）"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QPushButton, QHBoxLayout, QTreeWidget, QTreeWidgetItem
            from PyQt6.QtCore import Qt
            
            if not self.rclone_wrapper:
                QMessageBox.warning(self, "警告", "请先授权 Rclone")
                return
            
            # 创建浏览对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("浏览 Google Drive - 树形结构")
            dialog.setMinimumSize(700, 500)
            
            layout = QVBoxLayout()
            
            # 树形控件
            tree = QTreeWidget()
            tree.setHeaderLabel("📁 Google Drive 文件夹")
            layout.addWidget(tree)
            
            # 底部按钮
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            # 同步整个网盘按钮
            sync_all_button = QPushButton("✓ 同步整个网盘")
            sync_all_button.clicked.connect(lambda: self.select_folder_from_tree("root", "整个网盘", dialog))
            button_layout.addWidget(sync_all_button)
            
            cancel_button = QPushButton("取消")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            select_button = QPushButton("选择")
            button_layout.addWidget(select_button)
            
            layout.addLayout(button_layout)
            dialog.setLayout(layout)
            
            def load_subfolders(parent_item, folder_id):
                """延迟加载子文件夹"""
                import subprocess
                
                # 构建命令
                cmd = [
                    self.rclone_wrapper.rclone_path,
                    "lsjson",
                    "gdrive:",
                    "--dirs-only",
                    "--config", self.rclone_wrapper.config_path,
                    "--max-depth", "1"
                ]
                
                if folder_id and folder_id != "root":
                    from utils.path_helpers import validate_gdrive_id
                    safe_id = validate_gdrive_id(folder_id)
                    cmd.append(f"--drive-root-folder-id={safe_id}")
                
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        encoding='utf-8',
                        errors='ignore',
                        timeout=15
                    )
                    
                    if result.returncode == 0:
                        import json
                        folders = json.loads(result.stdout)
                        
                        for folder in folders:
                            folder_name = folder.get('Name', '')
                            folder_id_sub = folder.get('ID', '')
                            
                            # 创建子节点
                            child_item = QTreeWidgetItem(parent_item)
                            child_item.setText(0, f"📁 {folder_name}")
                            child_item.setData(0, Qt.ItemDataRole.UserRole, {
                                'id': folder_id_sub,
                                'name': folder_name
                            })
                            
                            # 添加占位符表示可展开
                            placeholder = QTreeWidgetItem(child_item)
                            placeholder.setText(0, "...")
                            
                except Exception as e:
                    self.log(f"加载子文件夹失败: {e}", "⚠")
            
            def on_item_expanded(item):
                """展开节点时加载子文件夹"""
                # 检查是否已加载
                if item.childCount() == 1 and item.child(0).text(0) == "...":
                    # 删除占位符
                    item.takeChild(0)
                    
                    # 加载真实数据
                    data = item.data(0, Qt.ItemDataRole.UserRole)
                    if data and isinstance(data, dict):
                        folder_id = data['id']
                        load_subfolders(item, folder_id)
            
            def on_select():
                """选择文件夹"""
                current_item = tree.currentItem()
                if current_item:
                    data = current_item.data(0, Qt.ItemDataRole.UserRole)
                    if data and isinstance(data, dict):
                        folder_id = data['id']
                        folder_name = data['name']
                        self.select_folder_from_tree(folder_id, folder_name, dialog)
                else:
                    QMessageBox.warning(dialog, "提示", "请选择一个文件夹")
            
            # 连接信号
            tree.itemExpanded.connect(on_item_expanded)
            select_button.clicked.connect(on_select)
            
            # 加载根目录
            self.log("正在加载 Google Drive 根目录...", "📂")
            dialog.show()
            
            # 添加根节点
            root_item = QTreeWidgetItem(tree)
            root_item.setText(0, "📁 我的云端硬盘")
            root_item.setData(0, Qt.ItemDataRole.UserRole, {'id': 'root', 'name': '我的云端硬盘'})
            
            # 加载根目录的子文件夹
            load_subfolders(root_item, "root")
            root_item.setExpanded(True)
            
            self.log("✓ 文件夹树加载完成", "✓")
            
            # 显示对话框
            dialog.exec()
                
        except Exception as e:
            self.log(f"✗ 浏览异常: {e}", "✗")
            QMessageBox.critical(self, "错误", f"浏览文件夹异常:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def select_folder_from_tree(self, folder_id, folder_name, dialog):
        """从树中选择文件夹"""
        self.select_folder_from_tree_embedded(folder_id, folder_name)
        dialog.accept()

    def browse_gdrive_folder(self):
        """浏览 Google Drive 文件夹（使用 Rclone，支持多级导航）"""
        try:
            from PyQt6.QtWidgets import (
                QDialog, QVBoxLayout, QListWidget, QListWidgetItem, 
                QPushButton, QHBoxLayout, QLabel
            )
            
            if not self.rclone_wrapper:
                QMessageBox.warning(self, "警告", "请先授权 Rclone")
                return
            
            # 创建浏览对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("浏览 Google Drive")
            dialog.setMinimumSize(700, 500)
            
            layout = QVBoxLayout()
            
            # 路径导航栏
            nav_layout = QHBoxLayout()
            path_label = QLabel("当前位置: ")
            nav_layout.addWidget(path_label)
            
            current_path_label = QLabel("根目录")
            current_path_label.setStyleSheet("font-weight: bold;")
            nav_layout.addWidget(current_path_label)
            nav_layout.addStretch()
            
            # 返回上级按钮
            back_button = QPushButton("⬆ 返回上级")
            back_button.setEnabled(False)
            nav_layout.addWidget(back_button)
            
            layout.addLayout(nav_layout)
            
            # 文件夹列表
            folder_list = QListWidget()
            layout.addWidget(folder_list)
            
            # 底部按钮
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            # 同步整个网盘按钮
            sync_all_button = QPushButton("✓ 同步整个网盘")
            sync_all_button.clicked.connect(lambda: self.select_root_folder(dialog))
            button_layout.addWidget(sync_all_button)
            
            cancel_button = QPushButton("取消")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            select_button = QPushButton("选择当前文件夹")
            button_layout.addWidget(select_button)
            
            layout.addLayout(button_layout)
            dialog.setLayout(layout)
            
            # 文件夹导航状态
            current_folder_id = ""
            current_folder_name = "根目录"
            folder_stack = []  # 用于返回上级
            
            def load_folders(folder_id="", folder_name="根目录"):
                """加载指定文件夹的子文件夹"""
                nonlocal current_folder_id, current_folder_name
                
                current_folder_id = folder_id
                current_folder_name = folder_name
                current_path_label.setText(folder_name)
                
                folder_list.clear()
                self.log(f"正在加载文件夹: {folder_name}...", "📂")
                
                # 使用 Rclone lsjson 列出文件夹
                import subprocess
                
                # Rclone 浏览时，如果有folder_id，使用 --drive-root-folder-id
                cmd = [
                    self.rclone_wrapper.rclone_path,
                    "lsjson",
                    "gdrive:",  # 总是使用根路径
                    "--dirs-only",
                    "--config", self.rclone_wrapper.config_path,
                    "--max-depth", "1"
                ]
                
                # 如果有文件夹ID，添加参数
                if folder_id:
                    from utils.path_helpers import validate_gdrive_id
                    safe_id = validate_gdrive_id(folder_id)
                    cmd.append(f"--drive-root-folder-id={safe_id}")
                
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    encoding='utf-8',
                    errors='ignore',
                    timeout=30,
                    creationflags=0x08000000 # CREATE_NO_WINDOW
                )
                
                if result.returncode == 0:
                    import json
                    folders = json.loads(result.stdout)
                    
                    if folders:
                        for folder in folders:
                            folder_name_item = folder.get('Name', '')
                            folder_id_item = folder.get('ID', '')
                            
                            item = QListWidgetItem(f"📁 {folder_name_item}")
                            item.setData(Qt.ItemDataRole.UserRole, {
                                'id': folder_id_item,
                                'name': folder_name_item
                            })
                            folder_list.addItem(item)
                        
                        self.log(f"✓ 找到 {len(folders)} 个文件夹", "✓")
                    else:
                        folder_list.addItem("（此文件夹为空）")
                        self.log("此文件夹没有子文件夹", "ℹ")
                else:
                    self.log(f"✗ 加载失败: {result.stderr}", "✗")
                    QMessageBox.critical(dialog, "错误", f"无法加载文件夹:\n{result.stderr}")
            
            def on_folder_double_click(item):
                """双击文件夹进入子文件夹"""
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and isinstance(data, dict):
                    folder_id = data['id']
                    folder_name = data['name']
                    
                    # 保存当前位置到栈
                    folder_stack.append({
                        'id': current_folder_id,
                        'name': current_folder_name
                    })
                    
                    # 加载子文件夹
                    load_folders(folder_id, folder_name)
                    back_button.setEnabled(True)
            
            def go_back():
                """返回上级文件夹"""
                if folder_stack:
                    parent = folder_stack.pop()
                    load_folders(parent['id'], parent['name'])
                    
                    if not folder_stack:
                        back_button.setEnabled(False)
            
            def on_select():
                """选择当前文件夹"""
                selected_items = folder_list.selectedItems()
                if selected_items:
                    data = selected_items[0].data(Qt.ItemDataRole.UserRole)
                    if data and isinstance(data, dict):
                        folder_id = data['id']
                        folder_name = data['name']
                        self.select_folder_from_tree_embedded(folder_id, folder_name)
                        dialog.accept()
                else:
                    # 选择当前文件夹
                    if current_folder_id:
                        self.select_folder_from_tree_embedded(current_folder_id, current_folder_name)
                        dialog.accept()
                    else:
                        QMessageBox.warning(dialog, "提示", "请选择一个文件夹或点击'同步整个网盘'")
            
            # 连接信号
            folder_list.itemDoubleClicked.connect(on_folder_double_click)
            back_button.clicked.connect(go_back)
            select_button.clicked.connect(on_select)
            
            # 初始加载根目录
            load_folders()
            
            # 显示对话框
            dialog.exec()
                
        except subprocess.TimeoutExpired:
            self.log("✗ 加载文件夹超时", "✗")
            QMessageBox.warning(self, "超时", "获取文件夹列表超时\n\n请直接输入文件夹ID")
        except Exception as e:
            self.log(f"✗ 浏览异常: {e}", "✗")
            QMessageBox.critical(self, "错误", f"浏览文件夹异常:\n{str(e)}\n\n请直接输入文件夹ID")
            import traceback
            traceback.print_exc()
    
    def select_root_folder(self, dialog):
        """选择同步整个网盘"""
        self.select_folder_from_tree_embedded("root", "整个网盘")
        dialog.accept()
        """浏览 Google Drive 文件夹（使用 Rclone）"""
        try:
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton, QHBoxLayout
            
            if not self.rclone_wrapper:
                QMessageBox.warning(self, "警告", "请先授权 Rclone")
                return
            
            # 创建浏览对话框
            dialog = QDialog(self)
            dialog.setWindowTitle("浏览 Google Drive")
            dialog.setMinimumSize(600, 400)
            
            layout = QVBoxLayout()
            
            # 文件夹列表
            self.folder_list = QListWidget()
            layout.addWidget(self.folder_list)
            
            # 按钮
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            cancel_button = QPushButton("取消")
            cancel_button.clicked.connect(dialog.reject)
            button_layout.addWidget(cancel_button)
            
            select_button = QPushButton("选择")
            select_button.clicked.connect(dialog.accept)
            button_layout.addWidget(select_button)
            
            layout.addLayout(button_layout)
            dialog.setLayout(layout)
            
            # 加载根目录文件夹
            self.log("正在加载 Google Drive 文件夹列表...", "📂")
            dialog.show()
            
            # 使用 Rclone lsf 列出文件夹
            import subprocess
            result = subprocess.run(
                [
                    self.rclone_wrapper.rclone_path,
                    "lsf",
                    "gdrive:",
                    "--dirs-only",
                    "--config", self.rclone_wrapper.config_path,
                    "--max-depth", "1"
                ],
                capture_output=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30,
                creationflags=0x08000000 # CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                folders = result.stdout.strip().split('\n')
                folders = [f.rstrip('/') for f in folders if f.strip()]
                
                if folders:
                    for folder_name in folders:
                        # 获取文件夹ID
                        # 注意：lsf 只返回名称，需要用 lsjson 获取ID
                        item = QListWidgetItem(f"📁 {folder_name}")
                        item.setData(Qt.ItemDataRole.UserRole, folder_name)
                        self.folder_list.addItem(item)
                    
                    self.log(f"✓ 找到 {len(folders)} 个文件夹", "✓")
                    
                    # 显示对话框
                    if dialog.exec():
                        selected_items = self.folder_list.selectedItems()
                        if selected_items:
                            folder_name = selected_items[0].data(Qt.ItemDataRole.UserRole)
                            
                            # 获取文件夹ID
                            self.log(f"正在获取文件夹 '{folder_name}' 的ID...", "🔍")
                            
                            # 使用 lsjson 获取详细信息包括ID
                            result2 = subprocess.run(
                                [
                                    self.rclone_wrapper.rclone_path,
                                    "lsjson",
                                    "gdrive:",
                                    "--dirs-only",
                                    "--config", self.rclone_wrapper.config_path,
                                    "--max-depth", "1"
                                ],
                                capture_output=True,
                                encoding='utf-8',
                                errors='ignore',
                                timeout=30,
                                creationflags=0x08000000 # CREATE_NO_WINDOW
                            )
                            
                            if result2.returncode == 0:
                                import json
                                items = json.loads(result2.stdout)
                                
                                for item in items:
                                    if item.get('Name') == folder_name and item.get('IsDir'):
                                        folder_id = item.get('ID', '')
                                        if folder_id:
                                            self.select_folder_from_tree_embedded(folder_id, folder_name)
                                            return
                                
                                # 如果没找到ID，使用名称
                                self.log(f"⚠ 未找到ID，无法选择: {folder_name}", "⚠")
                else:
                    self.log("未找到文件夹", "⚠")
                    QMessageBox.information(self, "提示", "未找到任何文件夹\n\n请直接输入文件夹ID")
            else:
                self.log(f"✗ 列出文件夹失败: {result.stderr}", "✗")
                QMessageBox.critical(
                    self, "错误", 
                    f"无法列出文件夹:\n{result.stderr}\n\n请直接输入文件夹ID"
                )
                
        except subprocess.TimeoutExpired:
            self.log("✗ 列出文件夹超时", "✗")
            QMessageBox.warning(self, "超时", "获取文件夹列表超时\n\n请直接输入文件夹ID")
        except Exception as e:
            self.log(f"✗ 浏览异常: {e}", "✗")
            QMessageBox.critical(self, "错误", f"浏览文件夹异常:\n{str(e)}\n\n请直接输入文件夹ID")
            import traceback
            traceback.print_exc()
        """浏览 Google Drive 文件夹"""
        try:
            dialog = GDriveFolderBrowser(self.gdrive_client, self)
            if dialog.exec():
                folder_id, folder_name = dialog.get_selected_folder()
                if folder_id:
                    self.select_folder_from_tree_embedded(folder_id, folder_name)
                    self.log(f"已选择云端文件夹: {folder_name}", "📁")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"浏览文件夹失败:\n{str(e)}")
    
    def browse_local_folder(self):
        """浏览本地文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择本地文件夹")
        if folder:
            self.local_folder_input.setText(folder)
    
    def authorize_rclone(self):
        """授权 Rclone（统一授权：下载+浏览+分享文件）"""
        try:
            import subprocess
            
            # 提示用户
            reply = QMessageBox.question(
                self, 
                ' Rclone 统一授权', 
                '即将打开浏览器进行 Google Drive 授权。\n\n'
                '本次授权将支持：\n'
                '✅ 下载您的文件\n'
                '✅ 下载分享给您的文件\n'
                '✅ 浏览云端文件夹\n\n'
                '这是唯一需要的授权！\n\n'
                '是否继续？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply != QMessageBox.StandardButton.Yes:
                return
            
            self.log("正在启动 Rclone 统一授权...", "🔑")
            
            # 检查 rclone 路径
            if not self.rclone_wrapper:
                QMessageBox.critical(self, "错误", "Rclone 未初始化")
                return
            
            rclone_path = self.rclone_wrapper.rclone_path
            
            # 先杀掉可能残留的 rclone 进程，释放 53682 端口
            # rclone authorize 固定使用 53682 作为 OAuth 回调端口
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", "rclone.exe"],
                    capture_output=True, creationflags=0x08000000
                )
                import time; time.sleep(0.5)  # 等待端口释放
            except Exception:
                pass
            
            # 优先从环境变量读取 Client ID 和 Client Secret，其次从 credentials.json 读取
            client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
            client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
            credentials_path = os.environ.get("GDRIVE_CREDENTIALS_PATH", "config/credentials.json")
            if (not client_id or not client_secret) and os.path.exists(credentials_path):
                try:
                    import json
                    with open(credentials_path, "r", encoding="utf-8") as f:
                        creds_data = json.load(f)
                        installed = creds_data.get("installed", {}) or creds_data.get("web", {})
                        if installed:
                            client_id = installed.get("client_id", "")
                            client_secret = installed.get("client_secret", "")
                except Exception as e:
                    self.log(f"读取 credentials.json 失败: {e}", "⚠")

            # 运行 rclone authorize（完整权限）
            self.log("请在弹出的浏览器中完成授权...", "⏳")
            self.log("提示：授权范围包括您的文件和分享文件", "ℹ")
            
            # 使用完整 drive 权限（不加 --rc，那个是配置远程控制服务的，和 OAuth 无关）
            cmd = [
                rclone_path, "authorize", "drive",
            ]
            if client_id and client_secret:
                cmd.extend([client_id, client_secret])
                self.log("检测到专属 Google API OAuth 凭据，正在使用专属凭据进行授权...", "🔑")
            
            cmd.extend(["--drive-scope", "drive"])
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,  # 5分钟超时
                creationflags=0x08000000 # CREATE_NO_WINDOW
            )
            
            if result.returncode == 0:
                # 提取 token
                output = result.stdout
                
                # 使用更健壮的 JSON 提取：匹配最剐的完整 JSON 对象（处理嵌套结构）
                import re, json
                # 找到以 { 开头的最剐 JSON 对象
                token_json = None
                for m in re.finditer(r'\{', output):
                    candidate = output[m.start():]
                    # 找到匹配的尾部
                    depth = 0
                    end = -1
                    for ci, ch in enumerate(candidate):
                        if ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                end = ci
                                break
                    if end > 0:
                        try:
                            parsed = json.loads(candidate[:end+1])
                            # 确保是 token（包含 access_token）
                            if 'access_token' in parsed:
                                token_json = candidate[:end+1]
                                break
                        except Exception:
                            continue
                
                if token_json:
                    # 直接写 rclone.conf（INI 格式）并限制文件访问权限
                    self.rclone_wrapper._write_remote_config(
                        "gdrive", client_id, client_secret, token_json
                    )
                    
                    self.log("✓ Rclone 授权成功！", "✓")
                    
                    # 直接获取用户信息（不等待测试连接，避免卡顿）
                    user_info = self.rclone_wrapper.get_user_info("gdrive")
                    email = user_info.get("email", "Google Drive")
                    
                    self.log(f"✓ 账号: {email}", "✓")
                    self.auth_status_label.setText(f"● 已连接: {email}")
                    self.auth_status_label.setStyleSheet("color: green; font-weight: bold;")
                    
                    # 启用所有功能
                    self.start_button.setEnabled(True)
                    self.preview_button.setEnabled(True)
                    self.rclone_auth_button.setText("🔄 重新授权")
                    
                    QMessageBox.information(
                        self, "授权成功", 
                        f"Rclone 统一授权成功！\n\n"
                        f"账号: {email}\n\n"
                        f"✅ 支持下载您的文件\n"
                        f"✅ 支持下载分享文件\n"
                        f"✅ 支持浏览云端文件夹\n\n"
                        f"正在加载文件夹结构..."
                    )
                    
                    # 自动加载文件夹树到主界面
                    from PyQt6.QtCore import QTimer
                    QTimer.singleShot(300, self.load_gdrive_root)
                else:
                    self.log("✗ 无法提取授权 token", "✗")
                    QMessageBox.warning(self, "警告", "授权可能未完成，请重试")
            else:
                self.log(f"✗ Rclone 授权失败: {result.stderr}", "✗")
                QMessageBox.critical(self, "错误", f"授权失败:\n{result.stderr}")
                
        except subprocess.TimeoutExpired:
            self.log("✗ 授权超时（5分钟）", "✗")
            QMessageBox.critical(self, "超时", "授权超时，请重试")
        except Exception as e:
            self.log(f"✗ 授权异常: {e}", "✗")
            QMessageBox.critical(self, "错误", f"授权异常:\n{str(e)}")
            import traceback
            traceback.print_exc()
    
    def start_sync(self):
        """开始同步"""
        # 验证输入 - 使用选中的文件夹
        gdrive_folder = self.selected_gdrive_folder_id
        local_folder = self.local_folder_input.text().strip()
        
        if not gdrive_folder:
            QMessageBox.warning(self, "警告", "请在右侧选择 Google Drive 来源文件夹")
            return
        
        if not local_folder:
            QMessageBox.warning(self, "警告", "请选择本地目标文件夹")
            return
        
        if not self.rclone_wrapper:
            QMessageBox.critical(self, "错误", "Rclone未初始化，请检查rclone.exe是否存在")
            return
        
        # 保存设置
        self.save_settings()
        
        # 重置统计
        self.total_files = 0
        self.completed_count = 0
        self.skipped_count = 0
        self.failed_count = 0
        
        # 启动Rclone同步工作线程
        self.sync_worker = RcloneSyncWorker(
            self.rclone_wrapper,
            gdrive_folder,
            local_folder
        )
        # 连接信号
        self.sync_worker.progress.connect(self.on_download_progress_rclone)
        self.sync_worker.finished.connect(self.on_sync_finished)
        self.sync_worker.log.connect(lambda msg, prefix: self.log(msg, prefix))
        self.sync_worker.file_event.connect(self.on_file_transfer_event)
        
        # 启动工作线程
        self.sync_worker.start()
        
        # 更新按钮状态
        self.start_button.setEnabled(False)
        self.pause_button.setEnabled(True)
        self.stop_button.setEnabled(True)
        
        self.log("开始同步...", "▶")
    
    def on_scan_progress(self, message):
        """扫描进度"""
        self.log(message, "🔍")
    
    def on_download_progress_rclone(self, stats):
        """处理 Rclone 进度更新"""
        try:
            # stats 是 RcloneStats 对象
            if stats.total_bytes > 0:
                downloaded = stats.bytes_transferred
                total = stats.total_bytes
                
                # 更新进度条
                progress = int((downloaded / total) * 100)
                self.current_progress.setValue(progress)
                
                # 格式化大小
                def format_size(size_bytes):
                    if size_bytes < 1024:
                        return f"{size_bytes} B"
                    elif size_bytes < 1024 * 1024:
                        return f"{size_bytes / 1024:.1f} KB"
                    elif size_bytes < 1024 * 1024 * 1024:
                        return f"{size_bytes / (1024 * 1024):.1f} MB"
                    else:
                        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
                
                # 更新状态文本 (例如: 48.2 GB / 48.2 GB)
                progress_text = f"{format_size(downloaded)} / {format_size(total)}"
                self.status_label.setText(progress_text)
                
                # 更新详细统计
                # 注意：stats.total_files 是我们需要动态添加的属性，如果 wrapper 没传，就默认 0
                total_files = getattr(stats, 'total_files', 0)
                # self.completed_count 是累积的，但 rclone stats 也有 transfers_complete
                # 我们优先用 rclone 返回的 transfers_complete，因为它更准（包含跳过的？）
                # 不，transfers_complete 是本次传输完成的。
                # 我们的 self.completed_count 是根据日志事件累加的。
                # 两者结合一下？为了一致性，如果 stats 里有值就用 stats 的
                
                comp_count = stats.transfers_complete
                # 如果 rclone 没返回有效 counts (0)，这可能是解析失败，或者是刚开始
                # 我们可以显示 logs 里的计数作为 fallback
                if comp_count == 0 and self.completed_count > 0:
                    comp_count = self.completed_count
                
                err_count = stats.errors
                if err_count == 0 and self.failed_count > 0:
                    err_count = self.failed_count
                    
                self.stats_total_files.setText(f"📂 总文件: {total_files}")
                self.stats_total_size.setText(f"💾 总大小: {format_size(total)}")
                self.stats_completed.setText(f"✅ 已完成: {comp_count}")
                self.stats_failed.setText(f"❌ 失败: {err_count}")
                
                # 更新速度和剩余时间
                speed_mb = stats.speed / (1024 * 1024)
                eta_str = f"{int(stats.eta)}s" if stats.eta < 3600 else f"{int(stats.eta/3600)}h {int((stats.eta%3600)/60)}m"
                if stats.eta == 0:
                    eta_str = "-"
                
                self.speed_label.setText(f"🚀 {speed_mb:.1f} MB/s  ⏱ 剩余: {eta_str}")
                
                self.speed_label.setText(f"🚀 {speed_mb:.1f} MB/s  ⏱ 剩余: {eta_str}")
                
                # 更新当前文件列表 (QTableWidget)
                from PyQt6.QtWidgets import QTableWidgetItem
                from PyQt6.QtGui import QColor, QBrush
                
                transfer_list = stats.transferring if stats.transferring else []
                
                # 总是刷新10行
                for i in range(10):
                    # 获取单元格 item (假设已初始化过)
                    item_name = self.file_table.item(i, 0)
                    item_size = self.file_table.item(i, 1)
                    item_pct = self.file_table.item(i, 2)
                    item_speed = self.file_table.item(i, 3)
                    item_status = self.file_table.item(i, 4)
                    
                    if not item_name: # 防御性编程
                         for c in range(5): self.file_table.setItem(i, c, QTableWidgetItem(""))
                         item_name = self.file_table.item(i, 0)
                         # ... reset others if needed
                    
                    if i < len(transfer_list):
                        file_info = transfer_list[i]
                        
                        name = file_info.get('name', '')
                        size = file_info.get('size', '-')
                        pct = file_info.get('percentage', '0%')
                        speed = file_info.get('speed', '-')
                        status = file_info.get('status', '等待中')
                        
                        # 设置文本
                        item_name.setText(name)
                        item_name.setToolTip(name) # 鼠标悬停显示全名
                        item_size.setText(size)
                        item_pct.setText(pct)
                        item_speed.setText(speed)
                        item_status.setText(status)
                        
                        # 状态颜色
                        if status == "传输中":
                            item_status.setForeground(QBrush(QColor("#1976D2")))
                        elif status == "准备传输":
                            item_status.setForeground(QBrush(QColor("#F57C00")))
                        else:
                            item_status.setForeground(QBrush(QColor("#666666")))
                            
                        # 对齐方式
                        item_size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        item_pct.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        item_speed.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                        item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)

                    else:
                        # 清空该行
                        item_name.setText("")
                        item_name.setToolTip("")
                        item_size.setText("")
                        item_pct.setText("")
                        item_speed.setText("")
                        item_status.setText("")
                
        except Exception as e:
            print(f"进度更新错误: {e}")

    def on_file_transfer_event(self, type, message, level):
        """处理文件传输事件"""
        from PyQt6.QtWidgets import QListWidgetItem
        from PyQt6.QtCore import Qt
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        if type == "success":
            color = "#2E7D32" # Green
            icon = "✅"
            self.completed_count += 1
        elif type == "error":
            color = "#C62828" # Red
            icon = "❌"
            self.failed_count += 1
        else:
            color = "#333333"
            icon = "ℹ"
            
        file_msg = message.replace("已完成:", "").replace("错误:", "").strip()
        
        # 创建列表项
        item_text = f"[{timestamp}] {icon} {file_msg}"
        item = QListWidgetItem(item_text)
        item.setForeground(Qt.GlobalColor.black if type == "info" else 
                          (Qt.GlobalColor.darkGreen if type == "success" else Qt.GlobalColor.darkRed))
        
        # 添加到顶部或底部? 用户通常习惯看最新的在底部，并自动滚动
        self.transfer_log.addItem(item)
        
        # 保持最多1000条
        if self.transfer_log.count() > 1000:
            self.transfer_log.takeItem(0) # 移除第一条（最旧的）
            
        # 自动滚动到底部
        self.transfer_log.scrollToBottom()
        
        # 同时也记录到主日志
        if type == "error":
             self.log(f"传输错误: {file_msg}", "❌")
        
        # 更新统计
        self.update_stats()

    def update_stats(self):
        """更新统计信息 (文件事件回调使用)"""
        # 这个方法由 on_file_transfer_event 调用
        # 主要用于更新完成/失败计数
        # 注意：on_download_progress_rclone 也会更新这些，但每秒一次
        # 这里为了实时反馈
        
        try:
            self.stats_completed.setText(f"✅ 已完成: {self.completed_count}")
            self.stats_failed.setText(f"❌ 失败: {self.failed_count}")
        except:
            pass

    def on_sync_finished(self, success):
        """同步完成"""
        if success:
            self.log("✓ 同步完成！", "✓")
            QMessageBox.information(
                self, "同步完成",
                "文件同步已成功完成！"
            )
        else:
            self.log("✗ 同步失败或已取消", "✗")
            
            # 自动保存错误日志
            try:
                import datetime
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                log_filename = f"sync_error_{timestamp}.txt"
                log_path = os.path.abspath(log_filename)
                
                with open(log_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.toPlainText())
                
                self.log(f"错误日志已保存: {log_path}", "ℹ")
                
                QMessageBox.warning(
                    self, "同步未完成",
                    f"同步未能完成。\n\n详细日志已保存到:\n{log_path}\n\n请查看该文件以获取错误详情。"
                )
            except Exception as e:
                print(f"保存日志失败: {e}")
                QMessageBox.warning(
                    self, "同步未完成",
                    "同步未能完成，请查看界面右下角的日志窗口了解详情。"
                )

        # 恢复按钮状态
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.pause_button.setText("⏸ 暂停")
        self.stop_button.setEnabled(False)

    def on_sync_error(self, error_msg):
        """同步错误"""
        self.log(f"同步错误: {error_msg}", "✗")
        QMessageBox.critical(self, "同步错误", f"同步过程中发生错误:\n{error_msg}")
    
    def stop_sync(self):
        """停止同步"""
        if self.sync_worker and self.sync_worker.isRunning():
            self.log("正在停止同步...", "⏹")
            
            # 设置停止标志
            self.sync_worker.should_stop = True
            
            # 断开所有信号连接，防止崩溃
            try:
                self.sync_worker.progress.disconnect()
                self.sync_worker.finished.disconnect()
                self.sync_worker.log.disconnect()
                self.sync_worker.file_event.disconnect()
            except:
                pass  # 如果已经断开连接，忽略错误
            
            # 等待线程完成
            if not self.sync_worker.wait(3000):  # 等待3秒
                self.log("强制终止同步线程", "⚠")
                self.sync_worker.terminate()
                self.sync_worker.wait()
            
            self.sync_worker = None
        
        self.log("同步已停止", "⏹")
        
        # 恢复按钮状态
        self.start_button.setEnabled(True)
        self.pause_button.setEnabled(False)
        self.stop_button.setEnabled(False)
    
    def preview_sync(self):
        """预览同步"""
        QMessageBox.information(self, "预览", "预览功能开发中...")
    
    def on_task_changed(self, index):
        """任务切换"""
        pass
    
    def open_settings(self):
        """打开设置对话框"""
        try:
            from ui.settings_dialog import SettingsDialog
            
            dialog = SettingsDialog(self)
            if dialog.exec():
                # 设置已保存，重新加载
                settings = dialog.get_settings()
                self.log("✓ 设置已更新", "✓")
                
                # 可以在这里应用新设置到 rclone_wrapper
                if self.rclone_wrapper and settings:
                    # 更新 rclone wrapper 的设置
                    self.rclone_wrapper.settings = settings
                    self.log("✓ Rclone 参数已更新", "✓")
        except Exception as e:
            self.log(f"✗ 打开设置失败: {e}", "✗")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"打开设置对话框失败:\n{str(e)}")
    
    def open_task_manager(self):
        """打开任务管理"""
        try:
            from ui.task_manager_dialog import TaskManagerDialog
            
            dialog = TaskManagerDialog(self)
            dialog.exec()
        except Exception as e:
            self.log(f"✗ 打开任务管理失败: {e}", "✗")
            import traceback
            traceback.print_exc()
            QMessageBox.critical(self, "错误", f"打开任务管理失败:\n{str(e)}")
    
    def export_logs(self):
        """导出日志"""
        try:
            import datetime
            filename, _ = QFileDialog.getSaveFileName(
                self, "导出日志",
                f"sync_log_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                "CSV files (*.csv)"
            )
            
            if filename:
                # 获取日志内容
                log_content = self.log_text.toPlainText()
                
                # 导出为CSV（防止公式注入）
                import csv
                from utils.path_helpers import sanitize_csv_field
                with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                    writer = csv.writer(f)
                    writer.writerow(['时间', '级别', '消息'])
                    
                    for line in log_content.split('\n'):
                        if line.strip():
                            # 简单解析
                            parts = line.split('] ', 1)
                            if len(parts) == 2:
                                time_part = sanitize_csv_field(parts[0].replace('[', ''))
                                msg_parts = parts[1].split(' ', 1)
                                if len(msg_parts) == 2:
                                    writer.writerow([time_part, sanitize_csv_field(msg_parts[0]), sanitize_csv_field(msg_parts[1])])
                                else:
                                    writer.writerow([time_part, '', sanitize_csv_field(parts[1])])
                
                self.log(f"✓ 日志已导出: {filename}", "✓")
                QMessageBox.information(self, "成功", f"日志已导出到:\n{filename}")
        except Exception as e:
            self.log(f"✗ 导出失败: {e}", "✗")
            QMessageBox.critical(self, "错误", f"导出失败:\n{str(e)}")
    
    def pause_sync(self):
        """暂停同步"""
        if self.sync_worker and self.sync_worker.isRunning():
            self.log("⏸ 暂停同步...", "ℹ")
            self.sync_worker.pause()
            
            # 更新按钮状态
            self.pause_button.setText("▶ 恢复")
            self.pause_button.clicked.disconnect()
            self.pause_button.clicked.connect(self.resume_sync)
    
    def resume_sync(self):
        """恢复同步"""
        self.log("▶ 恢复同步...", "ℹ")
        
        # 重新创建worker并启动（Rclone会自动跳过已下载文件）
        gdrive_folder = getattr(self, 'selected_gdrive_folder_id', '')
        local_folder = self.local_folder_input.text().strip()
        
        if self.sync_worker:
            self.sync_worker.stop()
            self.sync_worker.wait()
        
        # 创建新worker
        self.sync_worker = RcloneSyncWorker(
            self.rclone_wrapper,
            gdrive_folder,
            local_folder
        )
        self.sync_worker.progress.connect(self.on_download_progress_rclone)
        self.sync_worker.finished.connect(self.on_sync_finished)
        self.sync_worker.log.connect(lambda msg, prefix: self.log(msg, prefix))
        
        # 更新按钮状态
        self.pause_button.setText("⏸ 暂停")
        self.pause_button.clicked.disconnect()
        self.pause_button.clicked.connect(self.pause_sync)
        
        # 启动
        self.sync_worker.start()
    
    def preview_sync(self):
        """预览同步（重定向到新的异步预览）"""
        self.preview_files()

    def preview_files(self):
        """预览将要同步的文件（异步，防止崩溃）"""
        # 验证选择
        gdrive_folder = getattr(self, 'selected_gdrive_folder_id', None)
        
        if not gdrive_folder:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "警告", "请先在左侧选择 Google Drive 来源文件夹")
            return
        
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QProgressBar, QMessageBox
        from .preview_worker import PreviewWorker
        
        # 创建预览对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("预览文件列表")
        dialog.setGeometry(200, 200, 700, 500)
        
        layout = QVBoxLayout()
        
        # 进度显示
        progress_label = QLabel("正在扫描...")
        layout.addWidget(progress_label)
        
        progress_bar = QProgressBar()
        progress_bar.setRange(0, 0)  # 不确定进度
        layout.addWidget(progress_bar)
        
        # 文件列表
        file_list = QTextEdit()
        file_list.setReadOnly(True)
        layout.addWidget(file_list)
        
        # 按钮
        button_layout = QHBoxLayout()
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(dialog.reject)
        button_layout.addStretch()
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)
        
        dialog.setLayout(layout)
        
        # 创建 Worker
        worker = PreviewWorker(self.rclone_wrapper, gdrive_folder, max_files=1000)
        
        def on_files_loaded(files, total_count, total_size):
            progress_bar.setRange(0, 100)
            progress_bar.setValue(100)
            
            # 格式化大小
            if total_size > 1024*1024*1024:
                size_str = f"{total_size / (1024*1024*1024):.2f} GB"
            else:
                size_str = f"{total_size / (1024*1024):.2f} MB"
            
            progress_label.setText(f"统计完成: 共 {total_count} 个文件，总大小: {size_str}")
            
            # 显示文件列表
            file_text = f"=== 文件夹统计 ===\n文件总数: {total_count}\n总大小: {size_str}\n\n=== 前 {len(files)} 个文件 ===\n"
            
            file_text += "\n".join([
                f"{i+1}. {f['Name']} ({f.get('Size', 0) / 1024:.1f} KB)"
                for i, f in enumerate(files)
            ])
            
            if total_count > len(files):
                file_text += f"\n\n... (还有 {total_count - len(files)} 个文件未显示)"
                
            file_list.setText(file_text)
            
            cancel_button.setText("关闭")
            
            # 添加只有在加载完成后才显示的"开始同步"按钮
            if total_count > 0:
                sync_btn = QPushButton("🚀 立即开始同步")
                sync_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 5px;")
                sync_btn.clicked.connect(lambda: [dialog.accept(), self.start_sync()])
                button_layout.insertWidget(0, sync_btn)
        
        def on_progress(msg):
            progress_label.setText(msg)
        
        def on_error(err):
            progress_bar.setRange(0, 100)
            progress_bar.setValue(0)
            progress_label.setText(f"错误: {err}")
            QMessageBox.critical(dialog, "预览失败", err)
        
        worker.files_loaded.connect(on_files_loaded)
        worker.progress_update.connect(on_progress)
        worker.error_occurred.connect(on_error)
        worker.start()
        
        dialog.exec()

    def export_log(self):
        """导出日志"""
        self.export_logs()
    
    def closeEvent(self, event):
        """窗口关闭事件"""
        # 如果正在同步，先停止
        if self.sync_worker and self.sync_worker.isRunning():
            reply = QMessageBox.question(
                self, 
                '确认退出', 
                '同步正在进行中，确定要退出吗？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.stop_sync()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
    
    # ========== Google Drive 树形面板方法 ==========
    
    def create_gdrive_tree_panel(self):
        """创建 Google Drive 文件夹树面板"""
        from PyQt6.QtWidgets import QWidget, QVBoxLayout, QGroupBox, QTreeWidget, QPushButton, QHBoxLayout
        
        panel = QWidget()
        layout = QVBoxLayout()
        panel.setLayout(layout)
        
        # 标题
        group = QGroupBox("📁 Google Drive 来源")
        group_layout = QVBoxLayout()
        
        # 当前选择显示
        from PyQt6.QtWidgets import QLabel
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(QLabel("已选择:"))
        self.gdrive_source_label = QLabel("未选择")
        self.gdrive_source_label.setStyleSheet("color: gray; font-style: italic;")
        selection_layout.addWidget(self.gdrive_source_label, 1)
        group_layout.addLayout(selection_layout)
        
        # 树形控件
        self.gdrive_tree = QTreeWidget()
        self.gdrive_tree.setHeaderLabel("文件夹结构")
        self.gdrive_tree.itemExpanded.connect(self.on_tree_item_expanded)
        self.gdrive_tree.itemClicked.connect(self.on_tree_item_clicked)
        group_layout.addWidget(self.gdrive_tree)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        refresh_button = QPushButton("🔄 刷新")
        refresh_button.clicked.connect(self.load_gdrive_root)
        button_layout.addWidget(refresh_button)
        
        button_layout.addStretch()
        
        sync_all_button = QPushButton("✓ 同步整个网盘")
        sync_all_button.clicked.connect(lambda: self.select_folder_from_tree_embedded("root", "整个网盘"))
        button_layout.addWidget(sync_all_button)
        
        group_layout.addLayout(button_layout)
        group.setLayout(group_layout)
        layout.addWidget(group)
        
        return panel
    
    def load_gdrive_root(self):
        """加载 Google Drive 根目录（真正异步 - 使用 QThread）"""
        if not self.rclone_wrapper:
            self.log("请先授权 Rclone", "⚠")
            return
        
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        from .folder_load_worker import FolderLoadWorker
        
        self.gdrive_tree.clear()
        self.log("正在加载 Google Drive...", "📂")
        
        # 添加根节点
        self.root_item = QTreeWidgetItem(self.gdrive_tree)
        self.root_item.setText(0, "📁 我的云端硬盘")
        self.root_item.setData(0, Qt.ItemDataRole.UserRole, {'id': 'root', 'name': '我的云端硬盘'})
        
        # 使用 QThread 在后台加载，完全不阻塞UI
        self.folder_worker = FolderLoadWorker(self.rclone_wrapper, "root")
        self.folder_worker.folders_loaded.connect(lambda folders: self._on_root_loaded(folders, self.root_item))
        self.folder_worker.load_error.connect(lambda err: self.log(f"加载失败: {err}", "✗"))
        self.folder_worker.start()
    
    def _on_root_loaded(self, items, root_item):
        """根目录加载完成回调"""
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        
        for item in items:
            item_name = item.get('Name', '')
            item_id   = item.get('ID', '')
            is_dir    = item.get('IsDir', False)
            mime      = item.get('MimeType', '')
            icon      = _get_item_icon(is_dir, mime)
            
            child_item = QTreeWidgetItem(root_item)
            child_item.setText(0, f"{icon} {item_name}")
            child_item.setData(0, Qt.ItemDataRole.UserRole, {
                'id': item_id,
                'name': item_name,
                'is_dir': is_dir,
            })
            
            if is_dir:
                # 文件夹添加占位符
                placeholder = QTreeWidgetItem(child_item)
                placeholder.setText(0, "...")
        
        root_item.setExpanded(True)
        self.log(f"✓ Google Drive 加载完成", "✓")
    
    def load_subfolders_embedded(self, parent_item, folder_id):
        """延迟加载子文件夹（使用 QThread 异步）"""
        from .folder_load_worker import FolderLoadWorker
        
        # 使用 QThread 在后台加载
        worker = FolderLoadWorker(self.rclone_wrapper, folder_id)
        worker.folders_loaded.connect(lambda folders: self._populate_tree_items(folders, parent_item))
        worker.load_error.connect(lambda err: self.log(f"加载子文件夹失败: {err}", "⚠"))
        worker.start()
        
        # 保存 worker 引用，防止被垃圾回收
        if not hasattr(self, '_folder_workers'):
            self._folder_workers = []
        self._folder_workers.append(worker)
    
    def _populate_tree_items(self, items, parent_item):
        """填充树节点（在主线程执行）"""
        from PyQt6.QtWidgets import QTreeWidgetItem
        from PyQt6.QtCore import Qt
        
        for item in items:
            item_name = item.get('Name', '')
            item_id   = item.get('ID', '')
            is_dir    = item.get('IsDir', False)
            mime      = item.get('MimeType', '')
            icon      = _get_item_icon(is_dir, mime)
            
            child_item = QTreeWidgetItem(parent_item)
            child_item.setText(0, f"{icon} {item_name}")
            child_item.setData(0, Qt.ItemDataRole.UserRole, {
                'id': item_id,
                'name': item_name,
                'is_dir': is_dir,
            })
            
            if is_dir:
                placeholder = QTreeWidgetItem(child_item)
                placeholder.setText(0, "...")
    
    def on_tree_item_expanded(self, item):
        """展开节点时加载子目录（嵌入式版本）"""
        from PyQt6.QtCore import Qt
        
        if item.childCount() == 1 and item.child(0).text(0) == "...":
            item.takeChild(0)
            
            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data and isinstance(data, dict) and data.get('is_dir', True):
                folder_id = data['id']
                self.load_subfolders_embedded(item, folder_id)
    
    def on_tree_item_clicked(self, item, column):
        """点击树节点"""
        from PyQt6.QtCore import Qt
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        if not data.get('is_dir', True):
            # 文件不能选为同步目标
            return
        self.select_folder_from_tree_embedded(data['id'], data['name'])
    
    def on_tree_item_clicked(self, item, column):
        """点击树节点自动选择"""
        from PyQt6.QtCore import Qt
        
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and isinstance(data, dict):
            folder_id = data['id']
            folder_name = data['name']
            self.select_folder_from_tree_embedded(folder_id, folder_name)
    
    def select_folder_from_tree_embedded(self, folder_id, folder_name):
        """从嵌入式树中选择文件夹"""
        # 存储选择的文件夹ID
        self.selected_gdrive_folder_id = folder_id
        self.selected_gdrive_folder_name = folder_name
        self.selected_upload_gdrive_folder_id = folder_id
        self.selected_upload_gdrive_folder_name = folder_name
        
        # 更新来源路径显示
        if folder_id == "root":
            display_path = "📁 我的云端硬盘（整个网盘）"
        else:
            display_path = f"📁 {folder_name}"
        
        self.gdrive_source_label.setText(display_path)
        self.gdrive_source_label.setStyleSheet("color: green; font-weight: bold;")
        
        if hasattr(self, 'upload_target_label'):
            self.upload_target_label.setText(display_path)
            self.upload_target_label.setStyleSheet("color: green; font-weight: bold;")
        
        self.log(f"✓ 已选择来源: {folder_name}", "✓")

    
    # ========== 新增方法 ==========
    
    def create_local_path_section(self):
        """创建本地路径选择区域（带任务管理）"""
        from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox
        
        group = QGroupBox("💾 本地目标 & 任务")
        layout = QVBoxLayout()
        
        # === 任务管理区域 ===
        task_layout = QHBoxLayout()
        task_layout.addWidget(QLabel("📚 预设任务:"))
        
        self.task_combo = QComboBox()
        self.task_combo.addItem("选择任务...")
        self.task_combo.setMinimumWidth(200)
        task_layout.addWidget(self.task_combo, 1)
        
        load_task_btn = QPushButton("📂 加载")
        load_task_btn.clicked.connect(self.load_selected_task)
        task_layout.addWidget(load_task_btn)
        
        del_task_btn = QPushButton("🗑️ 删除")
        del_task_btn.clicked.connect(self.delete_selected_task)
        task_layout.addWidget(del_task_btn)
        
        layout.addLayout(task_layout)
        
        # 加载现有任务到下拉框
        self.load_tasks_to_combo()
        
        # 分隔线
        from PyQt6.QtWidgets import QFrame
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # === 本地文件夹选择 ===
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("保存到:"))
        if not hasattr(self, 'local_folder_input'):
            self.local_folder_input = QLineEdit()
        self.local_folder_input.setPlaceholderText("选择本地文件夹...")
        folder_layout.addWidget(self.local_folder_input)
        
        browse_button = QPushButton("📁 浏览")
        browse_button.clicked.connect(self.browse_local_folder)
        folder_layout.addWidget(browse_button)
        
        layout.addLayout(folder_layout)
        
        # 快速保存任务按钮
        save_task_layout = QHBoxLayout()
        save_task_layout.addStretch()
        
        save_task_button = QPushButton("💾 保存为新任务")
        save_task_button.setToolTip("将当前配置保存为新任务")
        save_task_button.clicked.connect(self.quick_save_task)
        save_task_layout.addWidget(save_task_button)
        
        layout.addLayout(save_task_layout)
        
        group.setLayout(layout)
        return group
    
    def create_scan_progress_section(self):
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
        self.scan_progress_group = group  # 保存引用以便控制显示
        group.setVisible(False)  # 默认隐藏
        return group
    
    def quick_save_task(self):
        """快速保存当前配置为任务"""
        from PyQt6.QtWidgets import QInputDialog, QMessageBox
        
        # 验证输入
        if not self.selected_gdrive_folder_id:
            QMessageBox.warning(self, "提示", "请先选择 Google Drive 来源文件夹")
            return
        
        local_path = self.local_folder_input.text().strip()
        if not local_path:
            QMessageBox.warning(self, "提示", "请先选择本地目标文件夹")
            return
        
        # 显示简单输入对话框
        task_name, ok = QInputDialog.getText(
            self, "保存为任务", 
            f"请输入任务名称:\n\n"
            f"来源: {self.selected_gdrive_folder_name}\n"
            f"目标: {local_path}\n\n"
            f"任务名称:"
        )
        
        if ok and task_name.strip():
            try:
                # 保存任务
                import json
                task = {
                    'name': task_name.strip(),
                    'gdrive_folder': self.selected_gdrive_folder_id,
                    'gdrive_folder_name': self.selected_gdrive_folder_name,
                    'local_folder': local_path,
                    'sync_mode': 'copy'
                }
                
                # 读取现有任务
                tasks_file = "config/tasks.json"
                tasks = []
                if os.path.exists(tasks_file):
                    with open(tasks_file, 'r', encoding='utf-8') as f:
                        tasks = json.load(f)
                
                # 添加新任务
                tasks.append(task)
                
                # 保存
                os.makedirs(os.path.dirname(tasks_file), exist_ok=True)
                with open(tasks_file, 'w', encoding='utf-8') as f:
                    json.dump(tasks, f, indent=2, ensure_ascii=False)
                
                # 刷新下拉框
                self.load_tasks_to_combo()
                
                self.log(f"✓ 任务已保存: {task_name}", "✓")
                QMessageBox.information(self, "成功", f"任务 '{task_name}' 已保存成功！")
                
            except Exception as e:
                self.log(f"保存任务失败: {e}", "✗")
                QMessageBox.critical(self, "错误", f"保存任务失败:\n{e}")

    def load_tasks_to_combo(self):
        """加载任务到下拉框"""
        try:
            self.task_combo.clear()
            self.task_combo.addItem("选择任务...")
            
            tasks_file = "config/tasks.json"
            if os.path.exists(tasks_file):
                import json
                with open(tasks_file, 'r', encoding='utf-8') as f:
                    tasks = json.load(f)
                
                for task in tasks:
                    self.task_combo.addItem(task['name'], task)
            
        except Exception as e:
            self.log(f"加载任务列表失败: {e}", "⚠")

    def load_selected_task(self):
        """加载选中的任务"""
        index = self.task_combo.currentIndex()
        if index <= 0:
            return
            
        task_data = self.task_combo.itemData(index)
        if not task_data:
            return
            
        try:
            # 恢复 Google Drive 选择
            self.selected_gdrive_folder_id = task_data.get('gdrive_folder', '')
            self.selected_gdrive_folder_name = task_data.get('gdrive_folder_name', '')
            self.selected_upload_gdrive_folder_id = self.selected_gdrive_folder_id
            self.selected_upload_gdrive_folder_name = self.selected_gdrive_folder_name
            
            # 更新显示
            if self.selected_gdrive_folder_id == "root":
                display = "📁 我的云端硬盘（整个网盘）"
            else:
                display = f"📁 {self.selected_gdrive_folder_name}"
            
            if hasattr(self, 'gdrive_source_label'):
                self.gdrive_source_label.setText(display)
                self.gdrive_source_label.setStyleSheet("color: green; font-weight: bold;")
                
            if hasattr(self, 'upload_target_label'):
                self.upload_target_label.setText(display)
                self.upload_target_label.setStyleSheet("color: green; font-weight: bold;")

            
            # 恢复本地路径
            local_path = task_data.get('local_folder', '')
            self.local_folder_input.setText(local_path)
            
            self.log(f"✓ 已加载任务: {task_data['name']}", "✓")
            
        except Exception as e:
            self.log(f"加载任务失败: {e}", "✗")

    def delete_selected_task(self):
        """删除选中的任务"""
        index = self.task_combo.currentIndex()
        if index <= 0:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "提示", "请先选择要删除的任务")
            return
            
        task_name = self.task_combo.currentText()
        
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(self, "确认删除", f"确定要删除任务 '{task_name}' 吗？",
                                   QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 从 JSON 文件删除
                tasks_file = "config/tasks.json"
                if os.path.exists(tasks_file):
                    import json
                    with open(tasks_file, 'r', encoding='utf-8') as f:
                        tasks = json.load(f)
                    
                    # 过滤掉要删除的任务
                    new_tasks = [t for t in tasks if t['name'] != task_name]
                    
                    with open(tasks_file, 'w', encoding='utf-8') as f:
                        json.dump(new_tasks, f, indent=2, ensure_ascii=False)
                    
                    # 刷新下拉框
                    self.load_tasks_to_combo()
                    self.log(f"✓ 任务已删除: {task_name}", "✓")
                    
            except Exception as e:
                self.log(f"删除任务失败: {e}", "✗")

    # ==================================================================
    # 素材上传功能实现
    # ==================================================================

    def create_upload_tab(self):
        """创建素材上传标签页"""
        upload_tab = QWidget()
        layout = QHBoxLayout()
        upload_tab.setLayout(layout)
        
        from PyQt6.QtWidgets import QSplitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter)
        
        # === 左侧控制面板 ===
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_panel.setLayout(left_layout)
        
        # 1. 目标云盘文件夹
        target_group = QGroupBox("目标云端文件夹")
        target_layout = QHBoxLayout()
        
        # 根据当前选择初始化显示
        folder_id = getattr(self, 'selected_gdrive_folder_id', '')
        folder_name = getattr(self, 'selected_gdrive_folder_name', '')
        if folder_id:
            if folder_id == "root":
                display = "📁 我的云端硬盘（整个网盘）"
            else:
                display = f"📁 {folder_name}"
            self.upload_target_label = QLabel(display)
            self.upload_target_label.setStyleSheet("color: green; font-weight: bold;")
        else:
            self.upload_target_label = QLabel("📁 请先在左侧选择目标文件夹")
            self.upload_target_label.setStyleSheet("color: #FF9800; font-weight: bold;")
            
        target_layout.addWidget(QLabel("当前上传目标 (同左侧选择):"))
        target_layout.addWidget(self.upload_target_label, 1)
        target_group.setLayout(target_layout)
        left_layout.addWidget(target_group)

        
        # 2. 拖拽上传区
        self.drag_area = UploadDragArea()
        self.drag_area.files_dropped.connect(self.on_files_dropped_to_upload)
        self.drag_area.clicked.connect(self.select_files_manually)
        left_layout.addWidget(self.drag_area)
        
        # 3. 拖拽提示和操作按钮
        add_buttons_layout = QHBoxLayout()
        self.add_files_btn = QPushButton("➕ 添加本地文件")
        self.add_files_btn.clicked.connect(self.select_files_manually)
        self.add_folder_btn = QPushButton("➕ 添加本地文件夹")
        self.add_folder_btn.clicked.connect(self.select_folder_manually)
        add_buttons_layout.addWidget(self.add_files_btn)
        add_buttons_layout.addWidget(self.add_folder_btn)
        left_layout.addLayout(add_buttons_layout)
        
        # === 右侧进度与队列表面板 ===
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_panel.setLayout(right_layout)
        
        # 1. 控制按钮组
        control_group = QGroupBox("上传控制")
        control_layout = QHBoxLayout()
        
        self.start_upload_btn = QPushButton("▶ 开始上传")
        self.start_upload_btn.clicked.connect(self.start_upload)
        self.start_upload_btn.setEnabled(False) # 队列为空时禁用
        
        self.stop_upload_btn = QPushButton("⏹ 停止")
        self.stop_upload_btn.clicked.connect(self.stop_upload)
        self.stop_upload_btn.setEnabled(False)
        
        self.delete_item_btn = QPushButton("➖ 删除选中")
        self.delete_item_btn.clicked.connect(self.delete_selected_upload_items)
        
        self.clear_queue_btn = QPushButton("🗑 清空列表")
        self.clear_queue_btn.clicked.connect(self.clear_upload_queue)
        
        control_layout.addWidget(self.start_upload_btn)
        control_layout.addWidget(self.stop_upload_btn)
        control_layout.addWidget(self.delete_item_btn)
        control_layout.addWidget(self.clear_queue_btn)
        control_layout.addStretch()
        control_group.setLayout(control_layout)
        right_layout.addWidget(control_group)
        
        # 2. 总体进度与统计
        stats_group = QGroupBox("📈 总体进度")
        stats_layout = QVBoxLayout()
        
        progress_info_layout = QHBoxLayout()
        self.upload_status_lbl = QLabel("等待上传中...")
        self.upload_speed_lbl = QLabel("🚀 0.0 MB/s")
        self.upload_speed_lbl.setStyleSheet("font-weight: bold; color: #2196F3;")
        progress_info_layout.addWidget(self.upload_status_lbl)
        progress_info_layout.addStretch()
        progress_info_layout.addWidget(self.upload_speed_lbl)
        stats_layout.addLayout(progress_info_layout)
        
        self.upload_overall_progress = QProgressBar()
        self.upload_overall_progress.setFixedHeight(15)
        self.upload_overall_progress.setFormat("%p%")
        stats_layout.addWidget(self.upload_overall_progress)
        
        # 队列统计标签
        stats_labels_layout = QHBoxLayout()
        self.upload_stats_count_lbl = QLabel("📂 待上传: 0 项")
        self.upload_stats_size_lbl = QLabel("💾 总大小: 0 B")
        self.upload_stats_success_lbl = QLabel("✅ 成功: 0")
        self.upload_stats_failed_lbl = QLabel("❌ 失败: 0")
        self.upload_stats_failed_lbl.setStyleSheet("color: red;")
        stats_labels_layout.addWidget(self.upload_stats_count_lbl)
        stats_labels_layout.addWidget(self.upload_stats_size_lbl)
        stats_labels_layout.addWidget(self.upload_stats_success_lbl)
        stats_labels_layout.addWidget(self.upload_stats_failed_lbl)
        stats_labels_layout.addStretch()
        stats_layout.addLayout(stats_labels_layout)
        
        stats_group.setLayout(stats_layout)
        right_layout.addWidget(stats_group)
        
        # 3. 待上传队列列表表格
        right_layout.addWidget(QLabel("上传任务队列:"))
        self.upload_table = QTableWidget()
        self.upload_table.setColumnCount(6)
        self.upload_table.setHorizontalHeaderLabels(["名称", "本地路径", "大小", "类型", "状态", "进度"])
        self.upload_table.verticalHeader().setVisible(False)
        self.upload_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.upload_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.upload_table.setAlternatingRowColors(True)
        
        # 列宽自适应
        self.upload_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.upload_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        self.upload_table.setColumnWidth(1, 250)
        self.upload_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.upload_table.setColumnWidth(2, 90)
        self.upload_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.upload_table.setColumnWidth(3, 70)
        self.upload_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.upload_table.setColumnWidth(4, 90)
        self.upload_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.upload_table.setColumnWidth(5, 100)
        
        right_layout.addWidget(self.upload_table)
        
        # 4. 上传专属日志框
        right_layout.addWidget(QLabel("上传日志:"))
        self.upload_log_list = QListWidget()
        self.upload_log_list.setUniformItemSizes(True)
        self.upload_log_list.setFixedHeight(120)
        self.upload_log_list.setStyleSheet("""
            QListWidget {
                font-family: 'Consolas', monospace;
                font-size: 9pt;
                background-color: #fafafa;
                border: 1px solid #ddd;
            }
        """)
        right_layout.addWidget(self.upload_log_list)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([400, 800])
        
        return upload_tab



    def on_files_dropped_to_upload(self, paths):
        """文件被拖入上传区时的回调"""
        self.add_paths_to_upload_queue(paths)

    def select_files_manually(self):
        """手动选择本地文件"""
        files, _ = QFileDialog.getOpenFileNames(self, "选择要上传的本地文件")
        if files:
            self.add_paths_to_upload_queue(files)

    def select_folder_manually(self):
        """手动选择本地文件夹"""
        folder = QFileDialog.getExistingDirectory(self, "选择要上传的本地文件夹")
        if folder:
            self.add_paths_to_upload_queue([folder])

    def add_paths_to_upload_queue(self, paths):
        """添加路径到上传队列"""
        if not paths:
            return
            
        to_calculate = []
        
        for path in paths:
            # 避免重复
            if any(item['path'] == path for item in self.upload_queue):
                continue
                
            is_dir = os.path.isdir(path)
            name = os.path.basename(path)
            
            item = {
                'path': path,
                'is_dir': is_dir,
                'name': name,
                'size': -1 if is_dir else os.path.getsize(path),
                'status': '等待上传'
            }
            
            self.upload_queue.append(item)
            idx = len(self.upload_queue) - 1
            
            # 插入表格行
            row = self.upload_table.rowCount()
            self.upload_table.insertRow(row)
            
            self.upload_table.setItem(row, 0, QTableWidgetItem(f"📁 {name}" if is_dir else f"📄 {name}"))
            self.upload_table.setItem(row, 1, QTableWidgetItem(path))
            
            size_str = "计算中..." if is_dir else self.format_file_size(item['size'])
            self.upload_table.setItem(row, 2, QTableWidgetItem(size_str))
            
            self.upload_table.setItem(row, 3, QTableWidgetItem("文件夹" if is_dir else "文件"))
            self.upload_table.setItem(row, 4, QTableWidgetItem("等待上传"))
            self.upload_table.setItem(row, 5, QTableWidgetItem("0%"))
            
            if is_dir:
                to_calculate.append((idx, path, True))
                
            self.upload_log(f"添加上传项: {name}", "➕")
            
        # 后台计算文件夹大小
        if to_calculate:
            self.start_size_calculation(to_calculate)
            
        self.update_upload_stats()
        self.start_upload_btn.setEnabled(len(self.upload_queue) > 0)

    def start_size_calculation(self, items):
        """后台非阻塞计算大小"""
        worker = SizeCalculatorWorker(items)
        worker.size_calculated.connect(self.on_size_calculated)
        self.size_workers.append(worker)
        worker.finished.connect(lambda: self.size_workers.remove(worker) if worker in self.size_workers else None)
        worker.start()

    def on_size_calculated(self, idx, size_bytes):
        """大小计算完成的回调"""
        if idx >= len(self.upload_queue):
            return
            
        self.upload_queue[idx]['size'] = size_bytes
        path = self.upload_queue[idx]['path']
        
        # 更新表格
        for row in range(self.upload_table.rowCount()):
            if self.upload_table.item(row, 1).text() == path:
                self.upload_table.item(row, 2).setText(self.format_file_size(size_bytes))
                break
                
        self.update_upload_stats()

    def format_file_size(self, size_bytes):
        """格式化文件大小"""
        if size_bytes < 0:
            return "计算中..."
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"

    def update_upload_stats(self):
        """更新上传状态栏统计"""
        count = len(self.upload_queue)
        self.upload_stats_count_lbl.setText(f"📂 待上传: {count} 项")
        
        total_size = sum(item['size'] for item in self.upload_queue if item['size'] > 0)
        self.upload_stats_size_lbl.setText(f"💾 总大小: {self.format_file_size(total_size)}")
        
        success_count = sum(1 for item in self.upload_queue if item['status'] == '已完成')
        failed_count = sum(1 for item in self.upload_queue if item['status'] == '失败')
        self.upload_stats_success_lbl.setText(f"✅ 成功: {success_count}")
        self.upload_stats_failed_lbl.setText(f"❌ 失败: {failed_count}")

    def delete_selected_upload_items(self):
        """从上传列表中删除选中的项目"""
        selected_ranges = self.upload_table.selectedRanges()
        if not selected_ranges:
            QMessageBox.warning(self, "提示", "请先在列表中选中要删除的行")
            return
            
        # 收集要删除的行索引并降序排列，避免删除引起的索引错乱
        rows_to_delete = []
        for r in selected_ranges:
            for row in range(r.topRow(), r.bottomRow() + 1):
                rows_to_delete.append(row)
        rows_to_delete = sorted(list(set(rows_to_delete)), reverse=True)
        
        for row in rows_to_delete:
            path = self.upload_table.item(row, 1).text()
            # 从内存队列中移除
            self.upload_queue = [item for item in self.upload_queue if item['path'] != path]
            # 从表格界面移除
            self.upload_table.removeRow(row)
            
        self.update_upload_stats()
        self.start_upload_btn.setEnabled(len(self.upload_queue) > 0)
        self.upload_log("已删除选中的待上传项", "ℹ")

    def clear_upload_queue(self):
        """清空上传列表"""
        if self.upload_worker and self.upload_worker.isRunning():
            QMessageBox.warning(self, "警告", "正在上传中，请先停止上传再清空列表")
            return
            
        self.upload_queue = []
        self.upload_table.setRowCount(0)
        self.update_upload_stats()
        self.start_upload_btn.setEnabled(False)
        self.upload_log("上传队列已清空", "🗑")

    def start_upload(self):
        """开始上传队列"""
        if not self.selected_gdrive_folder_id:
            QMessageBox.warning(self, "警告", "请先在左侧选择 Google Drive 目标文件夹（双击或展开，点击选中）")
            return
            
        if not self.upload_queue:
            QMessageBox.warning(self, "警告", "上传队列为空，请先拖入或添加本地文件")
            return
            
        if self.upload_worker and self.upload_worker.isRunning():
            return
            
        if not self.rclone_wrapper:
            QMessageBox.critical(self, "错误", "Rclone 未初始化，请检查 rclone.exe 是否存在")
            return
            
        # 过滤出未上传完成的项
        pending_items = [item for item in self.upload_queue if item['status'] not in ('已完成', '上传中')]
        if not pending_items:
            QMessageBox.information(self, "提示", "队列中的所有项目均已上传完成。若需重新上传，请清空后重新添加。")
            return
            
        # 锁定UI
        self.start_upload_btn.setEnabled(False)
        self.stop_upload_btn.setEnabled(True)
        self.delete_item_btn.setEnabled(False)
        self.clear_queue_btn.setEnabled(False)
        self.drag_area.setEnabled(False)
        
        # 启动上传线程
        self.upload_worker = RcloneUploadWorker(
            rclone_wrapper=self.rclone_wrapper,
            upload_items=pending_items,
            remote_folder_id=self.selected_gdrive_folder_id
        )

        
        self.upload_worker.item_started.connect(self.on_upload_item_started)
        self.upload_worker.item_progress.connect(self.on_upload_item_progress)
        self.upload_worker.item_finished.connect(self.on_upload_item_finished)
        self.upload_worker.overall_progress.connect(self.on_upload_overall_progress)
        self.upload_worker.queue_finished.connect(self.on_upload_queue_finished)
        self.upload_worker.log.connect(lambda msg, pref: self.upload_log(msg, pref))
        
        self.upload_worker.start()
        self.upload_status_lbl.setText("正在上传文件...")
        self.upload_log("上传任务队列已启动", "▶")

    def stop_upload(self):
        """停止上传"""
        if self.upload_worker and self.upload_worker.isRunning():
            self.upload_status_lbl.setText("正在停止...")
            self.upload_log("正在停止上传任务...", "⏹")
            self.upload_worker.stop()

    def on_upload_item_started(self, idx):
        """某项开始上传时的回调"""
        path = self.upload_worker.upload_items[idx]['path']
        for row in range(self.upload_table.rowCount()):
            if self.upload_table.item(row, 1).text() == path:
                # 状态修改为 上传中
                self.upload_table.item(row, 4).setText("上传中")
                self.upload_table.item(row, 4).setForeground(QBrush(QColor("#1976D2")))
                
                # 放入内置进度条
                progress_bar = QProgressBar()
                progress_bar.setRange(0, 100)
                progress_bar.setValue(0)
                progress_bar.setTextVisible(True)
                progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #ccc;
                        border-radius: 4px;
                        text-align: center;
                        font-size: 8pt;
                    }
                    QProgressBar::chunk {
                        background-color: #2196F3;
                    }
                """)
                self.upload_table.setCellWidget(row, 5, progress_bar)
                break
                
        # 同步内存状态
        for item in self.upload_queue:
            if item['path'] == path:
                item['status'] = '上传中'
                break
        self.update_upload_stats()

    def on_upload_item_progress(self, idx, stats):
        """某项上传进度更新的回调"""
        path = self.upload_worker.upload_items[idx]['path']
        for row in range(self.upload_table.rowCount()):
            if self.upload_table.item(row, 1).text() == path:
                widget = self.upload_table.cellWidget(row, 5)
                if isinstance(widget, QProgressBar) and stats.total_bytes > 0:
                    pct = int((stats.bytes_transferred / stats.total_bytes) * 100)
                    widget.setValue(pct)
                break

    def on_upload_item_finished(self, idx, success, message):
        """某项上传结束的回调"""
        path = self.upload_worker.upload_items[idx]['path']
        for row in range(self.upload_table.rowCount()):
            if self.upload_table.item(row, 1).text() == path:
                # 移除进度条部件，换成文本
                self.upload_table.removeCellWidget(row, 5)
                self.upload_table.setItem(row, 5, QTableWidgetItem("100%" if success else "0%"))
                
                # 状态与颜色
                status_item = self.upload_table.item(row, 4)
                if success:
                    status_item.setText("已完成")
                    status_item.setForeground(QBrush(QColor("#2E7D32")))
                else:
                    status_item.setText("失败")
                    status_item.setForeground(QBrush(QColor("#C62828")))
                break
                
        # 同步内存状态
        for item in self.upload_queue:
            if item['path'] == path:
                item['status'] = '已完成' if success else '失败'
                break
        self.update_upload_stats()

    def on_upload_overall_progress(self, pct, speed, eta):
        """总体上传进度回调"""
        self.upload_overall_progress.setValue(int(pct))
        
        speed_mb = speed / (1024 * 1024)
        eta_str = f"{int(eta)}s" if eta < 3600 else f"{int(eta/3600)}h {int((eta%3600)/60)}m"
        if eta == 0:
            eta_str = "-"
            
        self.upload_speed_lbl.setText(f"🚀 {speed_mb:.1f} MB/s  ⏱ 剩余: {eta_str}")

    def on_upload_queue_finished(self, all_success):
        """队列全部上传结束的回调"""
        self.upload_status_lbl.setText("上传完成" if all_success else "上传已停止/有失败")
        self.upload_speed_lbl.setText("🚀 0.0 MB/s")
        
        # 恢复UI
        self.start_upload_btn.setEnabled(len(self.upload_queue) > 0)
        self.stop_upload_btn.setEnabled(False)
        self.delete_item_btn.setEnabled(True)
        self.clear_queue_btn.setEnabled(True)
        self.drag_area.setEnabled(True)

        
        if all_success:
            QMessageBox.information(self, "上传成功", "队列中所有的本地素材均已成功上传到 Google Drive！")
        else:
            QMessageBox.warning(self, "上传未完全成功", "上传任务已结束。请检查日志或队列状态，确保所有文件上传成功。")

    def upload_log(self, message, prefix="ℹ"):
        """写日志到上传专用日志框"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        item_text = f"[{timestamp}] {prefix} {message}"
        from PyQt6.QtWidgets import QListWidgetItem
        item = QListWidgetItem(item_text)
        from PyQt6.QtCore import Qt
        if prefix == "✓":
            item.setForeground(Qt.GlobalColor.darkGreen)
        elif prefix == "✗":
            item.setForeground(Qt.GlobalColor.darkRed)
        self.upload_log_list.addItem(item)
        if self.upload_log_list.count() > 500:
            self.upload_log_list.takeItem(0)
        self.upload_log_list.scrollToBottom()


