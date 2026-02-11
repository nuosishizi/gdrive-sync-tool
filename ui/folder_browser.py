"""
Google Drive 文件夹浏览对话框
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QTreeWidget,
    QTreeWidgetItem, QLabel, QMessageBox, QLineEdit
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon


class FolderScanWorker(QThread):
    """文件夹扫描工作线程"""
    
    folders_loaded = pyqtSignal(list)  # 文件夹列表
    error_occurred = pyqtSignal(str)   # 错误信息
    
    def __init__(self, gdrive_client, parent_id='root'):
        super().__init__()
        self.gdrive_client = gdrive_client
        self.parent_id = parent_id
    
    def run(self):
        """执行扫描"""
        try:
            items = self.gdrive_client.list_folder_contents(self.parent_id)
            folders = [item for item in items if item.is_folder()]
            self.folders_loaded.emit(folders)
        except Exception as e:
            self.error_occurred.emit(str(e))


class GDriveFolderBrowser(QDialog):
    """Google Drive 文件夹浏览器"""
    
    def __init__(self, gdrive_client, parent=None):
        super().__init__(parent)
        self.gdrive_client = gdrive_client
        self.selected_folder_id = None
        self.selected_folder_name = None
        self.init_ui()
        
        # 加载根目录
        self.load_root_folders()
    
    def init_ui(self):
        """初始化UI"""
        self.setWindowTitle("选择 Google Drive 文件夹")
        self.setGeometry(200, 200, 600, 500)
        
        layout = QVBoxLayout()
        
        # 说明文本
        info_label = QLabel("浏览并选择要同步的 Google Drive 文件夹：")
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
        
        # 文件夹树
        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderLabels(["文件夹名称", "文件夹 ID"])
        self.folder_tree.setColumnWidth(0, 400)
        self.folder_tree.itemExpanded.connect(self.on_item_expanded)
        self.folder_tree.itemClicked.connect(self.on_item_clicked)  # 添加点击事件
        self.folder_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        layout.addWidget(self.folder_tree)
        
        # 选中的文件夹信息
        self.selected_label = QLabel("未选择文件夹")
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
    
    def load_root_folders(self):
        """加载根目录文件夹"""
        self.folder_tree.clear()
        
        # 添加"我的云端硬盘"根节点
        root_item = QTreeWidgetItem(self.folder_tree)
        root_item.setText(0, "📁 我的云端硬盘")
        root_item.setText(1, "root")
        root_item.setData(0, Qt.ItemDataRole.UserRole, "root")
        
        # 添加占位符（表示可展开）
        placeholder = QTreeWidgetItem(root_item)
        placeholder.setText(0, "加载中...")
        
        self.folder_tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
    
    def on_item_expanded(self, item):
        """当节点展开时加载子文件夹"""
        # 检查是否已加载
        if item.childCount() == 1 and item.child(0).text(0) == "加载中...":
            folder_id = item.data(0, Qt.ItemDataRole.UserRole)
            self.load_subfolders(item, folder_id)
    
    def load_subfolders(self, parent_item, folder_id):
        """加载子文件夹"""
        # 清除占位符
        parent_item.takeChildren()
        
        # 启动工作线程
        worker = FolderScanWorker(self.gdrive_client, folder_id)
        worker.folders_loaded.connect(lambda folders: self.on_folders_loaded(parent_item, folders))
        worker.error_occurred.connect(self.on_error)
        worker.start()
        
        # 保存 worker 引用防止被垃圾回收
        self.current_worker = worker
    
    def on_folders_loaded(self, parent_item, folders):
        """文件夹加载完成"""
        if not folders:
            # 没有子文件夹
            empty_item = QTreeWidgetItem(parent_item)
            empty_item.setText(0, "(无子文件夹)")
            empty_item.setDisabled(True)
        else:
            for folder in folders:
                folder_item = QTreeWidgetItem(parent_item)
                folder_item.setText(0, f"📁 {folder.name}")
                folder_item.setText(1, folder.id)
                folder_item.setData(0, Qt.ItemDataRole.UserRole, folder.id)
                
                # 添加占位符（假设可能有子文件夹）
                placeholder = QTreeWidgetItem(folder_item)
                placeholder.setText(0, "加载中...")
    
    def on_item_clicked(self, item, column):
        """单击选择文件夹"""
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_id and item.text(0) != "加载中..." and not item.isDisabled():
            self.selected_folder_id = folder_id
            self.selected_folder_name = item.text(0).replace("📁 ", "")
            self.selected_label.setText(f"✓ 已选择: {self.selected_folder_name} (ID: {folder_id})")
            self.select_button.setEnabled(True)
    
    def on_item_double_clicked(self, item, column):
        """双击直接确认选择"""
        folder_id = item.data(0, Qt.ItemDataRole.UserRole)
        if folder_id and item.text(0) != "加载中..." and not item.isDisabled():
            self.selected_folder_id = folder_id
            self.selected_folder_name = item.text(0).replace("📁 ", "")
            self.accept()  # 直接关闭对话框
    
    def search_folders(self):
        """搜索文件夹"""
        query = self.search_input.text().strip()
        if not query:
            QMessageBox.warning(self, "提示", "请输入搜索关键词")
            return
        
        try:
            folders = self.gdrive_client.search_folders(query)
            
            if not folders:
                QMessageBox.information(self, "搜索结果", f"未找到包含 '{query}' 的文件夹")
                return
            
            # 清空树并显示搜索结果
            self.folder_tree.clear()
            
            search_root = QTreeWidgetItem(self.folder_tree)
            search_root.setText(0, f"🔍 搜索结果: {query}")
            search_root.setText(1, "")
            
            for folder in folders:
                folder_item = QTreeWidgetItem(search_root)
                folder_item.setText(0, f"📁 {folder.name}")
                folder_item.setText(1, folder.id)
                folder_item.setData(0, Qt.ItemDataRole.UserRole, folder.id)
            
            self.folder_tree.addTopLevelItem(search_root)
            search_root.setExpanded(True)
            
        except Exception as e:
            QMessageBox.critical(self, "搜索错误", f"搜索失败:\n{str(e)}")
    
    def accept_selection(self):
        """确认选择"""
        if self.selected_folder_id:
            self.accept()
        else:
            QMessageBox.warning(self, "提示", "请先选择一个文件夹")
    
    def on_error(self, error_msg):
        """错误处理"""
        QMessageBox.critical(self, "错误", f"加载文件夹失败:\n{error_msg}")
    
    def get_selected_folder(self):
        """获取选中的文件夹"""
        return self.selected_folder_id, self.selected_folder_name
