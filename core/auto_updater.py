"""
自动更新检查器 — 静默在后台运行，有新版本时弹窗提示
"""
import urllib.request
import json
from PyQt6.QtCore import QThread, pyqtSignal, QTimer

try:
    from version import APP_VERSION
except ImportError:
    APP_VERSION = "1.0.21"  # fallback
GITHUB_RELEASES_API = "https://api.github.com/repos/secure-artifacts/google_tongbu/releases/latest"
CHECK_INTERVAL_HOURS = 6   # 每 6 小时静默检查一次


def _parse_version(tag: str) -> tuple:
    """把 'v1.2.3' 或 '1.2.3' 解析成可比较的元组 (1, 2, 3)"""
    tag = tag.lstrip("v").strip()
    try:
        return tuple(int(x) for x in tag.split("."))
    except Exception:
        return (0,)


class UpdateCheckWorker(QThread):
    """后台检查 GitHub Releases 是否有新版本"""

    update_available = pyqtSignal(str, str, str)  # tag, name, body
    check_failed     = pyqtSignal(str)             # error message

    def __init__(self, current_version: str = APP_VERSION):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            req = urllib.request.Request(
                GITHUB_RELEASES_API,
                headers={"User-Agent": f"GDriveSync/{self.current_version}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            latest_tag  = data.get("tag_name", "")
            latest_name = data.get("name", latest_tag)
            latest_body = data.get("body", "（无更新说明）")

            if not latest_tag:
                return

            if _parse_version(latest_tag) > _parse_version(self.current_version):
                self.update_available.emit(latest_tag, latest_name, latest_body)
        except Exception as e:
            self.check_failed.emit(str(e))


class AutoUpdater:
    """
    挂在主窗口上的自动更新管理器。
    调用 start() 后立即做第一次检查，之后每隔 CHECK_INTERVAL_HOURS 小时再次检查。
    """

    def __init__(self, parent_window):
        self.parent = parent_window
        self._workers = []

        # 定时器（毫秒）
        self._timer = QTimer(parent_window)
        self._timer.timeout.connect(self._check)

    def start(self):
        """启动：稍微延迟后首次检查，避免和启动流程抢资源"""
        QTimer.singleShot(8000, self._check)                          # 8 秒后第一次
        self._timer.start(CHECK_INTERVAL_HOURS * 3600 * 1000)        # 之后每 N 小时

    def _check(self):
        worker = UpdateCheckWorker(APP_VERSION)
        worker.update_available.connect(self._on_update_available)
        # check_failed 只是静默忽略（网络不好 / API 限频等情况）
        worker.start()
        self._workers.append(worker)
        # 清理已完成的 worker 引用
        self._workers = [w for w in self._workers if w.isRunning()]

    def _on_update_available(self, tag: str, name: str, body: str):
        from PyQt6.QtWidgets import QMessageBox, QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout
        import webbrowser

        dlg = QDialog(self.parent)
        dlg.setWindowTitle("🎉 发现新版本！")
        dlg.setMinimumWidth(480)

        layout = QVBoxLayout(dlg)

        layout.addWidget(QLabel(f"<b>当前版本:</b> v{APP_VERSION}"))
        layout.addWidget(QLabel(f"<b>最新版本:</b> {tag} — {name}"))
        layout.addWidget(QLabel("\n<b>更新内容:</b>"))

        body_edit = QTextEdit()
        body_edit.setReadOnly(True)
        body_edit.setPlainText(body or "（没有更新说明）")
        body_edit.setMaximumHeight(200)
        layout.addWidget(body_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        ignore_btn = QPushButton("稍后再说")
        ignore_btn.clicked.connect(dlg.reject)
        btn_layout.addWidget(ignore_btn)

        update_btn = QPushButton("🚀 立即下载新版本")
        update_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 6px 12px;")
        update_btn.clicked.connect(lambda: [
            webbrowser.open(f"https://github.com/secure-artifacts/google_tongbu/releases/tag/{tag}"),
            dlg.accept()
        ])
        btn_layout.addWidget(update_btn)

        layout.addLayout(btn_layout)
        dlg.exec()
