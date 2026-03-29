from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import socketserver
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QWidget, QWidgetAction

from dngine import APP_NAME, __version__
from dngine.core.app_config import AppConfig
from dngine.core.clipboard_quick_panel import ClipboardQuickPanel
from dngine.core.clipboard_store import ClipboardStore
from dngine.core.hotkey_helper import HotkeyHelperManager
from dngine.core.i18n import TranslationManager
from dngine.core.runtime_launch import build_background_subcommand_args, gui_executable, project_root, pythonpath_env
from dngine.core.storage_paths import CONFIG_FILENAME, DATABASE_FILENAME, LEGACY_CONFIG_FILENAME, LEGACY_DATABASE_FILENAME, resolve_runtime_path, standard_storage_root
from dngine.core.theme import ThemeManager

try:
    import keyboard as keyboard_backend
except Exception:
    keyboard_backend = None

def build_gui_launch_args(*, plugin_id: str | None = None, start_minimized: bool = False, force_visible: bool = False) -> list[str]:
    if getattr(sys, "frozen", False):
        args = [gui_executable(), "gui"]
    else:
        args = [sys.executable, "-m", "dngine", "gui"]
    if plugin_id:
        args.extend(["--plugin-id", plugin_id])
    if start_minimized:
        args.append("--start-minimized")
    if force_visible:
        args.append("--force-visible")
    return args


def build_clip_monitor_launch_args() -> list[str]:
    return build_background_subcommand_args("clip-monitor")


def _pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


class _MonitorLogger:
    def log(self, message: str, level: str = "INFO") -> None:
        print(f"[clip-monitor:{level}] {message}", flush=True)


class _MonitorServices(QObject):
    def __init__(self):
        super().__init__()
        self.app_root = Path(__file__).resolve().parents[1]
        self.storage_root = standard_storage_root()
        self.data_root = self.storage_root / "data"
        self.assets_root = self.app_root / "assets"
        self.locales_root = self.app_root / "i18n"
        self.config_path = resolve_runtime_path(self.data_root, CONFIG_FILENAME, LEGACY_CONFIG_FILENAME)
        self.output_root = self.storage_root / "output"
        self.database_path = resolve_runtime_path(self.data_root, DATABASE_FILENAME, LEGACY_DATABASE_FILENAME)
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.config = AppConfig(self.config_path, self.output_root, self.database_path)
        self.i18n = TranslationManager(self.config, self.locales_root)
        self.theme_manager = ThemeManager(self.config, self.assets_root)
        self.logger = _MonitorLogger()

    def resource_path(self, relative_path: str) -> Path:
        return self.assets_root / relative_path

    def log(self, message: str, level: str = "INFO") -> None:
        self.logger.log(message, level)

    def reload_live_preferences(self, application: QApplication) -> None:
        self.config.load()
        self.theme_manager.load_from_config()
        self.i18n.load_from_config()
        self.theme_manager.apply(application)
        self.i18n.apply(application)


class ClipboardMonitor(QObject):
    captured = Signal()

    def __init__(self, store: ClipboardStore, clipboard, logger=None):
        super().__init__()
        self.store = store
        self.clipboard = clipboard
        self.logger = logger
        self._enabled = True
        self._ignore_once = False
        self.clipboard.dataChanged.connect(self._handle_clipboard_changed)

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def ignore_next_change(self) -> None:
        self._ignore_once = True

    def capture_current(self) -> bool:
        inserted = self.store.add_mime_entry(self.clipboard.mimeData())
        if inserted and self.logger is not None:
            self.logger.log("Clipboard entry captured.")
        if inserted:
            self.captured.emit()
        return inserted

    def _handle_clipboard_changed(self) -> None:
        if self._ignore_once:
            self._ignore_once = False
            return
        if not self._enabled:
            return
        self.capture_current()


class _MonitorRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        runtime = self.server.runtime  # type: ignore[attr-defined]
        while True:
            line = self.rfile.readline()
            if not line:
                break
            try:
                payload = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if payload.get("token") != runtime.token:
                self.wfile.write(b"{\"ok\": false, \"error\": \"unauthorized\"}\n")
                self.wfile.flush()
                continue
            command = str(payload.get("command") or "").strip()
            body = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
            result = runtime.handle_command(command, body)
            self.wfile.write((json.dumps(result, ensure_ascii=False) + "\n").encode("utf-8"))
            self.wfile.flush()


class _ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


