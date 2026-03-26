from __future__ import annotations

import sys

from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


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

    def is_enabled(self) -> bool:
        return bool(self.services.config.get("minimize_to_tray") or self.services.config.get("close_to_tray"))

    def can_hide_to_tray(self) -> bool:
        return self.tray_icon is not None and self.is_enabled()

    def _build_menu(self) -> QMenu:
        tr = self.services.i18n.tr
        menu = QMenu()
        restore_action = QAction("Restore", menu)
        restore_action.triggered.connect(self._restore)
        menu.addAction(restore_action)

        restore_action.setText(tr("tray.menu.restore", "Restore"))

        quick_clipboard_action = QAction(tr("tray.menu.clipboard_quick", "Quick Clipboard"), menu)
        quick_clipboard_action.triggered.connect(self.services.clipboard_quick_panel.toggle)
        menu.addAction(quick_clipboard_action)

        clipboard_action = QAction(tr("tray.menu.clipboard", "Clipboard"), menu)
        clipboard_action.triggered.connect(lambda: self._window.open_plugin("clip_manager"))
        menu.addAction(clipboard_action)

        settings_action = QAction(tr("tray.menu.settings", "Settings"), menu)
        settings_action.triggered.connect(lambda: self._window.open_plugin("settings_center"))
        menu.addAction(settings_action)

        workflows_action = QAction(tr("tray.menu.workflows", "Workflows"), menu)
        workflows_action.triggered.connect(lambda: self._window.open_plugin("workflow_studio"))
        menu.addAction(workflows_action)

        menu.addSeparator()
        quit_action = QAction(tr("tray.menu.quit", "Quit"), menu)
        quit_action.triggered.connect(self._window.quit_from_tray)
        menu.addAction(quit_action)
        return menu

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
