from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style, section_title_style
from micro_toolkit.core.plugin_api import QtPlugin


class InspectorCenterPlugin(QtPlugin):
    plugin_id = "inspector_center"
    name = "Inspector"
    description = "Developer inspection tools for exploring live Qt widgets, layout structure, and styles."
    category = ""
    standalone = True
    allow_name_override = False
    allow_icon_override = False
    preferred_icon = "inspect"

    def create_widget(self, services) -> QWidget:
        return InspectorCenterPage(services, self.plugin_id)


class InspectorCenterPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.summary_label: QLabel | None = None
        self.status_label: QLabel | None = None
        self.path_list: QListWidget | None = None
        self.details_view: QPlainTextEdit | None = None
        self.inspect_button: QPushButton | None = None
        self.copy_button: QPushButton | None = None
        self._last_snapshot: dict[str, object] = {}
        self._build_ui()
        self._apply_texts()
        self._refresh_state()
        self.services.ui_inspector.snapshot_changed.connect(self._handle_snapshot_changed)
        self.services.ui_inspector.inspect_mode_changed.connect(self._handle_inspect_mode_changed)
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._apply_styles)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        control_card = QFrame()
        self.control_card = control_card
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(18, 18, 18, 18)
        control_layout.setSpacing(12)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        control_layout.addWidget(self.status_label)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)
        self.inspect_button = QPushButton()
        self.inspect_button.clicked.connect(self._toggle_inspecting)
        button_row.addWidget(self.inspect_button)
        self.copy_button = QPushButton()
        self.copy_button.clicked.connect(self._copy_snapshot)
        button_row.addWidget(self.copy_button)
        button_row.addStretch(1)
        control_layout.addLayout(button_row)
        outer.addWidget(control_card)

        content_row = QHBoxLayout()
        content_row.setSpacing(14)

        path_card = QFrame()
        self.path_card = path_card
        path_layout = QVBoxLayout(path_card)
        path_layout.setContentsMargins(18, 18, 18, 18)
        path_layout.setSpacing(10)
        self.path_title = QLabel()
        path_layout.addWidget(self.path_title)
        self.path_list = QListWidget()
        path_layout.addWidget(self.path_list, 1)
        content_row.addWidget(path_card, 1)

        detail_card = QFrame()
        self.detail_card = detail_card
        detail_layout = QVBoxLayout(detail_card)
        detail_layout.setContentsMargins(18, 18, 18, 18)
        detail_layout.setSpacing(10)
        self.details_title = QLabel()
        detail_layout.addWidget(self.details_title)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        detail_layout.addWidget(self.summary_label)
        self.details_view = QPlainTextEdit()
        self.details_view.setReadOnly(True)
        detail_layout.addWidget(self.details_view, 1)
        content_row.addWidget(detail_card, 2)

        outer.addLayout(content_row, 1)
        self._apply_styles()

    def _apply_styles(self, *_args) -> None:
        palette = self.services.theme_manager.current_palette()
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=800))
        self.description_label.setStyleSheet(muted_text_style(palette, size=14))
        self.path_title.setStyleSheet(section_title_style(palette, size=18))
        self.details_title.setStyleSheet(section_title_style(palette, size=18))
        self.summary_label.setStyleSheet(muted_text_style(palette, size=13))
        self.status_label.setStyleSheet(muted_text_style(palette, size=13))
        for frame in (self.control_card, self.path_card, self.detail_card):
            frame.setStyleSheet(card_style(palette, radius=16))

    def _apply_texts(self, *_args) -> None:
        self.title_label.setText(self._pt("title", "Inspector"))
        self.description_label.setText(
            self._pt(
                "description",
                "Inspect live widgets in the running interface. Start inspect mode, hover the UI, then click a widget to capture its structure, palette, and stylesheet details.",
            )
        )
        self.path_title.setText(self._pt("path.title", "Parent Chain"))
        self.details_title.setText(self._pt("details.title", "Widget Details"))
        self.copy_button.setText(self._pt("copy", "Copy snapshot"))
        self._refresh_state()

    def _refresh_state(self) -> None:
        enabled = self.services.developer_mode_enabled()
        inspecting = self.services.ui_inspector.inspect_mode()
        self.inspect_button.setEnabled(enabled)
        self.copy_button.setEnabled(bool(self._last_snapshot))
        self.inspect_button.setText(
            self._pt("inspect.stop", "Stop inspecting") if inspecting else self._pt("inspect.start", "Start inspecting")
        )
        if not enabled:
            self.status_label.setText(
                self._pt("status.locked", "Developer mode is off. Enable it from Settings to use the inspector.")
            )
        elif inspecting:
            self.status_label.setText(
                self._pt("status.live", "Inspect mode is active. Hover a widget in the app and click once to capture it. Press Esc to cancel.")
            )
        else:
            self.status_label.setText(
                self._pt("status.ready", "Inspector is ready. Start inspect mode to capture a widget.")
            )
        if not self._last_snapshot:
            self.summary_label.setText(self._pt("summary.empty", "No widget selected yet."))
            self.details_view.setPlainText("")
            self.path_list.clear()

    def begin_inspecting(self) -> None:
        if self.services.developer_mode_enabled():
            self.services.ui_inspector.set_inspect_mode(True)

    def _toggle_inspecting(self) -> None:
        if not self.services.developer_mode_enabled():
            return
        self.services.ui_inspector.toggle_inspect_mode()

    def _handle_snapshot_changed(self, payload: dict[str, object]) -> None:
        self._last_snapshot = dict(payload)
        self.copy_button.setEnabled(True)
        class_name = str(payload.get("class_name") or "QWidget")
        object_name = str(payload.get("object_name") or "")
        geometry = str(payload.get("geometry") or "")
        self.summary_label.setText(
            self._pt(
                "summary.value",
                "Selected: {class_name}{object_suffix}\nGeometry: {geometry}",
                class_name=class_name,
                object_suffix=f"  #{object_name}" if object_name else "",
                geometry=geometry,
            )
        )
        self.path_list.clear()
        parent_chain = payload.get("parent_chain") or []
        for item in parent_chain:
            self.path_list.addItem(str(item))
        self.details_view.setPlainText(json.dumps(payload, indent=2, ensure_ascii=False))
        self._refresh_state()

    def _handle_inspect_mode_changed(self, _enabled: bool) -> None:
        self._refresh_state()

    def _copy_snapshot(self) -> None:
        if not self._last_snapshot:
            return
        QApplication.clipboard().setText(json.dumps(self._last_snapshot, indent=2, ensure_ascii=False))
