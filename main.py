"""
应用入口
"""
import sys
import os
from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.gdrive_client import GDriveClient
from core.sync_engine import SyncEngine
from database.models import Database


def main():
    """主函数"""
    # 获取脚本所在目录（确保路径正确）
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)  # 切换工作目录到脚本所在位置
    
    # 创建应用
    app = QApplication(sys.argv)
    app.setApplicationName("Google Drive 同步工具 (Rclone)")
    
    # 设置全局图标（影响任务栏、标题栏、Alt+Tab显示）
    from PyQt6.QtGui import QIcon
    import sys as _sys
    _icon_candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'app_icon.ico'),
    ]
    if getattr(_sys, 'frozen', False):
        _icon_candidates.insert(0, os.path.join(os.path.dirname(_sys.executable), 'app_icon.ico'))
        if hasattr(_sys, '_MEIPASS'):
            _icon_candidates.insert(0, os.path.join(_sys._MEIPASS, 'app_icon.ico'))
    for _icon_path in _icon_candidates:
        if os.path.exists(_icon_path):
            app.setWindowIcon(QIcon(_icon_path))
            break
    
    # 初始化数据库
    db = Database("gdrive_sync.db")
    
    # 初始化GDrive客户端（可选 - 仅用于浏览文件夹）
    gdrive_client = None
    sync_engine = None
    try:
        gdrive_client = GDriveClient(
            credentials_path="config/credentials.json",
            token_path="config/token.pickle"
        )
        sync_engine = SyncEngine(gdrive_client, db)
    except Exception as e:
        print(f"GDrive客户端初始化失败（不影响Rclone功能）: {e}")
    
    # 创建主窗口
    window = MainWindow()
    window.set_components(gdrive_client, db, sync_engine)
    window.show()
    
    # 运行应用
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
