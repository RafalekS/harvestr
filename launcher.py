#!/usr/bin/env python3
"""Harvestr server launcher GUI."""
import json
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

from PyQt6.QtCore import (
    QProcess, QProcessEnvironment, Qt, QTimer, pyqtSignal
)
from PyQt6.QtGui import QColor, QFont, QIcon, QTextCursor
from PyQt6.QtWidgets import (
    QApplication, QFrame, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QPlainTextEdit, QPushButton,
    QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

SCRIPT_DIR = Path(__file__).resolve().parent
WEBUI_SCRIPT = SCRIPT_DIR / "webui.py"
SETTINGS_FILE = SCRIPT_DIR / "_launcher_settings.json"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7860


def _load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_settings(d: dict) -> None:
    try:
        SETTINGS_FILE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    except Exception:
        pass


class StatusIndicator(QWidget):
    """Coloured circle + label."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._dot.setFixedWidth(16)
        font = self._dot.font()
        font.setPointSize(14)
        self._dot.setFont(font)

        self._text = QLabel("Stopped")
        font2 = self._text.font()
        font2.setBold(True)
        self._text.setFont(font2)

        layout.addWidget(self._dot)
        layout.addWidget(self._text)
        layout.addStretch()
        self.set_stopped()

    def set_running(self, url: str = ""):
        self._dot.setStyleSheet("color: #4caf50;")
        self._text.setText(f"Running — {url}" if url else "Running")
        self._text.setStyleSheet("color: #4caf50;")

    def set_starting(self):
        self._dot.setStyleSheet("color: #ff9800;")
        self._text.setText("Starting…")
        self._text.setStyleSheet("color: #ff9800;")

    def set_stopped(self):
        self._dot.setStyleSheet("color: #f44336;")
        self._text.setText("Stopped")
        self._text.setStyleSheet("color: #f44336;")


class LauncherWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Harvestr Launcher")
        self.setMinimumSize(680, 500)

        self._process: QProcess | None = None
        self._settings = _load_settings()
        self._restart_pending = False

        self._build_ui()
        self._restore_settings()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(12, 12, 12, 12)

        # ── Configuration group ───────────────────────────────────────────────
        cfg_group = QGroupBox("Server Configuration")
        cfg_layout = QHBoxLayout(cfg_group)
        cfg_layout.setSpacing(12)

        cfg_layout.addWidget(QLabel("Host:"))
        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("127.0.0.1")
        self.host_edit.setFixedWidth(140)
        cfg_layout.addWidget(self.host_edit)

        cfg_layout.addWidget(QLabel("Port:"))
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(DEFAULT_PORT)
        self.port_spin.setFixedWidth(80)
        cfg_layout.addWidget(self.port_spin)

        cfg_layout.addStretch()
        root.addWidget(cfg_group)

        # Config path row
        cfg2_group = QGroupBox("Config File")
        cfg2_layout = QHBoxLayout(cfg2_group)
        cfg2_layout.setSpacing(8)
        cfg2_layout.addWidget(QLabel("config.json:"))
        self.config_edit = QLineEdit()
        self.config_edit.setPlaceholderText(r"Y:\Downloads\metube\harvstr\config.json  (leave blank for local)")
        cfg2_layout.addWidget(self.config_edit, stretch=1)
        root.addWidget(cfg2_group)

        # ── Status ────────────────────────────────────────────────────────────
        status_frame = QFrame()
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(4, 0, 4, 0)

        status_lbl = QLabel("Status:")
        status_lbl.setFixedWidth(52)
        status_layout.addWidget(status_lbl)

        self.status = StatusIndicator()
        status_layout.addWidget(self.status)
        root.addWidget(status_frame)

        # ── Buttons ───────────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_restart = QPushButton("Restart")
        self.btn_browser = QPushButton("Open in Browser")

        for btn in (self.btn_start, self.btn_stop, self.btn_restart, self.btn_browser):
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        self.btn_start.setStyleSheet("QPushButton { background: #388e3c; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px; } QPushButton:hover { background: #2e7d32; } QPushButton:disabled { background: #555; color: #999; }")
        self.btn_stop.setStyleSheet("QPushButton { background: #c62828; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px; } QPushButton:hover { background: #b71c1c; } QPushButton:disabled { background: #555; color: #999; }")
        self.btn_restart.setStyleSheet("QPushButton { background: #e65100; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px; } QPushButton:hover { background: #bf360c; } QPushButton:disabled { background: #555; color: #999; }")
        self.btn_browser.setStyleSheet("QPushButton { background: #1565c0; color: white; font-weight: bold; padding: 6px 18px; border-radius: 4px; } QPushButton:hover { background: #0d47a1; } QPushButton:disabled { background: #555; color: #999; }")

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addWidget(self.btn_restart)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_browser)

        self.btn_start.clicked.connect(self._start)
        self.btn_stop.clicked.connect(self._stop)
        self.btn_restart.clicked.connect(self._restart)
        self.btn_browser.clicked.connect(self._open_browser)

        root.addLayout(btn_row)

        # ── Log ───────────────────────────────────────────────────────────────
        log_group = QGroupBox("Server Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(6, 6, 6, 6)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(5000)
        mono = QFont("Consolas", 9)
        if not mono.exactMatch():
            mono = QFont("Courier New", 9)
        self.log.setFont(mono)
        self.log.setStyleSheet("background: #1e1e1e; color: #d4d4d4;")
        log_layout.addWidget(self.log)

        clear_btn = QPushButton("Clear Log")
        clear_btn.setFixedWidth(90)
        clear_btn.clicked.connect(self.log.clear)
        log_layout.addWidget(clear_btn, alignment=Qt.AlignmentFlag.AlignRight)

        root.addWidget(log_group, stretch=1)

        self._set_running_state(False)

    # ── Settings persistence ──────────────────────────────────────────────────

    def _restore_settings(self):
        self.host_edit.setText(self._settings.get("host", DEFAULT_HOST))
        self.port_spin.setValue(self._settings.get("port", DEFAULT_PORT))
        self.config_edit.setText(self._settings.get("config_path", ""))
        geo = self._settings.get("geometry")
        if geo:
            try:
                from PyQt6.QtCore import QByteArray
                self.restoreGeometry(QByteArray.fromHex(geo.encode()))
            except Exception:
                pass

    def _persist_settings(self):
        self._settings["host"] = self.host_edit.text().strip() or DEFAULT_HOST
        self._settings["port"] = self.port_spin.value()
        self._settings["config_path"] = self.config_edit.text().strip()
        try:
            self._settings["geometry"] = bytes(self.saveGeometry()).hex()
        except Exception:
            pass
        _save_settings(self._settings)

    def closeEvent(self, event):
        self._persist_settings()
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._append_log("[launcher] Stopping server before exit…")
            self._kill_tree()
            self._process.waitForFinished(3000)
        event.accept()

    # ── Process control ───────────────────────────────────────────────────────

    def _host(self) -> str:
        return self.host_edit.text().strip() or DEFAULT_HOST

    def _port(self) -> int:
        return self.port_spin.value()

    def _url(self) -> str:
        return f"http://{self._host()}:{self._port()}"

    def _start(self):
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._append_log("[launcher] Server already running.")
            return
        self._persist_settings()
        self._do_start()

    def _do_start(self):
        self.status.set_starting()
        self._set_running_state(False)

        proc = QProcess(self)
        # Run webui (and the downloader/tor it spawns) on the same Python that runs
        # this launcher — the global interpreter. No venv.
        proc.setProgram(sys.executable)
        cfg_path = self._settings.get("config_path", "").strip()
        args_list = [str(WEBUI_SCRIPT), "--host", self._host(), "--port", str(self._port())]
        if cfg_path:
            args_list += ["--config", cfg_path]
        proc.setArguments(args_list)

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUTF8", "1")
        proc.setProcessEnvironment(env)

        proc.readyReadStandardOutput.connect(self._on_stdout)
        proc.readyReadStandardError.connect(self._on_stderr)
        proc.finished.connect(self._on_finished)
        proc.errorOccurred.connect(self._on_error)

        self._process = proc
        proc.start()

        if not proc.waitForStarted(5000):
            self._append_log("[launcher] ERROR: failed to start process.")
            self.status.set_stopped()
            self._set_running_state(False)
            return

        self._append_log(f"[launcher] Started — {self._url()}")
        self.status.set_running(self._url())
        self._set_running_state(True)

    def _kill_tree(self):
        """Kill webui AND everything it spawned (downloaders, tor). QProcess.kill()
        only kills webui itself, orphaning its children; taskkill /T kills the
        whole process tree by PID."""
        proc = self._process
        if not proc:
            return
        pid = int(proc.processId())
        if pid > 0 and sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                return
            except Exception as e:
                self._append_log(f"[launcher] taskkill error: {e}")
        proc.kill()  # fallback: non-Windows, or taskkill unavailable/failed

    def _stop(self):
        if not self._process or self._process.state() == QProcess.ProcessState.NotRunning:
            self._append_log("[launcher] Server is not running.")
            return
        self._append_log("[launcher] Stopping server…")
        self._kill_tree()

    def _restart(self):
        if self._process and self._process.state() != QProcess.ProcessState.NotRunning:
            self._restart_pending = True
            self._append_log("[launcher] Restarting server…")
            self._kill_tree()
        else:
            self._do_start()

    def _open_browser(self):
        webbrowser.open(self._url())

    # ── Process signals ───────────────────────────────────────────────────────

    def _on_stdout(self):
        data = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            self._append_log(line)

    def _on_stderr(self):
        data = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        for line in data.splitlines():
            self._append_log(f"[stderr] {line}")

    def _on_finished(self, exit_code: int, exit_status):
        self._append_log(f"[launcher] Server stopped (exit code {exit_code})")
        self.status.set_stopped()
        self._set_running_state(False)
        self._process = None
        if self._restart_pending:
            self._restart_pending = False
            QTimer.singleShot(800, self._do_start)

    def _on_error(self, error):
        names = {
            QProcess.ProcessError.FailedToStart: "FailedToStart",
            QProcess.ProcessError.Crashed: "Crashed",
            QProcess.ProcessError.Timedout: "Timedout",
            QProcess.ProcessError.WriteError: "WriteError",
            QProcess.ProcessError.ReadError: "ReadError",
            QProcess.ProcessError.UnknownError: "UnknownError",
        }
        self._append_log(f"[launcher] Process error: {names.get(error, error)}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _append_log(self, text: str):
        self.log.appendPlainText(text)
        self.log.moveCursor(QTextCursor.MoveOperation.End)

    def _set_running_state(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.btn_restart.setEnabled(running)
        self.btn_browser.setEnabled(running)
        self.host_edit.setEnabled(not running)
        self.port_spin.setEnabled(not running)
        self.config_edit.setEnabled(not running)


def main():
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("C:/Scripts/Media/harvestr/config/assets/launch.png"))  # added by AI Icon Studio
    app.setApplicationName("Harvestr Launcher")
    app.setStyle("Fusion")

    # Dark palette
    from PyQt6.QtGui import QPalette
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(45, 45, 48))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.Base, QColor(30, 30, 30))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(50, 50, 50))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(30, 30, 30))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.Button, QColor(55, 55, 58))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    pal.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(38, 79, 120))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    app.setPalette(pal)

    win = LauncherWindow()
    win.show()
    # --- taskbar icon added by AI Icon Studio ---
    try:
        import ctypes
        ctypes.windll.user32.LoadImageW.restype = ctypes.c_void_p
        _hicon = ctypes.windll.user32.LoadImageW(None, "C:/Scripts/Media/harvestr/config/assets/launch.png", 1, 0, 0, 0x10 | 0x40)
        if _hicon:
            _hwnd = int(win.winId())
            ctypes.windll.user32.SendMessageW(_hwnd, 0x80, 1, _hicon)
            ctypes.windll.user32.SendMessageW(_hwnd, 0x80, 0, _hicon)
    except Exception as _icon_err:
        import sys as _sys
        print("AI Icon Studio: taskbar icon failed:", _icon_err, file=_sys.stderr)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
