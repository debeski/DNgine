from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from dngine.core.page_style import apply_page_chrome, apply_semantic_class, muted_text_style, section_title_style
from dngine.core.widgets import DroppableListWidget, InfoCardWidget, MetricDonutWidget, PathLineEdit, ScrollSafeComboBox
from dngine.sdk.i18n import _pt, apply_direction, bind_tr


class SDKPage(QWidget):
    def __init__(self):
        super().__init__()
        self.generated_widgets: dict[str, QWidget] = {}
        self.generated_actions: dict[str, QPushButton] = {}
        self.generated_fields: dict[str, object] = {}
        self.generated_sections: dict[str, object] = {}
        self.generated_task_specs: dict[str, object] = {}
        self._chrome_cards: list[QFrame] = []
        self._title_label: QLabel | None = None
        self._description_label: QLabel | None = None
        self._summary_label: QLabel | None = None
        self._section_title_labels: list[QLabel] = []
        self._body_labels: list[QLabel] = []
        self._sdk_runtime = None

    def apply_sdk_chrome(self, services) -> None:
        palette = services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self._title_label,
            description_label=self._description_label,
            cards=self._chrome_cards,
            summary_label=self._summary_label,
        )
        for label in self._section_title_labels:
            label.setStyleSheet(section_title_style(palette))
        for label in self._body_labels:
            label.setStyleSheet(muted_text_style(palette))


class TextPanelWidget(QFrame):
    def __init__(self, title: str, placeholder: str = "", default: str = "", *, read_only: bool = True, semantic_class: str = "output_class"):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        self.title_label = QLabel(title)
        layout.addWidget(self.title_label)
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(bool(read_only))
        self.editor.setPlaceholderText(placeholder)
        if default not in {None, ""}:
            self.editor.setPlainText(str(default))
        apply_semantic_class(self.editor, semantic_class or "output_class")
        layout.addWidget(self.editor, 1)

    def set_title(self, title: str) -> None:
        self.title_label.setText(title)

    def set_placeholder(self, text: str) -> None:
        self.editor.setPlaceholderText(text)

    def set_text(self, text: str) -> None:
        self.editor.setPlainText(str(text or ""))

    def toPlainText(self) -> str:
        return self.editor.toPlainText()

    def blockSignals(self, block: bool) -> bool:
        previous = super().blockSignals(block)
        self.editor.blockSignals(block)
        return previous


def _apply_table_widget_data(widget: QTableWidget, field_spec) -> None:
    headers = [str(header) for header in (field_spec.table_headers or ())]
    rows = [[str(value) for value in row] for row in (field_spec.table_rows or ())]
    widget.setColumnCount(len(headers))
    if headers:
        widget.setHorizontalHeaderLabels(headers)
    widget.setRowCount(len(rows))
    for row_index, row_values in enumerate(rows):
        if widget.columnCount() < len(row_values):
            widget.setColumnCount(len(row_values))
        for column, value in enumerate(row_values):
            item = QTableWidgetItem(str(value))
            item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
            widget.setItem(row_index, column, item)


def _build_field_widget(field_spec):
    kind = str(field_spec.kind or "text").strip().lower()
    if kind == "multiline":
        widget = QPlainTextEdit()
        widget.setPlaceholderText(field_spec.placeholder)
        if field_spec.default not in {None, ""}:
            widget.setPlainText(str(field_spec.default))
        widget.setReadOnly(bool(field_spec.read_only))
        return widget
    if kind == "text_panel":
        return TextPanelWidget(
            field_spec.label,
            field_spec.placeholder,
            "" if field_spec.default is None else str(field_spec.default),
            read_only=bool(field_spec.read_only),
            semantic_class=field_spec.semantic_class or "output_class",
        )
    if kind == "choice":
        widget = ScrollSafeComboBox()
        for option in field_spec.options:
            widget.addItem(option.label, option.value)
        if field_spec.default not in {None, ""}:
            index = widget.findData(field_spec.default)
            if index >= 0:
                widget.setCurrentIndex(index)
        return widget
    if kind == "toggle":
        widget = QCheckBox()
        widget.setChecked(bool(field_spec.default))
        widget.setText(field_spec.placeholder or "")
        return widget
    if kind == "numeric":
        if isinstance(field_spec.default, float):
            widget = QDoubleSpinBox()
        else:
            widget = QSpinBox()
        if field_spec.min_value is not None:
            widget.setMinimum(field_spec.min_value)
        if field_spec.max_value is not None:
            widget.setMaximum(field_spec.max_value)
        if field_spec.default is not None:
            widget.setValue(field_spec.default)
        return widget
    if kind == "path":
        widget = PathLineEdit(mode=str(field_spec.path_mode or "any"), allowed_extensions=list(field_spec.allowed_extensions))
        widget.setPlaceholderText(field_spec.placeholder)
        if field_spec.default:
            widget.setText(str(field_spec.default))
        widget.setReadOnly(bool(field_spec.read_only))
        return widget
    if kind == "file_list":
        mode = str(field_spec.path_mode) if field_spec.path_mode else "file"
        widget = DroppableListWidget(mode=mode, allowed_extensions=list(field_spec.allowed_extensions))
        if field_spec.semantic_class:
            apply_semantic_class(widget, field_spec.semantic_class)
        return widget
    if kind == "table":
        widget = QTableWidget(0, 0)
        widget.setAlternatingRowColors(True)
        widget.verticalHeader().setVisible(False)
        widget.horizontalHeader().setStretchLastSection(True)
        widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        widget.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        _apply_table_widget_data(widget, field_spec)
        if field_spec.semantic_class:
            apply_semantic_class(widget, field_spec.semantic_class)
        return widget
    if kind == "preview":
        widget = QLabel(field_spec.placeholder or "")
        widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        apply_semantic_class(widget, field_spec.semantic_class or "preview_class")
        return widget
    if kind == "donut":
        widget = MetricDonutWidget(field_spec.label)
        widget.set_metric(
            0.0,
            caption=field_spec.default or "",
            accent=field_spec.placeholder or "",
            remainder=field_spec.help_text or ""
        )
        return widget
    if kind == "info_card_field":
        widget = InfoCardWidget(field_spec.label)
        widget.set_rows(list(field_spec.table_rows or ()))
        return widget
    widget = QLineEdit()
    widget.setPlaceholderText(field_spec.placeholder)
    if field_spec.default not in {None, ""}:
        widget.setText(str(field_spec.default))
    widget.setReadOnly(bool(field_spec.read_only))
    return widget