class MonitorQuickHotkey(QObject):
    def __init__(self, services: _MonitorServices, toggle_callback):
        super().__init__()
        self.services = services
        self.toggle_callback = toggle_callback
        self.helper_manager = HotkeyHelperManager(self.services.data_root, self.services.logger)
        self.helper_manager.action_requested.connect(self._handle_helper_action)
        self._hotkey_handle = None
        self._using_helper = False
        self._current_sequence = ""
        self._current_enabled = False
        self._blocked_sequence = ""
        self._helper_allowed = False

    def set_helper_allowed(self, allowed: bool) -> None:
        allowed = bool(allowed)
        if self._helper_allowed == allowed:
            return
        self._helper_allowed = allowed
        self._blocked_sequence = ""

    def refresh(self, *, enabled: bool) -> None:
        hotkeys = self.services.config.get("hotkeys") or {}
        binding = hotkeys.get("show_clipboard_quick_panel", {}) if isinstance(hotkeys, dict) else {}
        sequence = str(binding.get("sequence", "Ctrl+Alt+V")).strip()
        scope = str(binding.get("scope", "global")).strip().lower()
        should_enable = bool(enabled and sequence and scope == "global")
        if not should_enable:
            self._clear()
            return
        if self._blocked_sequence and self._blocked_sequence == sequence:
            return
        if self._current_enabled and self._current_sequence == sequence:
            if self._hotkey_handle is not None:
                return
            if self._using_helper and self.helper_manager.is_active():
                return
        self._clear()
        if self._direct_hotkeys_supported():
            try:
                self._hotkey_handle = keyboard_backend.add_hotkey(sequence, self.toggle_callback)
                self._current_sequence = sequence
                self._current_enabled = True
                return
            except Exception as exc:
                self.services.log(f"Clip-Monitor hotkey fallback triggered: {exc}", "WARNING")
        if self._helper_allowed and self.helper_manager.can_request_helper():
            success, message = self.helper_manager.enable_for_session({"show_clipboard_quick_panel": sequence})
            self._using_helper = success
            if not success:
                self.services.log(message, "WARNING")
                self._blocked_sequence = sequence
                return
            self._current_sequence = sequence
            self._current_enabled = True
            self._blocked_sequence = ""
            return
        self._current_sequence = sequence

    def shutdown(self) -> None:
        self._clear()

    def _handle_helper_action(self, action_id: str) -> None:
        if action_id == "show_clipboard_quick_panel":
            self.toggle_callback()

    def _clear(self) -> None:
        if keyboard_backend is not None and self._hotkey_handle is not None:
            try:
                keyboard_backend.remove_hotkey(self._hotkey_handle)
            except Exception:
                pass
        self._hotkey_handle = None
        if self._using_helper:
            self.helper_manager.disable_for_session()
        self._using_helper = False
        self._current_sequence = ""
        self._current_enabled = False
        self._blocked_sequence = ""

    @staticmethod
    def _direct_hotkeys_supported() -> bool:
        if keyboard_backend is None:
            return False
        if sys.platform.startswith("linux"):
            geteuid = getattr(os, "geteuid", None)
            if callable(geteuid) and geteuid() != 0:
                return False
        return True


