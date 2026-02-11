"""
设置对话框
"""
import os
import json
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
    QLabel, QLineEdit, QSpinBox, QCheckBox, QPushButton,
    QGroupBox, QTabWidget, QWidget, QMessageBox
)
from PyQt6.QtCore import Qt


class SettingsDialog(QDialog):
    """设置对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(500)
        self.settings_file = "config/app_settings.json"
        self.settings = self.load_settings()
        
        self.init_ui()
        self.load_values()
    
    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout()
        
        # 创建标签页
        tabs = QTabWidget()
        
        # Rclone 参数标签页
        rclone_tab = self.create_rclone_tab()
        tabs.addTab(rclone_tab, "Rclone 参数")
        
        # 下载设置标签页
        download_tab = self.create_download_tab()
        tabs.addTab(download_tab, "下载设置")
        
        # 界面设置标签页
        ui_tab = self.create_ui_tab()
        tabs.addTab(ui_tab, "界面设置")
        
        layout.addWidget(tabs)
        
        # 底部按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.reset_button = QPushButton("恢复默认")
        self.reset_button.clicked.connect(self.reset_to_default)
        button_layout.addWidget(self.reset_button)
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_settings_clicked)
        button_layout.addWidget(self.save_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def create_rclone_tab(self):
        """创建 Rclone 参数标签页"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 并发设置组
        concurrent_group = QGroupBox("并发设置")
        concurrent_layout = QFormLayout()
        
        self.checkers_spin = QSpinBox()
        self.checkers_spin.setRange(1, 32)
        self.checkers_spin.setValue(8)
        self.checkers_spin.setToolTip("并发检查文件的数量（默认：8）")
        concurrent_layout.addRow("并发检查数:", self.checkers_spin)
        
        self.transfers_spin = QSpinBox()
        self.transfers_spin.setRange(1, 16)
        self.transfers_spin.setValue(4)
        self.transfers_spin.setToolTip("并发传输文件的数量（默认：4）")
        concurrent_layout.addRow("并发传输数:", self.transfers_spin)
        
        concurrent_group.setLayout(concurrent_layout)
        layout.addWidget(concurrent_group)
        
        # 性能设置组
        performance_group = QGroupBox("性能设置")
        performance_layout = QFormLayout()
        
        self.chunk_size_spin = QSpinBox()
        self.chunk_size_spin.setRange(1, 256)
        self.chunk_size_spin.setValue(64)
        self.chunk_size_spin.setSuffix(" MB")
        self.chunk_size_spin.setToolTip("Drive 分块大小（默认：64MB）")
        performance_layout.addRow("分块大小:", self.chunk_size_spin)
        
        self.buffer_size_spin = QSpinBox()
        self.buffer_size_spin.setRange(0, 256)
        self.buffer_size_spin.setValue(0)
        self.buffer_size_spin.setSuffix(" MB")
        self.buffer_size_spin.setToolTip("缓冲区大小，0=自动（默认：0）")
        performance_layout.addRow("缓冲区:", self.buffer_size_spin)
        
        performance_group.setLayout(performance_layout)
        layout.addWidget(performance_group)
        
        # 重试设置组
        retry_group = QGroupBox("重试设置")
        retry_layout = QFormLayout()
        
        self.retries_spin = QSpinBox()
        self.retries_spin.setRange(1, 100)
        self.retries_spin.setValue(10)
        self.retries_spin.setToolTip("失败重试次数（默认：10）")
        retry_layout.addRow("重试次数:", self.retries_spin)
        
        self.low_level_retries_spin = QSpinBox()
        self.low_level_retries_spin.setRange(1, 100)
        self.low_level_retries_spin.setValue(10)
        self.low_level_retries_spin.setToolTip("底层重试次数（默认：10）")
        retry_layout.addRow("底层重试:", self.low_level_retries_spin)
        
        retry_group.setLayout(retry_layout)
        layout.addWidget(retry_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_download_tab(self):
        """创建下载设置标签页"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 带宽限制组
        bandwidth_group = QGroupBox("带宽限制")
        bandwidth_layout = QFormLayout()
        
        self.bwlimit_enabled = QCheckBox("启用带宽限制")
        self.bwlimit_enabled.toggled.connect(self.on_bwlimit_toggled)
        bandwidth_layout.addRow("", self.bwlimit_enabled)
        
        self.bwlimit_spin = QSpinBox()
        self.bwlimit_spin.setRange(1, 10000)
        self.bwlimit_spin.setValue(0)
        self.bwlimit_spin.setSuffix(" MB/s")
        self.bwlimit_spin.setEnabled(False)
        self.bwlimit_spin.setToolTip("限制下载速度（0=不限制）")
        bandwidth_layout.addRow("最大速度:", self.bwlimit_spin)
        
        bandwidth_group.setLayout(bandwidth_layout)
        layout.addWidget(bandwidth_group)
        
        # 文件处理组
        file_group = QGroupBox("文件处理")
        file_layout = QFormLayout()
        
        self.skip_existing = QCheckBox("跳过已存在的文件")
        self.skip_existing.setChecked(True)
        self.skip_existing.setToolTip("不重新下载已存在的文件")
        file_layout.addRow("", self.skip_existing)
        
        self.delete_empty_dirs = QCheckBox("删除空目录")
        self.delete_empty_dirs.setChecked(False)
        self.delete_empty_dirs.setToolTip("同步后删除空目录")
        file_layout.addRow("", self.delete_empty_dirs)
        
        file_group.setLayout(file_layout)
        layout.addWidget(file_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def create_ui_tab(self):
        """创建界面设置标签页"""
        widget = QWidget()
        layout = QVBoxLayout()
        
        # 通知设置组
        notification_group = QGroupBox("通知设置")
        notification_layout = QFormLayout()
        
        self.notify_on_complete = QCheckBox("同步完成时通知")
        self.notify_on_complete.setChecked(True)
        notification_layout.addRow("", self.notify_on_complete)
        
        self.notify_on_error = QCheckBox("发生错误时通知")
        self.notify_on_error.setChecked(True)
        notification_layout.addRow("", self.notify_on_error)
        
        notification_group.setLayout(notification_layout)
        layout.addWidget(notification_group)
        
        # 日志设置组
        log_group = QGroupBox("日志设置")
        log_layout = QFormLayout()
        
        self.verbose_logging = QCheckBox("详细日志")
        self.verbose_logging.setChecked(True)
        self.verbose_logging.setToolTip("显示详细的同步信息")
        log_layout.addRow("", self.verbose_logging)
        
        self.auto_export_log = QCheckBox("自动导出日志")
        self.auto_export_log.setChecked(False)
        self.auto_export_log.setToolTip("同步完成后自动导出日志")
        log_layout.addRow("", self.auto_export_log)
        
        log_group.setLayout(log_layout)
        layout.addWidget(log_group)
        
        layout.addStretch()
        widget.setLayout(layout)
        return widget
    
    def on_bwlimit_toggled(self, checked):
        """带宽限制切换"""
        self.bwlimit_spin.setEnabled(checked)
    
    def load_settings(self):
        """加载设置"""
        default_settings = {
            "rclone": {
                "checkers": 8,
                "transfers": 4,
                "chunk_size": 64,
                "buffer_size": 0,
                "retries": 10,
                "low_level_retries": 10
            },
            "download": {
                "bwlimit_enabled": False,
                "bwlimit": 0,
                "skip_existing": True,
                "delete_empty_dirs": False
            },
            "ui": {
                "notify_on_complete": True,
                "notify_on_error": True,
                "verbose_logging": True,
                "auto_export_log": False
            }
        }
        
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    # 合并默认设置
                    for key in default_settings:
                        if key not in loaded:
                            loaded[key] = default_settings[key]
                        else:
                            for subkey in default_settings[key]:
                                if subkey not in loaded[key]:
                                    loaded[key][subkey] = default_settings[key][subkey]
                    return loaded
            except:
                pass
        
        return default_settings
    
    def load_values(self):
        """加载设置值到控件"""
        # Rclone 参数
        rclone = self.settings.get("rclone", {})
        self.checkers_spin.setValue(rclone.get("checkers", 8))
        self.transfers_spin.setValue(rclone.get("transfers", 4))
        self.chunk_size_spin.setValue(rclone.get("chunk_size", 64))
        self.buffer_size_spin.setValue(rclone.get("buffer_size", 0))
        self.retries_spin.setValue(rclone.get("retries", 10))
        self.low_level_retries_spin.setValue(rclone.get("low_level_retries", 10))
        
        # 下载设置
        download = self.settings.get("download", {})
        self.bwlimit_enabled.setChecked(download.get("bwlimit_enabled", False))
        self.bwlimit_spin.setValue(download.get("bwlimit", 0))
        self.skip_existing.setChecked(download.get("skip_existing", True))
        self.delete_empty_dirs.setChecked(download.get("delete_empty_dirs", False))
        
        # UI 设置
        ui = self.settings.get("ui", {})
        self.notify_on_complete.setChecked(ui.get("notify_on_complete", True))
        self.notify_on_error.setChecked(ui.get("notify_on_error", True))
        self.verbose_logging.setChecked(ui.get("verbose_logging", True))
        self.auto_export_log.setChecked(ui.get("auto_export_log", False))
    
    def save_settings_clicked(self):
        """保存设置"""
        # 收集设置
        self.settings = {
            "rclone": {
                "checkers": self.checkers_spin.value(),
                "transfers": self.transfers_spin.value(),
                "chunk_size": self.chunk_size_spin.value(),
                "buffer_size": self.buffer_size_spin.value(),
                "retries": self.retries_spin.value(),
                "low_level_retries": self.low_level_retries_spin.value()
            },
            "download": {
                "bwlimit_enabled": self.bwlimit_enabled.isChecked(),
                "bwlimit": self.bwlimit_spin.value(),
                "skip_existing": self.skip_existing.isChecked(),
                "delete_empty_dirs": self.delete_empty_dirs.isChecked()
            },
            "ui": {
                "notify_on_complete": self.notify_on_complete.isChecked(),
                "notify_on_error": self.notify_on_error.isChecked(),
                "verbose_logging": self.verbose_logging.isChecked(),
                "auto_export_log": self.auto_export_log.isChecked()
            }
        }
        
        # 保存到文件
        try:
            os.makedirs(os.path.dirname(self.settings_file), exist_ok=True)
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            
            QMessageBox.information(self, "成功", "设置已保存！")
            self.accept()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存设置失败:\n{str(e)}")
    
    def reset_to_default(self):
        """恢复默认设置"""
        reply = QMessageBox.question(
            self, "确认",
            "确定要恢复默认设置吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # 恢复默认值
            self.checkers_spin.setValue(8)
            self.transfers_spin.setValue(4)
            self.chunk_size_spin.setValue(64)
            self.buffer_size_spin.setValue(0)
            self.retries_spin.setValue(10)
            self.low_level_retries_spin.setValue(10)
            
            self.bwlimit_enabled.setChecked(False)
            self.bwlimit_spin.setValue(0)
            self.skip_existing.setChecked(True)
            self.delete_empty_dirs.setChecked(False)
            
            self.notify_on_complete.setChecked(True)
            self.notify_on_error.setChecked(True)
            self.verbose_logging.setChecked(True)
            self.auto_export_log.setChecked(False)
    
    def get_settings(self):
        """获取设置"""
        return self.settings