def _build_section_widget(page, page_spec, section):
    kind = str(section.kind).strip().lower()
    if kind == "file_list":
        field_spec = section.fields[0] if section.fields else None
        if field_spec is not None and str(field_spec.kind).strip().lower() == "file_list":
            widget = _build_field_widget(field_spec)
            page.generated_widgets[field_spec.field_id] = widget
            page.generated_fields[field_spec.field_id] = field_spec
        else:
            widget = DroppableListWidget(mode="file")
        page.generated_widgets[section.section_id] = widget
        return widget
    if kind == "preview_pane":
        field_spec = section.fields[0] if section.fields else None
        if field_spec is not None and str(field_spec.kind).strip().lower() == "preview":
            widget = _build_field_widget(field_spec)
            page.generated_widgets[field_spec.field_id] = widget
            page.generated_fields[field_spec.field_id] = field_spec
        else:
            widget = QLabel(section.description or page_spec.result_spec.preview_placeholder)
            widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            apply_semantic_class(widget, section.semantic_class or "preview_class")
        page.generated_widgets[section.section_id] = widget
        return widget
    if kind == "table_pane":
        field_spec = section.fields[0] if section.fields else None
        if field_spec is not None and str(field_spec.kind).strip().lower() == "table":
            widget = _build_field_widget(field_spec)
            page.generated_widgets[field_spec.field_id] = widget
            page.generated_fields[field_spec.field_id] = field_spec
        else:
            widget = QTableWidget(0, 0)
            apply_semantic_class(widget, section.semantic_class or "output_class")
        page.generated_widgets[section.section_id] = widget
        return widget
    if kind == "details_pane":
        field_spec = section.fields[0] if section.fields else None
        if field_spec is not None and str(field_spec.kind).strip().lower() == "multiline":
            widget = _build_field_widget(field_spec)
            widget.setReadOnly(True)
            page.generated_widgets[field_spec.field_id] = widget
            page.generated_fields[field_spec.field_id] = field_spec
        else:
            widget = QPlainTextEdit()
            widget.setReadOnly(True)
            widget.setPlaceholderText(section.description or page_spec.result_spec.details_placeholder)
            apply_semantic_class(widget, section.semantic_class or "output_class")
        page.generated_widgets[section.section_id] = widget
        return widget
    if kind == "text_panel":
        field_spec = section.fields[0] if section.fields else None
        if field_spec is not None and str(field_spec.kind).strip().lower() == "text_panel":
            widget = _build_field_widget(field_spec)
            page.generated_widgets[field_spec.field_id] = widget
            page.generated_fields[field_spec.field_id] = field_spec
        else:
            widget = TextPanelWidget(section.title or "", section.description or "")
        page.generated_widgets[section.section_id] = widget
        return widget
    if kind == "table_details_pane":
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        for field_spec in section.fields:
            field_kind = str(field_spec.kind).strip().lower()
            widget = _build_field_widget(field_spec)
            if field_kind == "multiline":
                widget.setReadOnly(True)
                apply_semantic_class(widget, field_spec.semantic_class or "output_class")
            elif field_kind == "table":
                apply_semantic_class(widget, field_spec.semantic_class or "output_class")
            page.generated_widgets[field_spec.field_id] = widget
            page.generated_fields[field_spec.field_id] = field_spec
            layout.addWidget(widget, 1)
        page.generated_widgets[section.section_id] = container
        return container
    return None