class ClipMonitorRuntime(QObject):
    def __init__(self, application: QApplication):
        super().__init__()
        self.application = application
        self.services = _MonitorServices()
        self.services.reload_live_preferences(self.application)
        self.runtime_root = self.services.data_root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.runtime_path = self.runtime_root / "clip_monitor_runtime.json"
        self.pid_path = self.runtime_root / "clip_monitor.pid"
        self.token = os.urandom(24).hex()
        self._app_active = False
        self._app_pid: int | None = None
        self._helper_allowed = False
        self._config_mtime = 0.0
        self._server, self._server_thread = self._start_server()
        self.store = ClipboardStore(self.services.database_path)
        self.clipboard = QGuiApplication.clipboard()
        self.monitor = ClipboardMonitor(self.store, self.clipboard, logger=self.services)
        self.quick_panel = ClipboardQuickPanel(
            self.services,
            open_full_callback=self.open_full_clipboard,
            before_restore_callback=self.monitor.ignore_next_change,
        )
        self.quick_panel.hide()
        self.hotkey_controller = MonitorQuickHotkey(self.services, self.toggle_quick_panel)
        self.tray_icon: QSystemTrayIcon | None = None
        self._tray_menu: QMenu | None = None
        self._app_status_dot: QLabel | None = None
        self._app_status_text: QLabel | None = None
        self._monitor_status_dot: QLabel | None = None
        self._monitor_status_text: QLabel | None = None
        self._last_tray_visible: bool | None = None
        self._status_timer = QTimer(self)
        self._status_timer.setInterval(900)
        self._status_timer.timeout.connect(self._tick)
        self._status_timer.start()
        self._create_tray_icon()
        self._write_runtime_file()
        self._refresh_state(force=True)
        self.pid_path.write_text(str(os.getpid()), encoding="utf-8")

    def handle_command(self, command: str, payload: dict) -> dict:
        if command == "ping":
            return self._status_payload()
        if command == "toggle_quick_panel":
            QTimer.singleShot(0, self.toggle_quick_panel)
            return {"ok": True}
        if command == "show_quick_panel":
            QTimer.singleShot(0, self.show_quick_panel)
            return {"ok": True}
        if command == "set_app_state":
            active = bool(payload.get("active"))
            self._helper_allowed = bool(payload.get("prefer_helper"))
            pid = payload.get("pid")
            try:
                self._app_pid = int(pid) if pid is not None else None
            except Exception:
                self._app_pid = None
            self._app_active = active
            self.hotkey_controller.set_helper_allowed(self._helper_allowed)
            QTimer.singleShot(0, self._refresh_state)
            return self._status_payload()
        if command == "refresh_preferences":
            QTimer.singleShot(0, self._refresh_state)
            return self._status_payload()
        if command == "stop":
            persist = bool(payload.get("persist_disabled", True))
            if persist:
                self.services.config.set("clip_monitor_enabled", False)
            QTimer.singleShot(0, self.shutdown)
            return {"ok": True}
        if command == "open_clipboard":
            QTimer.singleShot(0, self.open_full_clipboard)
            return {"ok": True}
        return {"ok": False, "error": f"Unknown command: {command}"}

    def toggle_quick_panel(self) -> None:
        self._refresh_state()
        self.quick_panel.toggle()

    def show_quick_panel(self) -> None:
        self._refresh_state()
        if not self.quick_panel.isVisible():
            self.quick_panel.toggle()

    def open_full_clipboard(self) -> None:
        env = pythonpath_env()
        subprocess.Popen(
            build_gui_launch_args(plugin_id="clip_snip", force_visible=True),
            cwd=str(project_root()) if not getattr(sys, "frozen", False) else None,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

    def open_main_app(self) -> None:
        env = pythonpath_env()
        subprocess.Popen(
            build_gui_launch_args(force_visible=True),
            cwd=str(project_root()) if not getattr(sys, "frozen", False) else None,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )

    def shutdown(self) -> None:
        self.hotkey_controller.shutdown()
        if self.tray_icon is not None:
            self.tray_icon.hide()
        try:
            self._server.shutdown()
        except Exception:
            pass
        try:
            self._server.server_close()
        except Exception:
            pass
        for path in (self.runtime_path, self.pid_path):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        self.application.quit()

    def _status_payload(self) -> dict:
        return {
            "ok": True,
            "app_active": self._app_active,
            "clip_monitor_enabled": bool(self.services.config.get("clip_monitor_enabled")),
            "pid": os.getpid(),
        }

    def _start_server(self):
        server = _ThreadedTCPServer(("127.0.0.1", 0), _MonitorRequestHandler)
        server.runtime = self  # type: ignore[attr-defined]
        thread = threading.Thread(target=server.serve_forever, daemon=True, name="microtk-clip-monitor-ipc")
        thread.start()
        return server, thread

    def _write_runtime_file(self) -> None:
        payload = {
            "pid": os.getpid(),
            "port": int(self._server.server_address[1]),
            "token": self.token,
        }
        self.runtime_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _tick(self) -> None:
        if self._app_active and not _pid_alive(self._app_pid):
            self._app_active = False
        self._refresh_state()

    def _refresh_state(self, *, force: bool = False) -> None:
        try:
            config_mtime = self.services.config_path.stat().st_mtime
        except OSError:
            config_mtime = 0.0
        config_changed = force or config_mtime != self._config_mtime
        if config_changed:
            self._config_mtime = config_mtime
            self.services.reload_live_preferences(self.application)
            self.quick_panel.refresh_ui()
        monitor_enabled = bool(self.services.config.get("clip_monitor_enabled"))
        self.monitor.set_enabled(monitor_enabled)
        tray_visible = monitor_enabled and not self._app_active
        self.hotkey_controller.refresh(enabled=tray_visible)
        self._refresh_tray(tray_visible, force=config_changed)

    def _create_tray_icon(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray_icon = QSystemTrayIcon(self._tray_icon(), self.application)
        self.tray_icon.setToolTip(APP_NAME)
        self.tray_icon.activated.connect(self._handle_tray_activation)
        self._tray_menu = self._build_menu()
        self.tray_icon.setContextMenu(self._tray_menu)
        self._refresh_tray(False, force=True)

    def _refresh_tray(self, visible: bool, *, force: bool = False) -> None:
        if self.tray_icon is None:
            return
        self._update_status_widgets()
        if force or self._last_tray_visible != bool(visible):
            self.tray_icon.setVisible(bool(visible))
            self._last_tray_visible = bool(visible)

    def _build_menu(self) -> QMenu:
        tr = self.services.i18n.tr
        menu = QMenu()
        menu.addAction(self._status_action("app", tr("tray.status.app", "App"), self._app_active))
        menu.addAction(self._status_action("monitor", tr("tray.status.clip_monitor", "Clip-Monitor"), bool(self.services.config.get("clip_monitor_enabled"))))
        menu.addSeparator()

        quick_action = QAction(tr("tray.menu.clipboard_quick", "Quick Clipboard"), menu)
        quick_action.triggered.connect(self.toggle_quick_panel)
        menu.addAction(quick_action)

        clipboard_action = QAction(tr("tray.menu.clipboard", "Clipboard"), menu)
        clipboard_action.triggered.connect(self.open_full_clipboard)
        menu.addAction(clipboard_action)

        open_app_action = QAction(tr("tray.menu.open_main_app", "Open Main App"), menu)
        open_app_action.triggered.connect(lambda: self.open_main_app() if not self._app_active else None)
        menu.addAction(open_app_action)

        menu.addSeparator()
        stop_action = QAction(tr("tray.menu.stop_clip_monitor", "Stop Clip-Monitor"), menu)
        stop_action.triggered.connect(lambda: self.handle_command("stop", {"persist_disabled": True}))
        menu.addAction(stop_action)
        return menu

    def _status_action(self, key: str, label: str, enabled: bool) -> QWidgetAction:
        action = QWidgetAction(self.application)
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        dot = QLabel()
        dot.setFixedWidth(12)
        text = QLabel()
        row.addWidget(dot)
        row.addWidget(text, 1)
        action.setDefaultWidget(host)
        action.setEnabled(True)
        if key == "app":
            self._app_status_dot = dot
            self._app_status_text = text
        else:
            self._monitor_status_dot = dot
            self._monitor_status_text = text
        self._update_status_widget(dot, text, label, enabled)
        return action

    def _update_status_widgets(self) -> None:
        tr = self.services.i18n.tr
        if self._app_status_dot is not None and self._app_status_text is not None:
            self._update_status_widget(self._app_status_dot, self._app_status_text, tr("tray.status.app", "App"), self._app_active)
        if self._monitor_status_dot is not None and self._monitor_status_text is not None:
            self._update_status_widget(
                self._monitor_status_dot,
                self._monitor_status_text,
                tr("tray.status.clip_monitor", "Clip-Monitor"),
                bool(self.services.config.get("clip_monitor_enabled")),
            )

    def _update_status_widget(self, dot: QLabel, text: QLabel, label: str, enabled: bool) -> None:
        tr = self.services.i18n.tr
        palette = self.services.theme_manager.current_palette()
        dot.setText(f"<span style='color: {'#22c55e' if enabled else '#ef4444'};'>●</span>")
        text.setText(f"{label}: {tr('tray.status.on', 'ON') if enabled else tr('tray.status.off', 'OFF')}")
        text.setStyleSheet(f"font-weight: 600; color: {palette.text_primary};")

    def _handle_tray_activation(self, reason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self.toggle_quick_panel()

    def _tray_icon(self) -> QIcon:
        candidates = []
        if sys.platform == "darwin":
            candidates.extend(
                [
                    self.services.resource_path("icons/app-indicator.svg"),
                    self.services.resource_path("app.icns"),
                ]
            )
        candidates.append(self.services.resource_path("app.ico"))
        for icon_path in candidates:
            if icon_path.exists():
                icon = QIcon(str(icon_path))
                if not icon.isNull():
                    return icon
        return QIcon()


class ClipMonitorManager(QObject):
    status_changed = Signal()

    def __init__(self, config, data_root: Path):
        super().__init__()
        self.config = config
        self.data_root = Path(data_root)
        self.runtime_root = self.data_root / "runtime"
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self.runtime_path = self.runtime_root / "clip_monitor_runtime.json"
        self._process: subprocess.Popen | None = None

    def is_enabled(self) -> bool:
        return bool(self.config.get("clip_monitor_enabled"))

    def is_running(self) -> bool:
        runtime = self._runtime_info()
        return runtime is not None and self._ping(runtime) is not None

    def ensure_running(self) -> bool:
        if not self.is_enabled():
            return False
        runtime = self._runtime_info()
        if runtime is not None and self._ping(runtime) is not None:
            return True
        env = pythonpath_env()
        self._process = subprocess.Popen(
            build_clip_monitor_launch_args(),
            cwd=str(project_root()) if not getattr(sys, "frozen", False) else None,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        deadline = time.time() + 12.0
        while time.time() < deadline:
            runtime = self._runtime_info()
            if runtime is not None and self._ping(runtime) is not None:
                self.status_changed.emit()
                return True
            time.sleep(0.1)
        return False

    def set_app_active(self, active: bool, pid: int | None = None, *, prefer_helper: bool = False) -> bool:
        runtime = self._runtime_info()
        if runtime is None:
            return False
        result = self._request(
            "set_app_state",
            {
                "active": bool(active),
                "pid": pid,
                "prefer_helper": bool(prefer_helper),
            },
        )
        self.status_changed.emit()
        return bool(result and result.get("ok"))

    def refresh_preferences(self) -> None:
        if self.is_running():
            self._request("refresh_preferences", {})
            self.status_changed.emit()

    def toggle_quick_panel(self) -> bool:
        result = self._request("toggle_quick_panel", {})
        return bool(result and result.get("ok"))

    def stop(self, *, persist_disabled: bool = True) -> bool:
        runtime = self._runtime_info()
        monitor_pid = int(runtime["pid"]) if runtime else None
        result = self._request("stop", {"persist_disabled": persist_disabled}, runtime=runtime)
        if persist_disabled:
            self.config.set("clip_monitor_enabled", False)
        # Wait for the monitor process to actually exit so macOS does not
        # leave a stale dock icon behind.
        if monitor_pid and _pid_alive(monitor_pid):
            deadline = time.time() + 3.0
            while time.time() < deadline and _pid_alive(monitor_pid):
                time.sleep(0.05)
            # If it's still alive, force-terminate.
            if _pid_alive(monitor_pid):
                try:
                    os.kill(monitor_pid, signal.SIGKILL if hasattr(signal, "SIGKILL") else signal.SIGTERM)
                except OSError:
                    pass
        # Clean up any leftover runtime files.
        for path in (self.runtime_path, self.runtime_root / "clip_monitor.pid"):
            try:
                if path.exists():
                    path.unlink()
            except Exception:
                pass
        if self._process is not None:
            try:
                self._process.wait(timeout=1.0)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None
        self.status_changed.emit()
        return bool(result and result.get("ok"))

    def app_status_on(self) -> bool:
        runtime = self._runtime_info()
        payload = self._ping(runtime) if runtime is not None else None
        return bool(payload and payload.get("app_active"))

    def _ping(self, runtime: dict | None):
        if runtime is None:
            return None
        return self._request("ping", {}, runtime=runtime)

    def _runtime_info(self) -> dict | None:
        if not self.runtime_path.exists():
            return None
        try:
            payload = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        try:
            payload["port"] = int(payload.get("port"))
            payload["pid"] = int(payload.get("pid"))
        except Exception:
            return None
        if not _pid_alive(payload["pid"]):
            return None
        return payload

    def _request(self, command: str, payload: dict, *, runtime: dict | None = None) -> dict | None:
        runtime = runtime or self._runtime_info()
        if runtime is None:
            return None
        message = {
            "token": runtime.get("token"),
            "command": command,
            "payload": payload,
        }
        try:
            with socket.create_connection(("127.0.0.1", int(runtime["port"])), timeout=1.5) as connection:
                connection.sendall((json.dumps(message) + "\n").encode("utf-8"))
                response = b""
                while not response.endswith(b"\n"):
                    chunk = connection.recv(4096)
                    if not chunk:
                        break
                    response += chunk
        except OSError:
            return None
        try:
            return json.loads(response.decode("utf-8").strip())
        except Exception:
            return None


def build_clip_monitor_parser(subparsers) -> None:
    subparsers.add_parser("clip-monitor", help=argparse.SUPPRESS)


def run_clip_monitor_service(_args) -> int:
    # NOTE: macOS dock-icon suppression is handled in __main__.py *before*
    # PySide6 is imported.  It cannot be done here because the import of
    # this module already triggers AppKit/NSApplication initialisation.
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(f"{APP_NAME} Clip Monitor")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)
    runtime = ClipMonitorRuntime(app)

    def _cleanup(*_args):
        runtime.shutdown()

    signal.signal(signal.SIGTERM, _cleanup)
    signal.signal(signal.SIGINT, _cleanup)
    return app.exec()
