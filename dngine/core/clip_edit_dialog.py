"""Edit & Transform dialog for clipboard entries.

Provides two modes:
1. **Edit mode** – user modifies content, saves over original or as new entry.
2. **Transform mode** – same dialog with a grouped transform combo for live preview.

All saved / created entries are marked with ``user_edited`` metadata.
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from dngine.core.clipboard_store import ClipboardStore
from dngine.core.clipboard_transforms import (
    CONTENT_TRANSFORMS,
    TEXT_FORMATTING_TRANSFORMS,
    apply_transform,
)
from dngine.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox

_SEPARATOR_VALUE = "__separator__"


class ClipEditDialog(QDialog):
    """Unified dialog for editing and transforming a clipboard entry."""

    def __init__(
        self,
        store: ClipboardStore,
        entry_id: int,
        services,
        plugin_id: str,
        *,
        transform_mode: bool = False,
        parent=None,
        pt=None,
    ):
        super().__init__(parent)
        self.store = store
        self.entry_id = entry_id
        self.services = services
        self.plugin_id = plugin_id
        self.transform_mode = transform_mode
        self.tr = pt or (lambda k, d, **kw: d.format(**kw) if kw else d)

        self._entry = self.store.get_entry(entry_id)
        self._original_content = self._entry.content if self._entry else ""
        self._original_html = self._entry.html_content if self._entry else ""
        self._did_act = False

        self.setWindowTitle(
            self.tr("dialog.transform.title", "Transform Text")
            if transform_mode
            else self.tr("dialog.edit.title", "Edit Clipboard Item")
        )
        self.resize(580, 460)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        if self.transform_mode:
            transform_row = QHBoxLayout()
            transform_row.setSpacing(8)
            self.transform_label = QLabel(self.tr("dialog.transform.label", "Transform:"))
            transform_row.addWidget(self.transform_label)
            self.transform_combo = QComboBox()
            self._populate_transform_combo()
            self.transform_combo.currentIndexChanged.connect(self._apply_selected_transform)
            transform_row.addWidget(self.transform_combo, 1)
            layout.addLayout(transform_row)

        self.editor = QPlainTextEdit()
        self.editor.setPlainText(self._original_content)
        self.editor.setPlaceholderText(self.tr("dialog.edit.placeholder", "Edit content here..."))
        layout.addWidget(self.editor, 1)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.save_copy_button = QPushButton(self.tr("dialog.edit.save_copy", "Save && Copy"))
        self.save_copy_button.setToolTip(
            self.tr("dialog.edit.save_copy.tip", "Save changes to this entry and copy to clipboard")
        )
        self.save_copy_button.clicked.connect(self._save_and_copy)
        button_row.addWidget(self.save_copy_button)

        self.save_new_button = QPushButton(self.tr("dialog.edit.save_new", "Save as New && Copy"))
        self.save_new_button.setToolTip(
            self.tr("dialog.edit.save_new.tip", "Create a new entry and copy to clipboard")
        )
        self.save_new_button.clicked.connect(self._save_as_new_and_copy)
        button_row.addWidget(self.save_new_button)

        self.copy_only_button = QPushButton(self.tr("dialog.edit.copy_only", "Copy Only"))
        self.copy_only_button.setToolTip(
            self.tr("dialog.edit.copy_only.tip", "Copy to clipboard without saving")
        )
        self.copy_only_button.clicked.connect(self._copy_only)
        button_row.addWidget(self.copy_only_button)

        button_row.addStretch(1)

        cancel_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        cancel_box.rejected.connect(self.reject)
        button_row.addWidget(cancel_box)

        layout.addLayout(button_row)

    def _populate_transform_combo(self) -> None:
        self.transform_combo.addItem(
            self.tr("dialog.transform.none", "— Select Transform —"), ""
        )

        # Content group header
        self.transform_combo.addItem(
            self.tr("dialog.transform.group.content", "── Content ──"),
            _SEPARATOR_VALUE,
        )
        idx = self.transform_combo.count() - 1
        model = self.transform_combo.model()
        item = model.item(idx)
        if item is not None:
            item.setEnabled(False)

        for value, tr_key, default in CONTENT_TRANSFORMS:
            self.transform_combo.addItem(self.tr(tr_key, default), value)

        # Formatting group header
        self.transform_combo.addItem(
            self.tr("dialog.transform.group.formatting", "── Formatting ──"),
            _SEPARATOR_VALUE,
        )
        idx = self.transform_combo.count() - 1
        item = model.item(idx)
        if item is not None:
            item.setEnabled(False)

        for value, tr_key, default in TEXT_FORMATTING_TRANSFORMS:
            self.transform_combo.addItem(self.tr(tr_key, default), value)

    # ------------------------------------------------------------------
    # Transform
    # ------------------------------------------------------------------

    def _apply_selected_transform(self) -> None:
        transform_id = self.transform_combo.currentData()
        if not transform_id or transform_id == _SEPARATOR_VALUE:
            return
        result = apply_transform(transform_id, self._original_content, self._original_html)
        self.editor.setPlainText(result.text)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _current_text(self) -> str:
        return self.editor.toPlainText()

    def _copy_to_clipboard(self, text: str) -> None:
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            self.services.clip_monitor_manager.ignore_next_change()
            clipboard.setText(text)

    def _save_and_copy(self) -> None:
        text = self._current_text()
        self.store.update_content(self.entry_id, text, user_edited=True)
        self._copy_to_clipboard(text)
        self.services.log(self.tr("log.edit_saved", "Clipboard entry updated and copied."))
        self._did_act = True
        self.accept()

    def _save_as_new_and_copy(self) -> None:
        text = self._current_text()
        metadata = {"user_edited": True}
        self.store.add_entry(text, metadata=metadata)
        self._copy_to_clipboard(text)
        self.services.log(self.tr("log.edit_new_saved", "New clipboard entry created and copied."))
        self._did_act = True
        self.accept()

    def _copy_only(self) -> None:
        text = self._current_text()
        self._copy_to_clipboard(text)
        self.services.log(self.tr("log.edit_copied", "Clipboard content copied."))
        self._did_act = True
        self.accept()

    @property
    def did_act(self) -> bool:
        return self._did_act