def render_page_spec(services, plugin_id: str, page_spec):
    page = SDKPage()
    apply_direction(page, services)

    outer = QVBoxLayout(page)
    outer.setContentsMargins(28, 28, 28, 28)
    outer.setSpacing(16)

    title_label = QLabel(page_spec.title)
    outer.addWidget(title_label)
    page.generated_widgets["page.title"] = title_label
    page._title_label = title_label

    description_label = QLabel(page_spec.description)
    description_label.setWordWrap(True)
    outer.addWidget(description_label)
    page.generated_widgets["page.description"] = description_label
    page._description_label = description_label

    cards: list[QFrame] = []
    result_summary_label = None

    sections = list(page_spec.sections)
    for section in sections:
        page.generated_sections[section.section_id] = section

    task_specs = list(page_spec.task_specs or ())
    for task_spec in task_specs:
        page.generated_task_specs[task_spec.task_id] = task_spec

    index = 0
    while index < len(sections):
        section = sections[index]
        kind = str(section.kind).strip().lower()
        if kind == "settings_card":
            card = QFrame()
            form = QFormLayout(card)
            form.setContentsMargins(16, 14, 16, 14)
            form.setSpacing(10)
            for field_spec in section.fields:
                widget = _build_field_widget(field_spec)
                label_widget = QLabel(field_spec.label)
                if field_spec.help_text:
                    widget.setToolTip(field_spec.help_text)
                page.generated_widgets[field_spec.field_id] = widget
                page.generated_widgets[f"{field_spec.field_id}.label"] = label_widget
                page.generated_fields[field_spec.field_id] = field_spec
                if str(field_spec.kind).strip().lower() == "toggle":
                    widget.setText(field_spec.placeholder or field_spec.label)
                form.addRow(label_widget, widget)
            outer.addWidget(card)
            cards.append(card)
            page.generated_widgets[section.section_id] = card
            index += 1
            continue

        if kind == "row":
            row_layout = QHBoxLayout()
            row_layout.setSpacing(14)
            for field_spec in section.fields:
                widget = _build_field_widget(field_spec)
                page.generated_widgets[field_spec.field_id] = widget
                page.generated_fields[field_spec.field_id] = field_spec
                if isinstance(widget, QFrame):
                    cards.append(widget)
                title_label = getattr(widget, "title_label", None)
                if isinstance(title_label, QLabel):
                    page._section_title_labels.append(title_label)
                row_layout.addWidget(widget, getattr(field_spec, "stretch", 1))
            outer.addLayout(row_layout)
            index += 1
            continue

        if kind == "text_panel":
            widget = _build_section_widget(page, page_spec, section)
            if widget is not None:
                if isinstance(widget, QFrame):
                    cards.append(widget)
                title_label = getattr(widget, "title_label", None)
                if isinstance(title_label, QLabel):
                    page._section_title_labels.append(title_label)
                outer.addWidget(widget, max(1, section.stretch or 1))
            index += 1
            continue

        if kind == "actions_row":
            row = QHBoxLayout()
            row.setSpacing(10)
            for action_spec in section.actions:
                button = QPushButton(action_spec.label)
                button.setEnabled(bool(action_spec.enabled))
                if action_spec.tooltip:
                    button.setToolTip(action_spec.tooltip)
                row.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)
                page.generated_actions[action_spec.action_id] = button
            row.addStretch(1)
            outer.addLayout(row)
            index += 1
            continue

        next_kind = ""
        if index + 1 < len(sections):
            next_kind = str(sections[index + 1].kind).strip().lower()
        if (kind, next_kind) in {
            ("file_list", "preview_pane"),
            ("file_list", "table_details_pane"),
            ("table_pane", "details_pane"),
        }:
            next_section = sections[index + 1]
            splitter = QSplitter(Qt.Orientation.Horizontal)
            first_widget = _build_section_widget(page, page_spec, section)
            second_widget = _build_section_widget(page, page_spec, next_section)
            if first_widget is not None:
                splitter.addWidget(first_widget)
            if second_widget is not None:
                splitter.addWidget(second_widget)
            splitter.setStretchFactor(0, max(1, section.stretch or 1))
            splitter.setStretchFactor(1, max(1, next_section.stretch or 1))
            outer.addWidget(splitter, max(1, max(section.stretch or 1, next_section.stretch or 1)))
            page.generated_widgets[f"{section.section_id}.splitter"] = splitter
            index += 2
            continue

        built_section_widget = _build_section_widget(page, page_spec, section)
        if built_section_widget is not None:
            outer.addWidget(built_section_widget, max(1, section.stretch or 1))
            index += 1
            continue

        if kind == "summary_output_pane":
            summary_card = QFrame()
            summary_layout = QVBoxLayout(summary_card)
            summary_layout.setContentsMargins(16, 14, 16, 14)
            summary_layout.setSpacing(10)
            result_summary_label = QLabel(section.description or page_spec.result_spec.summary_placeholder)
            result_summary_label.setWordWrap(True)
            summary_layout.addWidget(result_summary_label)
            output = QPlainTextEdit()
            output.setReadOnly(True)
            output.setPlaceholderText(page_spec.result_spec.output_placeholder)
            apply_semantic_class(output, section.semantic_class or "output_class")
            summary_layout.addWidget(output)
            outer.addWidget(summary_card, max(1, section.stretch or 1))
            cards.append(summary_card)
            page.generated_widgets[section.section_id] = summary_card
            page.generated_widgets[f"{section.section_id}.summary"] = result_summary_label
            page.generated_widgets[f"{section.section_id}.output"] = output
            index += 1
            continue

        if kind == "info_card":
            card = QFrame()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)
            title_label = None
            if section.title:
                title_label = QLabel(section.title)
                title_label.setWordWrap(True)
                layout.addWidget(title_label)
                page.generated_widgets[f"{section.section_id}.title"] = title_label
                page._section_title_labels.append(title_label)
            body_label = QLabel(section.description)
            body_label.setWordWrap(True)
            body_label.setOpenExternalLinks(True)
            layout.addWidget(body_label)
            page.generated_widgets[section.section_id] = card
            page.generated_widgets[f"{section.section_id}.body"] = body_label
            page._body_labels.append(body_label)
            outer.addWidget(card, max(1, section.stretch or 1))
            cards.append(card)
            index += 1
            continue

        if kind == "table_card":
            card = QFrame()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(10)
            if section.title:
                title_label = QLabel(section.title)
                title_label.setWordWrap(True)
                layout.addWidget(title_label)
                page.generated_widgets[f"{section.section_id}.title"] = title_label
                page._section_title_labels.append(title_label)
            field_spec = section.fields[0] if section.fields else None
            table_widget = _build_field_widget(field_spec) if field_spec is not None else QTableWidget(0, 0)
            if field_spec is not None:
                page.generated_widgets[field_spec.field_id] = table_widget
                page.generated_fields[field_spec.field_id] = field_spec
            layout.addWidget(table_widget, 1)
            page.generated_widgets[section.section_id] = card
            outer.addWidget(card, max(1, section.stretch or 1))
            cards.append(card)
            index += 1
            continue

        index += 1

    page._chrome_cards = cards
    page._summary_label = result_summary_label
    page.apply_sdk_chrome(services)
    return page


