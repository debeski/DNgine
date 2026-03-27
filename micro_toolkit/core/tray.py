from __future__ import annotations

import sys

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QSystemTrayIcon, QWidget, QWidgetAction


class TrayManager:
    def __init__(self, services):
        self.services = services
        self.tray_icon: QSystemTrayIcon | None = None
        self._window = None

    def attach(self, window) -> None:
        self._window = window
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.services.log("System tray is not available in this session.", "WARNING")
            self._sync_application_quit_policy()
            return

        if self.tray_icon is None:
            icon = self._tray_icon(window)
            self.tray_icon = QSystemTrayIcon(icon, window)
            self.tray_icon.setToolTip("Micro Toolkit")
            self.tray_icon.activated.connect(self._handle_activation)
            self.tray_icon.setContextMenu(self._build_menu())
            self.services.i18n.language_changed.connect(self._refresh_menu)
        self.sync_visibility()

    def sync_visibility(self) -> None:
        enabled = self.is_enabled()
        if self.tray_icon is None:
            self._sync_application_quit_policy()
            return
        self.tray_icon.setVisible(enabled)
        self._sync_application_quit_policy()

    def show_message(self, title: str, message: str) -> None:
        if self.tray_icon is not None:
            self.tray_icon.showMessage(title, message)

    def hide(self) -> None:
        if self.tray_icon is None:
            return
        self.tray_icon.hide()

    def is_enabled(self) -> bool:
        return bool(
            self.services.config.get("minimize_to_tray")
            or self.services.config.get("close_to_tray")
            or self.services.clip_monitor_enabled()
        )

    def can_hide_to_tray(self) -> bool:
        return self.tray_icon is not None and self.is_enabled()

    def _build_menu(self) -> QMenu:
        tr = self.services.i18n.tr
        menu = QMenu()
        menu.addAction(self._status_action(tr("tray.status.app", "App"), True))
        menu.addAction(
            self._status_action(
                tr("tray.status.clip_monitor", "Clip-Monitor"),
                self.services.clip_monitor_enabled() and self.services.clip_monitor_manager.is_running(),
            )
        )
        menu.addSeparator()

        restore_action = QAction("Restore", menu)
        restore_action.triggered.connect(self._restore)
        menu.addAction(restore_action)

        restore_action.setText(tr("tray.menu.restore", "Restore"))

        quick_clipboard_action = QAction(tr("tray.menu.clipboard_quick", "Quick Clipboard"), menu)
        quick_clipboard_action.triggered.connect(self.services.show_clipboard_quick_panel)
        menu.addAction(quick_clipboard_action)

        clipboard_action = QAction(tr("tray.menu.clipboard", "Clipboard"), menu)
        clipboard_action.triggered.connect(lambda: self._open_window_plugin("clip_snip"))
        menu.addAction(clipboard_action)

        settings_action = QAction(tr("tray.menu.settings", "Settings"), menu)
        settings_action.triggered.connect(lambda: self._open_window_plugin("command_center"))
        menu.addAction(settings_action)

        workflows_action = QAction(tr("tray.menu.workflows", "Workflows"), menu)
        workflows_action.triggered.connect(lambda: self._open_window_plugin("workflow_studio"))
        menu.addAction(workflows_action)

        menu.addSeparator()
        if self.services.clip_monitor_enabled():
            stop_monitor_action = QAction(tr("tray.menu.stop_clip_monitor", "Stop Clip-Monitor"), menu)
            stop_monitor_action.triggered.connect(lambda: self.services.set_clip_monitor_enabled(False))
            menu.addAction(stop_monitor_action)

        quit_action = QAction(tr("tray.menu.quit_app", "Quit App"), menu)
        quit_action.triggered.connect(self._window.quit_from_tray)
        menu.addAction(quit_action)
        return menu

    def _status_action(self, label: str, enabled: bool) -> QWidgetAction:
        tr = self.services.i18n.tr
        palette = self.services.theme_manager.current_palette()
        action = QWidgetAction(self._window)
        host = QWidget()
        row = QHBoxLayout(host)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(8)
        dot = QLabel()
        dot.setFixedWidth(12)
        dot.setText(f"<span style='color: {'#22c55e' if enabled else '#ef4444'};'>●</span>")
        text = QLabel(f"{label}: {tr('tray.status.on', 'ON') if enabled else tr('tray.status.off', 'OFF')}")
        text.setStyleSheet(f"font-weight: 600; color: {palette.text_primary};")
        row.addWidget(dot)
        row.addWidget(text, 1)
        action.setDefaultWidget(host)
        action.setEnabled(True)
        return action

    def _refresh_menu(self) -> None:
        if self.tray_icon is not None:
            self.tray_icon.setContextMenu(self._build_menu())

    def _handle_activation(self, reason) -> None:
        if reason in {QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick}:
            self._restore()

    def _restore(self) -> None:
        if self._window is None:
            return
        self._window.restore_from_tray()

    def _open_window_plugin(self, plugin_id: str) -> None:
        if self._window is None:
            return
        self._window.restore_from_tray()
        self._window.open_plugin(plugin_id)

    def _tray_icon(self, window) -> QIcon:
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
        return window.windowIcon()

    def _sync_application_quit_policy(self) -> None:
        app = self.services.application
        if app is None:
            return
        app.setQuitOnLastWindowClosed(not self.can_hide_to_tray())
