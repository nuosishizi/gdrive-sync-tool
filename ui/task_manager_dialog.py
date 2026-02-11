"""
任务管理对话框
"""
import json
import os
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QLineEdit, QLabel, QGroupBox, QFormLayout, QComboBox
)
from PyQt6.QtCore import Qt


class TaskManagerDialog(QDialog):
    """任务管理对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("任务管理")
        self.setMinimumSize(800, 500)
        self.tasks_file = "config/tasks.json"
        self.tasks = self.load_tasks()
        
        self.init_ui()
        self.refresh_table()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        
        # 任务列表
        list_group = QGroupBox("任务列表")
        list_layout = QVBoxLayout()
        
        self.task_table = QTableWidget()
        self.task_table.setColumnCount(5)
        self.task_table.setHorizontalHeaderLabels([
            "名称", "云端文件夹", "本地文件夹", "状态", "创建时间"
        ])
        self.task_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.task_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        list_layout.addWidget(self.task_table)
        
        list_group.setLayout(list_layout)
        layout.addWidget(list_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        
        self.add_button = QPushButton("➕ 添加任务")
        self.add_button.clicked.connect(self.add_task)
        button_layout.addWidget(self.add_button)
        
        self.edit_button = QPushButton("✏ 编辑任务")
        self.edit_button.clicked.connect(self.edit_task)
        button_layout.addWidget(self.edit_button)
        
        self.delete_button = QPushButton("🗑 删除任务")
        self.delete_button.clicked.connect(self.delete_task)
        button_layout.addWidget(self.delete_button)
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_tasks(self):
        """加载任务列表"""
        if os.path.exists(self.tasks_file):
            try:
                with open(self.tasks_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                pass
        return []
    
    def save_tasks(self):
        """保存任务列表"""
        try:
            os.makedirs(os.path.dirname(self.tasks_file), exist_ok=True)
            with open(self.tasks_file, 'w', encoding='utf-8') as f:
                json.dump(self.tasks, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存任务失败:\n{str(e)}")
            return False
    
    def refresh_table(self):
        """刷新任务表格"""
        self.task_table.setRowCount(0)
        
        for task in self.tasks:
            row = self.task_table.rowCount()
            self.task_table.insertRow(row)
            
            self.task_table.setItem(row, 0, QTableWidgetItem(task.get('name', '')))
            self.task_table.setItem(row, 1, QTableWidgetItem(task.get('gdrive_folder', '')))
            self.task_table.setItem(row, 2, QTableWidgetItem(task.get('local_folder', '')))
            self.task_table.setItem(row, 3, QTableWidgetItem(task.get('status', '就绪')))
            self.task_table.setItem(row, 4, QTableWidgetItem(task.get('created_at', '')))
    
    def add_task(self):
        """添加任务"""
        dialog = TaskEditDialog(self)
        if dialog.exec():
            task_data = dialog.get_task_data()
            task_data['created_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            task_data['status'] = '就绪'
            
            self.tasks.append(task_data)
            if self.save_tasks():
                self.refresh_table()
                QMessageBox.information(self, "成功", "任务已添加！")
    
    def edit_task(self):
        """编辑任务"""
        selected_rows = self.task_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "警告", "请先选择要编辑的任务")
            return
        
        row = selected_rows[0].row()
        task = self.tasks[row]
        
        dialog = TaskEditDialog(self, task)
        if dialog.exec():
            task_data = dialog.get_task_data()
            task_data['created_at'] = task.get('created_at', datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            task_data['status'] = task.get('status', '就绪')
            
            self.tasks[row] = task_data
            if self.save_tasks():
                self.refresh_table()
                QMessageBox.information(self, "成功", "任务已更新！")
    
    def delete_task(self):
        """删除任务"""
        selected_rows = self.task_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "警告", "请先选择要删除的任务")
            return
        
        row = selected_rows[0].row()
        task_name = self.tasks[row].get('name', '')
        
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除任务 '{task_name}' 吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            del self.tasks[row]
            if self.save_tasks():
                self.refresh_table()
                QMessageBox.information(self, "成功", "任务已删除！")
    
    def get_tasks(self):
        """获取任务列表"""
        return self.tasks


class TaskEditDialog(QDialog):
    """任务编辑对话框"""
    
    def __init__(self, parent=None, task=None):
        super().__init__(parent)
        self.setWindowTitle("编辑任务" if task else "添加任务")
        self.setMinimumWidth(500)
        self.task = task or {}
        
        self.init_ui()
        self.load_values()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("例如：每日备份")
        form_layout.addRow("任务名称:", self.name_input)
        
        self.gdrive_folder_input = QLineEdit()
        self.gdrive_folder_input.setPlaceholderText("输入文件夹ID")
        form_layout.addRow("云端文件夹:", self.gdrive_folder_input)
        
        self.local_folder_input = QLineEdit()
        self.local_folder_input.setPlaceholderText("选择本地路径")
        form_layout.addRow("本地文件夹:", self.local_folder_input)
        
        layout.addLayout(form_layout)
        
        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_task)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def load_values(self):
        """加载任务数据"""
        if self.task:
            self.name_input.setText(self.task.get('name', ''))
            self.gdrive_folder_input.setText(self.task.get('gdrive_folder', ''))
            self.local_folder_input.setText(self.task.get('local_folder', ''))
    
    def save_task(self):
        """保存任务"""
        name = self.name_input.text().strip()
        gdrive_folder = self.gdrive_folder_input.text().strip()
        local_folder = self.local_folder_input.text().strip()
        
        if not name:
            QMessageBox.warning(self, "警告", "请输入任务名称")
            return
        
        if not gdrive_folder:
            QMessageBox.warning(self, "警告", "请输入云端文件夹ID")
            return
        
        if not local_folder:
            QMessageBox.warning(self, "警告", "请输入本地文件夹路径")
            return
        
        self.accept()
    
    def get_task_data(self):
        """获取任务数据"""
        return {
            'name': self.name_input.text().strip(),
            'gdrive_folder': self.gdrive_folder_input.text().strip(),
            'local_folder': self.local_folder_input.text().strip()
        }