def _field_value(widget, field_spec) -> object:
    kind = str(field_spec.kind or "text").strip().lower()
    if kind == "multiline":
        return widget.toPlainText()
    if kind == "choice":
        return widget.currentData() if widget.currentData() is not None else widget.currentText()
    if kind == "toggle":
        return bool(widget.isChecked())
    if kind == "numeric":
        return widget.value()
    if kind == "path":
        return widget.text()
    if kind == "text_panel":
        return widget.toPlainText()
    if kind in {"preview", "file_list", "table", "donut", "info_card_field"}:
        return None
    return widget.text()


class SDKPageRuntime:
    def __init__(self, plugin, page: SDKPage, services, page_spec):
        self.plugin = plugin
        self.page = page
        self.services = services
        self.plugin_id = plugin.plugin_id
        self.tr = bind_tr(services, self.plugin_id)
        self.page_spec = page_spec
        self.state: dict[str, object] = {}
        self._preview_modes: dict[str, str] = {}
        self._field_widget_map: dict[str, object] = {}
        self._internal_flags: dict[str, object] = {}
        self._timers: dict[str, object] = {}
        self._task_specs = {task.task_id: task for task in (page_spec.task_specs or ())}
        self._file_behaviors = {behavior.widget_id: behavior for behavior in (page_spec.file_behaviors or ())}
        self._connect_theme_and_language()
        self._initialize_state()
        self._bind_fields()
        self._bind_file_behaviors()
        self._bind_action_handlers()
        self._bind_task_actions()
        self._apply_visibility_rules()
        self._apply_enable_rules()
        self._refresh_file_lists()
        self._run_initial_reactions()
        self._refresh_preview_bindings()
        self._start_timers()
        self._run_auto_actions()

    def _run_auto_actions(self) -> None:
        from PySide6.QtCore import QTimer
        for section in self.page_spec.sections:
            if hasattr(section, "actions"):
                for action_spec in section.actions:
                    if getattr(action_spec, "auto_run", False):
                        button = self.page.generated_actions.get(action_spec.action_id)
                        if button is not None:
                            QTimer.singleShot(50, button.click)

    def _start_timers(self) -> None:
        from PySide6.QtCore import QTimer
        for timer_spec in getattr(self.page_spec, "timer_tasks", ()) or ():
            timer = QTimer(self.page)
            timer.setInterval(max(50, timer_spec.interval_ms))
            timer.timeout.connect(lambda _spec=timer_spec: _spec.handler(self))
            timer.start()
            self._timers[timer_spec.timer_id] = timer

    def _connect_theme_and_language(self) -> None:
        language_changed = getattr(getattr(self.services, "i18n", None), "language_changed", None)
        if language_changed is not None:
            language_changed.connect(self._handle_language_change)
        theme_changed = getattr(getattr(self.services, "theme_manager", None), "theme_changed", None)
        if theme_changed is not None:
            theme_changed.connect(self._handle_theme_change)

    def _initialize_state(self) -> None:
        for state_spec in self.page_spec.state or ():
            default = state_spec.default
            if isinstance(default, list):
                default = list(default)
            elif isinstance(default, dict):
                default = dict(default)
            elif isinstance(default, set):
                default = set(default)
            self.state[state_spec.state_id] = default
        for field_id, field_spec in self.page.generated_fields.items():
            widget = self.page.generated_widgets.get(field_id)
            if widget is not None:
                self._field_widget_map[field_id] = widget
                value = _field_value(widget, field_spec)
                if value is not None or field_id not in self.state:
                    self.state[field_id] = value
        for behavior in self.page_spec.file_behaviors or ():
            self.state.setdefault(behavior.state_id, [])
            if behavior.selection_state_id:
                self.state.setdefault(behavior.selection_state_id, -1)

    def _bind_fields(self) -> None:
        for field_id, field_spec in self.page.generated_fields.items():
            widget = self.page.generated_widgets.get(field_id)
            if widget is None:
                continue
            kind = str(field_spec.kind or "text").strip().lower()
            if kind == "multiline":
                widget.textChanged.connect(lambda _field_id=field_id, _widget=widget: self._set_state(_field_id, _widget.toPlainText()))
                continue
            if kind == "choice":
                widget.currentIndexChanged.connect(lambda _index, _field_id=field_id, _widget=widget: self._set_state(_field_id, _widget.currentData() if _widget.currentData() is not None else _widget.currentText()))
                continue
            if kind == "toggle":
                widget.toggled.connect(lambda value, _field_id=field_id: self._set_state(_field_id, bool(value)))
                continue
            if kind == "numeric":
                widget.valueChanged.connect(lambda value, _field_id=field_id: self._set_state(_field_id, value))
                continue
            if kind == "path":
                widget.textChanged.connect(lambda value, _field_id=field_id: self._set_state(_field_id, value))
                continue
            if kind == "text_panel":
                editor = getattr(widget, "editor", None)
                if editor is not None:
                    editor.textChanged.connect(
                        lambda _field_id=field_id, _widget=widget: self._set_state(_field_id, _widget.toPlainText())
                    )
                continue
            if kind in {"preview", "file_list", "table", "donut", "info_card_field"}:
                continue
            widget.textChanged.connect(lambda value, _field_id=field_id: self._set_state(_field_id, value))

    def _bind_file_behaviors(self) -> None:
        for behavior in self.page_spec.file_behaviors or ():
            widget = self.page.generated_widgets.get(behavior.widget_id)
            if widget is None:
                continue
            if behavior.remove_action_text and hasattr(widget, "set_remove_action_text"):
                widget.set_remove_action_text(behavior.remove_action_text)
            widget.files_dropped.connect(lambda paths, _behavior=behavior: self._append_files(_behavior, list(paths or ())))
            widget.remove_requested.connect(lambda row, _behavior=behavior: self._remove_file_at(_behavior, int(row)))
            if behavior.selection_state_id:
                widget.currentRowChanged.connect(lambda row, _behavior=behavior: self._set_selection(_behavior, int(row)))
            if behavior.add_action_id:
                button = self.page.generated_actions.get(behavior.add_action_id)
                if button is not None:
                    button.clicked.connect(lambda _checked=False, _behavior=behavior: self._add_files_from_dialog(_behavior))
            if behavior.clear_action_id:
                button = self.page.generated_actions.get(behavior.clear_action_id)
                if button is not None:
                    button.clicked.connect(lambda _checked=False, _behavior=behavior: self._clear_files(_behavior))

    def _bind_task_actions(self) -> None:
        for binding in self.page_spec.task_bindings or ():
            button = self.page.generated_actions.get(binding.action_id)
            if button is not None:
                button.clicked.connect(lambda _checked=False, _binding=binding: self._run_task_binding(_binding))

    def _bind_action_handlers(self) -> None:
        for binding in self.page_spec.action_bindings or ():
            button = self.page.generated_actions.get(binding.action_id)
            if button is not None:
                button.clicked.connect(lambda _checked=False, _binding=binding: self._run_action_binding(_binding))

    def _handle_language_change(self, _language: str) -> None:
        self.page_spec = self.plugin.declare_page_spec(self.services)
        self.tr = bind_tr(self.services, self.plugin_id)
        self._task_specs = {task.task_id: task for task in (self.page_spec.task_specs or ())}
        self._file_behaviors = {behavior.widget_id: behavior for behavior in (self.page_spec.file_behaviors or ())}
        self._reapply_texts()
        self._run_initial_reactions()
        self._apply_visibility_rules()
        self._apply_enable_rules()
        self._refresh_file_lists()
        self._refresh_preview_bindings()
        apply_direction(self.page, self.services)
        self.page.apply_sdk_chrome(self.services)

    def _target_object(self, target_id: str):
        return self.page.generated_widgets.get(target_id) or self.page.generated_actions.get(target_id)

    def _handle_theme_change(self, _mode: str) -> None:
        self.page.apply_sdk_chrome(self.services)

    def _reapply_texts(self) -> None:
        self.page.generated_widgets["page.title"].setText(self.page_spec.title)
        self.page.generated_widgets["page.description"].setText(self.page_spec.description)

        for section in self.page_spec.sections:
            kind = str(section.kind or "").strip().lower()
            if kind == "settings_card":
                for field_spec in section.fields:
                    label_widget = self.page.generated_widgets.get(f"{field_spec.field_id}.label")
                    widget = self.page.generated_widgets.get(field_spec.field_id)
                    if label_widget is not None:
                        label_widget.setText(field_spec.label)
                    if widget is None:
                        continue
                    if field_spec.help_text:
                        widget.setToolTip(field_spec.help_text)
                    field_kind = str(field_spec.kind or "").strip().lower()
                    if field_kind == "choice":
                        current_value = widget.currentData() if widget.currentData() is not None else widget.currentText()
                        widget.blockSignals(True)
                        widget.clear()
                        for option in field_spec.options:
                            widget.addItem(option.label, option.value)
                        index = widget.findData(current_value)
                        if index < 0 and field_spec.default not in {None, ""}:
                            index = widget.findData(field_spec.default)
                        widget.setCurrentIndex(max(0, index))
                        widget.blockSignals(False)
                    elif field_kind == "multiline":
                        widget.setPlaceholderText(field_spec.placeholder)
                    elif field_kind == "text_panel":
                        if hasattr(widget, "set_title"):
                            widget.set_title(field_spec.label)
                        if hasattr(widget, "set_placeholder"):
                            widget.set_placeholder(field_spec.placeholder)
                    elif field_kind == "toggle":
                        widget.setText(field_spec.placeholder or field_spec.label)
                    elif field_kind == "path":
                        widget.setPlaceholderText(field_spec.placeholder)
                    elif field_kind == "preview" and widget.pixmap() is None:
                        widget.setText(field_spec.placeholder)
                    elif field_kind not in {"file_list", "table"}:
                        widget.setPlaceholderText(field_spec.placeholder)

            if kind == "row":
                for field_spec in section.fields:
                    widget = self.page.generated_widgets.get(field_spec.field_id)
                    if widget is None:
                        continue
                    field_kind = str(field_spec.kind or "").strip().lower()
                    if field_kind == "donut" and hasattr(widget, "set_title"):
                        widget.set_title(field_spec.label)
                    elif field_kind == "info_card_field" and hasattr(widget, "title_label"):
                        widget.title_label.setText(field_spec.label)
                    elif field_kind == "text_panel":
                        if hasattr(widget, "set_title"):
                            widget.set_title(field_spec.label)
                        if hasattr(widget, "set_placeholder"):
                            widget.set_placeholder(field_spec.placeholder)

            if kind == "actions_row":
                for action_spec in section.actions:
                    button = self.page.generated_actions.get(action_spec.action_id)
                    if button is None:
                        continue
                    button.setText(action_spec.label)
                    button.setEnabled(bool(action_spec.enabled))
                    button.setToolTip(action_spec.tooltip or "")

            if kind == "summary_output_pane":
                if self._summary_is_placeholder():
                    self.set_summary_placeholder(section.description or self.page_spec.result_spec.summary_placeholder)
                output = self.page.generated_widgets.get(f"{section.section_id}.output")
                if output is not None:
                    output.setPlaceholderText(self.page_spec.result_spec.output_placeholder)
            if kind == "info_card":
                title_label = self.page.generated_widgets.get(f"{section.section_id}.title")
                if title_label is not None:
                    title_label.setText(section.title)
                body_label = self.page.generated_widgets.get(f"{section.section_id}.body")
                if body_label is not None:
                    body_label.setText(section.description)
            if kind == "table_card":
                title_label = self.page.generated_widgets.get(f"{section.section_id}.title")
                if title_label is not None:
                    title_label.setText(section.title)
                field_spec = section.fields[0] if section.fields else None
                widget = self.page.generated_widgets.get(field_spec.field_id) if field_spec is not None else None
                if isinstance(widget, QTableWidget) and field_spec is not None:
                    _apply_table_widget_data(widget, field_spec)
            if kind == "text_panel":
                field_spec = section.fields[0] if section.fields else None
                widget = self.page.generated_widgets.get(field_spec.field_id) if field_spec is not None else None
                if widget is not None and field_spec is not None:
                    if hasattr(widget, "set_title"):
                        widget.set_title(field_spec.label)
                    if hasattr(widget, "set_placeholder"):
                        widget.set_placeholder(field_spec.placeholder)

        for behavior in self.page_spec.file_behaviors or ():
            widget = self.page.generated_widgets.get(behavior.widget_id)
            if widget is not None and behavior.remove_action_text and hasattr(widget, "set_remove_action_text"):
                widget.set_remove_action_text(behavior.remove_action_text)

        self.page.apply_sdk_chrome(self.services)

    def _summary_is_placeholder(self) -> bool:
        label = self.page.generated_widgets.get("result.summary")
        if label is None:
            return False
        text = label.text().strip()
        return text in {
            "",
            str(self.page_spec.result_spec.summary_placeholder or "").strip(),
            str(self.page.generated_sections.get("result").description if self.page.generated_sections.get("result") else "").strip(),
        }

    def _set_state(self, key: str, value: object) -> None:
        previous = self.state.get(key, object())
        self.state[key] = value
        self._apply_visibility_rules()
        self._apply_enable_rules()
        if previous != value:
            self._run_state_reactions(key)
        self._refresh_preview_bindings(key)

    def _set_selection(self, behavior, row: int) -> None:
        self.state[behavior.selection_state_id] = row
        self._run_state_reactions(behavior.selection_state_id)
        self._refresh_preview_bindings(behavior.selection_state_id)

    def _apply_visibility_rules(self) -> None:
        for rule in self.page_spec.visibility_rules or ():
            visible = bool(rule.predicate(self))
            for target_id in rule.target_ids:
                target = self._target_object(target_id)
                if target is not None:
                    target.setVisible(visible)

    def _apply_enable_rules(self) -> None:
        for rule in self.page_spec.enable_rules or ():
            enabled = bool(rule.predicate(self))
            for target_id in rule.target_ids:
                target = self._target_object(target_id)
                if target is not None:
                    target.setEnabled(enabled)

    def _run_state_reactions(self, changed_key: str) -> None:
        for reaction in self.page_spec.state_reactions or ():
            if reaction.depends_on and changed_key not in reaction.depends_on:
                continue
            reaction.handler(self, changed_key)

    def _run_initial_reactions(self) -> None:
        for reaction in self.page_spec.state_reactions or ():
            reaction.handler(self, "")

    def _refresh_file_lists(self) -> None:
        for behavior in self.page_spec.file_behaviors or ():
            widget = self.page.generated_widgets.get(behavior.widget_id)
            if widget is None:
                continue
            files = list(self.state.get(behavior.state_id, []) or [])
            current_row = int(self.state.get(behavior.selection_state_id, -1)) if behavior.selection_state_id else -1
            widget.blockSignals(True)
            widget.clear()
            names = [behavior.display_adapter(path) if callable(behavior.display_adapter) else os.path.basename(path) for path in files]
            if names:
                widget.addItems(names)
            widget.blockSignals(False)
            if behavior.selection_state_id:
                if not files:
                    current_row = -1
                elif current_row < 0:
                    current_row = 0
                else:
                    current_row = min(current_row, len(files) - 1)
                self.state[behavior.selection_state_id] = current_row
                if current_row >= 0:
                    widget.setCurrentRow(current_row)

    def _append_files(self, behavior, paths: list[str]) -> None:
        current = list(self.state.get(behavior.state_id, []) or [])
        field_spec = self.page.generated_fields.get(behavior.widget_id)
        allowed_extensions = tuple(str(ext).lower() for ext in getattr(field_spec, "allowed_extensions", ()) if str(ext).strip())
        for path in paths:
            if allowed_extensions and Path(path).suffix.lower() not in allowed_extensions:
                continue
            if behavior.allow_duplicates or path not in current:
                current.append(path)
        self.state[behavior.state_id] = current
        if behavior.selection_state_id and current and int(self.state.get(behavior.selection_state_id, -1)) < 0:
            self.state[behavior.selection_state_id] = 0
        self._refresh_file_lists()
        self._run_state_reactions(behavior.state_id)
        if behavior.selection_state_id and self.state.get(behavior.selection_state_id, -1) >= 0:
            self._run_state_reactions(behavior.selection_state_id)
        self._apply_visibility_rules()
        self._apply_enable_rules()
        self._refresh_preview_bindings(behavior.state_id)

    def _remove_file_at(self, behavior, row: int) -> None:
        current = list(self.state.get(behavior.state_id, []) or [])
        if row < 0 or row >= len(current):
            return
        del current[row]
        self.state[behavior.state_id] = current
        if behavior.selection_state_id:
            if not current:
                self.state[behavior.selection_state_id] = -1
            else:
                self.state[behavior.selection_state_id] = min(row, len(current) - 1)
        self._refresh_file_lists()
        self._run_state_reactions(behavior.state_id)
        if behavior.selection_state_id:
            self._run_state_reactions(behavior.selection_state_id)
        self._apply_visibility_rules()
        self._apply_enable_rules()
        self._refresh_preview_bindings(behavior.state_id)

    def _clear_files(self, behavior) -> None:
        self.state[behavior.state_id] = []
        if behavior.selection_state_id:
            self.state[behavior.selection_state_id] = -1
        self._refresh_file_lists()
        self._run_state_reactions(behavior.state_id)
        if behavior.selection_state_id:
            self._run_state_reactions(behavior.selection_state_id)
        self._apply_visibility_rules()
        self._apply_enable_rules()
        self._refresh_preview_bindings(behavior.state_id)

    def _add_files_from_dialog(self, behavior) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self.page,
            behavior.dialog_title or _pt(self.tr, "dialog.select_files", "Select Files"),
            str(self.services.default_output_path()),
            behavior.file_filter or "",
        )
        if files:
            self._append_files(behavior, list(files))

    def _refresh_preview_bindings(self, changed_key: str | None = None) -> None:
        for binding in self.page_spec.preview_bindings or ():
            dependencies = set(binding.dependencies or ())
            if changed_key is not None and dependencies and changed_key not in dependencies:
                continue
            self._refresh_preview(binding)

    def _refresh_preview(self, binding) -> None:
        widget = self.page.generated_widgets.get(binding.widget_id)
        if widget is None:
            return
        try:
            rendered = binding.builder(self)
        except Exception as exc:
            widget.clear()
            widget.setText(_pt(self.tr, "preview.error", "Preview error: {message}", message=str(exc)))
            self._preview_modes[binding.widget_id] = "error"
            return
        if isinstance(rendered, dict):
            pixmap = rendered.get("pixmap")
            text = str(rendered.get("text", "") or "")
        else:
            pixmap = rendered
            text = ""
        if pixmap is not None:
            widget.setPixmap(pixmap)
            widget.setText("")
            self._preview_modes[binding.widget_id] = "pixmap"
            return
        widget.clear()
        widget.setText(text or binding.empty_text or self.page_spec.result_spec.preview_placeholder)
        self._preview_modes[binding.widget_id] = "text"

    def _run_task_binding(self, binding) -> None:
        task_spec = self._task_specs.get(binding.task_id)
        if task_spec is None:
            raise KeyError(f"Unknown task id: {binding.task_id}")
        payload = binding.payload_builder(self)
        if payload is None:
            return
        disabled_action_ids = tuple(binding.disable_actions or ()) or (binding.action_id,)
        if callable(binding.before_run):
            binding.before_run(self)
        for action_id in disabled_action_ids:
            button = self.page.generated_actions.get(action_id)
            if button is not None:
                button.setEnabled(False)

        def _handle_result(result):
            if callable(binding.on_result):
                binding.on_result(self, result)
            else:
                self.set_summary(task_spec.success_text or _pt(self.tr, "summary.complete", "Task complete."))

        def _handle_error(payload):
            if callable(binding.on_error):
                binding.on_error(self, payload)
                return
            message = self._error_message(payload, fallback=task_spec.error_text or _pt(self.tr, "error.unknown", "Unknown task error"))
            import logging
            logging.getLogger("DNgine").error("Task execution failed", exc_info=payload if isinstance(payload, Exception) else None)
            
            self.set_summary(task_spec.error_text or _pt(self.tr, "summary.failed", "Task failed."))
            self.set_output(message)
            self.services.record_run(self.plugin_id, "ERROR", message[:500])

        def _handle_finished():
            for action_id in disabled_action_ids:
                button = self.page.generated_actions.get(action_id)
                if button is not None:
                    button.setEnabled(True)
            if callable(binding.on_finished):
                binding.on_finished(self)

        from dngine.sdk.tasks import run_task_spec

        run_task_spec(
            self.services,
            task_spec,
            payload,
            translate=self.tr,
            on_result=_handle_result,
            on_error=_handle_error,
            on_finished=_handle_finished,
        )

    def _run_action_binding(self, binding) -> None:
        try:
            binding.handler(self)
        except Exception as exc:
            self.warn(
                _pt(self.tr, "action.failed.title", "Action failed"),
                str(exc),
            )

    def _error_message(self, payload: object, *, fallback: str) -> str:
        if isinstance(payload, dict):
            return str(payload.get("message") or fallback)
        return str(payload or fallback)

    def value(self, key: str, default: object = None) -> object:
        return self.state.get(key, default)

    def snapshot(self) -> dict[str, object]:
        return dict(self.state)

    def set_value(self, key: str, value: object) -> None:
        self._set_state(key, value)

    def widget(self, key: str):
        return self.page.generated_widgets.get(key)

    def set_field_value(self, field_id: str, value: object, *, trigger: bool = True) -> None:
        widget = self.page.generated_widgets.get(field_id)
        field_spec = self.page.generated_fields.get(field_id)
        if widget is None or field_spec is None:
            return
        kind = str(field_spec.kind or "text").strip().lower()
        widget.blockSignals(True)
        try:
            if kind == "multiline":
                widget.setPlainText("" if value is None else str(value))
            elif kind == "text_panel":
                if hasattr(widget, "set_text"):
                    widget.set_text("" if value is None else str(value))
            elif kind == "choice":
                index = widget.findData(value)
                if index < 0:
                    index = widget.findText(str(value))
                if index >= 0:
                    widget.setCurrentIndex(index)
            elif kind == "toggle":
                widget.setChecked(bool(value))
            elif kind == "numeric":
                widget.setValue(value)
            elif kind == "path":
                widget.setText("" if value is None else str(value))
            elif kind == "donut":
                if isinstance(value, dict):
                    widget.set_metric(
                        value.get("percent", 0.0),
                        caption=value.get("caption", field_spec.default or ""),
                        accent=value.get("accent", field_spec.placeholder or ""),
                        remainder=value.get("remainder", field_spec.help_text or ""),
                    )
            elif kind == "info_card_field":
                if isinstance(value, list) or isinstance(value, tuple):
                    widget.set_rows(list(value))
            elif kind == "table":
                if isinstance(value, list) or isinstance(value, tuple):
                    from PySide6.QtCore import Qt
                    from PySide6.QtWidgets import QTableWidgetItem
                    rows = [[str(v) for v in r] for r in value]
                    widget.setRowCount(len(rows))
                    for row_index, row_values in enumerate(rows):
                        if widget.columnCount() < len(row_values):
                            widget.setColumnCount(len(row_values))
                        for column, v in enumerate(row_values):
                            item = QTableWidgetItem(str(v))
                            item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                            widget.setItem(row_index, column, item)
            elif kind not in {"preview", "file_list"}:
                widget.setText("" if value is None else str(value))
        finally:
            widget.blockSignals(False)
        if trigger:
            self._set_state(field_id, value)

    def set_flag(self, name: str, value: object) -> None:
        self._internal_flags[name] = value

    def flag(self, name: str, default: object = None) -> object:
        return self._internal_flags.get(name, default)

    def files(self, state_id: str) -> list[str]:
        return list(self.state.get(state_id, []) or [])

    def selected_file(self, behavior_widget_id: str) -> str | None:
        behavior = self._file_behaviors.get(behavior_widget_id)
        if behavior is None:
            return None
        files = self.files(behavior.state_id)
        row = int(self.state.get(behavior.selection_state_id, -1)) if behavior.selection_state_id else -1
        if row < 0 or row >= len(files):
            return None
        return files[row]

    def set_summary(self, text: str) -> None:
        label = self.page.generated_widgets.get("result.summary")
        if label is not None:
            label.setText(text)

    def set_summary_placeholder(self, text: str) -> None:
        self.set_summary(text)

    def clear_output(self) -> None:
        output = self.page.generated_widgets.get("result.output")
        if output is not None:
            output.clear()

    def set_output(self, text: str) -> None:
        output = self.page.generated_widgets.get("result.output")
        if output is not None:
            output.setPlainText(text)

    def set_placeholder(self, field_id: str, text: str) -> None:
        widget = self.page.generated_widgets.get(field_id)
        if widget is None:
            return
        if hasattr(widget, "setPlaceholderText"):
            widget.setPlaceholderText(text)

    def set_path_field_constraints(
        self,
        field_id: str,
        *,
        mode: str | None = None,
        allowed_extensions: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        widget = self.page.generated_widgets.get(field_id)
        if widget is None:
            return
        if mode is not None and hasattr(widget, "set_mode"):
            widget.set_mode(str(mode))
        if allowed_extensions is not None and hasattr(widget, "set_allowed_extensions"):
            widget.set_allowed_extensions(list(allowed_extensions))

    def set_details_text(self, field_id: str, text: str) -> None:
        widget = self.page.generated_widgets.get(field_id)
        if widget is not None and hasattr(widget, "setPlainText"):
            widget.setPlainText(text)

    def set_table_headers(self, field_id: str, headers: list[str]) -> None:
        widget = self.page.generated_widgets.get(field_id)
        if isinstance(widget, QTableWidget):
            widget.setColumnCount(len(headers))
            widget.setHorizontalHeaderLabels(list(headers))

    def set_table_rows(self, field_id: str, rows: list[list[str]]) -> None:
        widget = self.page.generated_widgets.get(field_id)
        if not isinstance(widget, QTableWidget):
            return
        widget.setRowCount(len(rows))
        for row_index, row_values in enumerate(rows):
            if widget.columnCount() < len(row_values):
                widget.setColumnCount(len(row_values))
            for column, value in enumerate(row_values):
                item = QTableWidgetItem(str(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                widget.setItem(row_index, column, item)

    def warn(self, title: str, message: str) -> None:
        QMessageBox.warning(self.page, title, message)

    def choose_directory(self, title: str) -> str:
        return QFileDialog.getExistingDirectory(self.page, title, str(self.services.default_output_path()))

    def choose_file(self, title: str, file_filter: str = "", *, start_path: str = "") -> str:
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self.page,
            title,
            start_path or str(self.services.default_output_path()),
            file_filter,
        )
        return str(file_path or "")

    def choose_save_file(self, title: str, suggested_path: str = "", file_filter: str = "") -> str:
        file_path, _selected_filter = QFileDialog.getSaveFileName(
            self.page,
            title,
            suggested_path or str(self.services.default_output_path()),
            file_filter,
        )
        return str(file_path or "")


def wire_page_runtime(plugin, page: SDKPage, services, page_spec):
    runtime = SDKPageRuntime(plugin, page, services, page_spec)
    page._sdk_runtime = runtime
    if page_spec.file_behaviors:
        def _add_file_paths(paths: list[str], widget_id: str | None = None):
            target = None
            if widget_id:
                target = next((behavior for behavior in page_spec.file_behaviors if behavior.widget_id == widget_id), None)
            else:
                target = page_spec.file_behaviors[0]
            if target is not None:
                runtime._append_files(target, list(paths or ()))

        page.add_file_paths = _add_file_paths
    return runtime
