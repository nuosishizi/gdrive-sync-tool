"""
Google Drive 文件夹浏览对话框（支持显示文件和文件夹）
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget,
    QTreeWidgetItem, QLabel, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon


# 根据 MIME 类型判断文件图标
def _icon_for(item):
    if item.is_folder():
        return "📁"
    mime = item.mime_type or ""
    if "spreadsheet" in mime or "excel" in mime:
        return "📊"
    elif "document" in mime or "word" in mime:
        return "📄"
    elif "presentation" in mime or "powerpoint" in mime:
        return "📑"
    elif "pdf" in mime:
        return "📋"
    elif "image" in mime:
        return "🖼"
    elif "video" in mime:
        return "🎬"
    elif "audio" in mime:
        return "🎵"
    elif "zip" in mime or "compressed" in mime:
        return "🗜"
    else:
        return "📄"


def _size_str(size_bytes):
    """格式化文件大小"""
    if size_bytes <= 0:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


class ItemScanWorker(QThread):
    """文件/文件夹扫描工作线程"""
    
    items_loaded = pyqtSignal(list)   # 所有条目
    error_occurred = pyqtSignal(str)
    
    def __init__(self, gdrive_client, parent_id='root'):
        super().__init__()
        self.gdrive_client = gdrive_client
        self.parent_id = parent_id
    
    def run(self):
        try:
            # 加载全部条目（文件夹 + 文件）
            items = self.gdrive_client.list_folder_contents(self.parent_id)
            # 文件夹排前面，然后按名称排序
            folders = sorted([i for i in items if i.is_folder()], key=lambda x: x.name.lower())
            files   = sorted([i for i in items if not i.is_folder()], key=lambda x: x.name.lower())
            self.items_loaded.emit(folders + files)
        except Exception as e:
            self.error_occurred.emit(str(e))


# 向后兼容旧名称
FolderScanWorker = ItemScanWorker


class GDriveFolderBrowser(QDialog):
    """Google Drive 文件夹 / 文件浏览器"""
    
    def __init__(self, gdrive_client, parent=None):
        super().__init__(parent)
        self.gdrive_client = gdrive_client
        self.selected_folder_id = None
        self.selected_folder_name = None
        self._workers = []  # 防止被垃圾回收
        self.init_ui()
        self.load_root_folders()
    
    def init_ui(self):
        self.setWindowTitle("选择 Google Drive 文件夹")
        self.setGeometry(200, 200, 700, 550)
        
        layout = QVBoxLayout()
        
        info_label = QLabel("浏览并选择要同步的 Google Drive 文件夹（文件夹 + 文件均可见）：")
        layout.addWidget(info_label)
        
        # 搜索框
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("搜索:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入文件夹名称搜索...")
        self.search_input.returnPressed.connect(self.search_folders)
        search_layout.addWidget(self.search_input)
        self.search_button = QPushButton("🔍 搜索")
        self.search_button.clicked.connect(self.search_folders)
        search_layout.addWidget(self.search_button)
        layout.addLayout(search_layout)
        
        # 文件树（三列：名称、大小、类型）
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["名称", "大小", "类型"])
        self.folder_tree.setColumnWidth(0, 420)
        self.folder_tree.setColumnWidth(1, 90)
        self.folder_tree.setColumnWidth(2, 120)
        self.folder_tree.itemExpanded.connect(self.on_item_expanded)
        self.folder_tree.itemClicked.connect(self.on_item_clicked)
        self.folder_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.folder_tree)
        
        # 选中信息
        self.selected_label = QLabel("未选择")
        self.selected_label.setStyleSheet("padding: 5px; background-color: #f0f0f0; border-radius: 3px;")
        layout.addWidget(self.selected_label)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.select_button = QPushButton("✓ 选择此文件夹")
        self.select_button.clicked.connect(self.accept_selection)
        self.select_button.setEnabled(False)
        button_layout.addWidget(self.select_button)
        
        self.cancel_button = QPushButton("✗ 取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
    
    # ------------------------------------------------------------------
    # 数据加载
    # ------------------------------------------------------------------

    def load_root_folders(self):
        self.folder_tree.clear()
        
        root_item = QTreeWidgetItem(self.folder_tree)
        root_item.setText(0, "📁 我的云端硬盘")
        root_item.setText(1, "")
        root_item.setText(2, "根目录")
        root_item.setData(0, Qt.ItemDataRole.UserRole, {"id": "root", "is_folder": True})
        
        placeholder = QTreeWidgetItem(root_item)
        placeholder.setText(0, "加载中...")
        
        self.folder_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
    
    def on_item_expanded(self, item):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        if not data.get("is_folder"):
            return
        if item.childCount() == 1 and item.child(0).text(0) == "加载中...":
            self._load_items(item, data["id"])
    
    def _load_items(self, parent_item, folder_id):
        parent_item.takeChildren()
        
        worker = ItemScanWorker(self.gdrive_client, folder_id)
        worker.items_loaded.connect(lambda items: self._on_items_loaded(parent_item, items))
        worker.error_occurred.connect(self.on_error)
        worker.start()
        self._workers.append(worker)
    
    def _on_items_loaded(self, parent_item, items):
        if not items:
            empty = QTreeWidgetItem(parent_item)
            empty.setText(0, "（空目录）")
            empty.setDisabled(True)
            return
        
        for item in items:
            tree_item = QTreeWidgetItem(parent_item)
            icon = _icon_for(item)
            tree_item.setText(0, f"{icon} {item.name}")
            tree_item.setText(1, _size_str(item.size) if not item.is_folder() else "")
            tree_item.setText(2, "文件夹" if item.is_folder() else _mime_label(item.mime_type))
            tree_item.setData(0, Qt.ItemDataRole.UserRole, {
                "id": item.id,
                "name": item.name,
                "is_folder": item.is_folder(),
            })
            
            if item.is_folder():
                # 添加占位符（可能有子项）
                placeholder = QTreeWidgetItem(tree_item)
                placeholder.setText(0, "加载中...")
            else:
                # 文件不可点击选为同步目标，颜色灰显
                tree_item.setForeground(0, tree_item.foreground(0))  # 默认色
    
    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def on_item_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(data, dict):
            return
        if not data.get("is_folder"):
            # 文件不能被选为同步目标
            self.selected_label.setText("⚠ 请选择文件夹（不能选单个文件）")
            self.select_button.setEnabled(False)
            self.selected_folder_id = None
            return
        folder_id = data["id"]
        folder_name = data["name"]
        self.selected_folder_id = folder_id
        self.selected_folder_name = folder_name
        self.selected_label.setText(f"✓ 已选择: {folder_name} (ID: {folder_id})")
        self.select_button.setEnabled(True)
    
    def on_item_double_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(data, dict) and data.get("is_folder"):
            self.selected_folder_id = data["id"]
            self.selected_folder_name = data["name"]
            self.accept()
    
    def search_folders(self):
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return
        try:
            folders = self.gdrive_client.search_folders(query)
            if not folders:
                QMessageBox.information(self, "搜索结果", f"未找到包含 '{query}' 的文件夹")
                return
            self.folder_tree.clear()
            search_root = QTreeWidgetItem(self.folder_tree)
            search_root.setText(0, f"🔍 搜索结果: {query}")
            for folder in folders:
                fi = QTreeWidgetItem(search_root)
                fi.setText(0, f"📁 {folder.name}")
                fi.setText(1, "")
                fi.setText(2, "文件夹")
                fi.setData(0, Qt.ItemDataRole.UserRole, {"id": folder.id, "name": folder.name, "is_folder": True})
            self.folder_tree.addTopLevelItem(search_root)
            search_root.setExpanded(True)
        except Exception as e:
            QMessageBox.critical(self, "搜索错误", f"搜索失败:\n{str(e)}")
    
    def accept_selection(self):
        if self.selected_folder_id:
            self.accept()
        else:
            QMessageBox.warning(self, "提示", "请先选择一个文件夹")
    
    def on_error(self, error_msg):
        QMessageBox.critical(self, "错误", f"加载失败:\n{error_msg}")
    
    def get_selected_folder(self):
        return self.selected_folder_id, self.selected_folder_name


def _mime_label(mime: str) -> str:
    if not mime:
        return "文件"
    if "folder" in mime:
        return "文件夹"
    if "spreadsheet" in mime:
        return "表格"
    if "document" in mime:
        return "文档"
    if "presentation" in mime:
        return "演示文稿"
    if "pdf" in mime:
        return "PDF"
    if "image" in mime:
        return "图片"
    if "video" in mime:
        return "视频"
    if "audio" in mime:
        return "音频"
    if "zip" in mime or "compress" in mime:
        return "压缩包"
    # 取 mime 最后一段便于阅读
    return mime.split("/")[-1] if "/" in mime else "文件"
