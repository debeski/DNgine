from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.media_utils import SUPPORTED_IMAGE_FILTER, apply_tag, pil_to_pixmap, safe_output_extension
from micro_toolkit.core.page_style import card_style, label_surface_style, muted_text_style, page_title_style
from micro_toolkit.core.plugin_api import QtPlugin
from micro_toolkit.core.widgets import ScrollSafeComboBox


QComboBox = ScrollSafeComboBox


def _tr(translate, key: str, default: str, **kwargs) -> str:
    if callable(translate):
        try:
            return translate(key, default, **kwargs)
        except Exception:
            pass
    text = default
    if kwargs:
        try:
            text = text.format(**kwargs)
        except Exception:
            pass
    return text


def run_image_tagger_task(
    context,
    files: list[str],
    output_dir: str,
    name: str,
    date_mode: str,
    custom_date: str,
    *,
    translate=None,
):
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        context.log(_tr(translate, "log.tagging", "Tagging {file}...", file=os.path.basename(file_path)))
        image = Image.open(file_path)
        tagged = apply_tag(image, name, date_mode, custom_date)
        output_ext = safe_output_extension(file_path, None)
        output_name = f"tagged_{Path(file_path).stem}{output_ext}"
        output_path = os.path.join(output_dir, output_name)
        save_format = output_ext.lstrip(".").upper()
        if save_format == "JPG":
            save_format = "JPEG"
        tagged.save(output_path, format=save_format)
        output_files.append(output_path)

    context.log(_tr(translate, "log.done", "Batch tagging complete. Wrote {count} files.", count=len(output_files)))
    return {
        "count": len(output_files),
        "output_dir": output_dir,
        "files": output_files,
    }


class ImageTaggerPlugin(QtPlugin):
    plugin_id = "tagger"
    name = "Image Tagger"
    description = "Batch-apply a smart glassmorphic date/name tag to images with live preview and cleaner controls."
    category = "Media Utilities"

    def create_widget(self, services) -> QWidget:
        return ImageTaggerPage(services, self.plugin_id)


class ImageTaggerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.files: list[str] = []
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size: 14px; color: #43535c;")
        outer.addWidget(self.description_label)

        self.form_card = QFrame()
        form = QFormLayout(self.form_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setSpacing(10)

        self.name_input = QLineEdit()
        self.name_label = QLabel()
        form.addRow(self.name_label, self.name_input)

        self.date_mode = QComboBox()
        self.date_mode.currentIndexChanged.connect(self._update_custom_date_visibility)
        self.date_mode.currentTextChanged.connect(self._update_custom_date_visibility)
        self.date_mode_label = QLabel()
        form.addRow(self.date_mode_label, self.date_mode)

        self.custom_date_input = QLineEdit()
        self.custom_date_label = QLabel()
        form.addRow(self.custom_date_label, self.custom_date_input)
        outer.addWidget(self.form_card)

        files_row = QHBoxLayout()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self._clear_files)
        files_row.addWidget(self.add_button)
        files_row.addWidget(self.clear_button)
        files_row.addStretch(1)
        outer.addLayout(files_row)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.file_list = QListWidget()
        self.file_list.currentRowChanged.connect(self._show_preview_for_row)
        left_layout.addWidget(self.file_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        right_layout.addWidget(self.preview_label, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        controls = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        outer.addLayout(controls)

        self.summary_output = QPlainTextEdit()
        self.summary_output.setReadOnly(True)
        outer.addWidget(self.summary_output, 1)

        self._update_custom_date_visibility()

    def _update_custom_date_visibility(self) -> None:
        is_custom = self._selected_date_mode() == "custom"
        self.custom_date_input.setVisible(is_custom)
        self.custom_date_label.setVisible(is_custom)

    def _selected_date_mode(self) -> str:
        return str(self.date_mode.currentData() or self.date_mode.currentText() or "taken")

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]]) -> None:
        current_value = str(combo.currentData() or combo.currentText() or "")
        combo.blockSignals(True)
        combo.clear()
        for value, label in items:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        if index < 0:
            index = 0
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    def _handle_language_change(self) -> None:
        self._apply_texts()
        self._refresh_file_list()
        if self.file_list.currentRow() >= 0:
            self._show_preview_for_row(self.file_list.currentRow())

    def _apply_texts(self) -> None:
        self.title_label.setText(self._pt("title", "Image Tagger"))
        self.description_label.setText(
            self._pt(
                "description",
                "Apply a clean bottom-right tag using EXIF date, today's date, or a custom date while previewing the selected image.",
            )
        )
        self.name_label.setText(self._pt("label.name", "Tag Name"))
        self.date_mode_label.setText(self._pt("label.date_source", "Date Source"))
        self.custom_date_label.setText(self._pt("label.custom_date", "Custom Date"))
        self.name_input.setPlaceholderText(self._pt("placeholder.name", "Name or signature"))
        self.custom_date_input.setPlaceholderText(self._pt("placeholder.date", "YYYY-MM-DD or any parseable date"))
        self._set_combo_items(
            self.date_mode,
            [
                ("taken", self._pt("date_mode.taken", "Taken date")),
                ("today", self._pt("date_mode.today", "Today's date")),
                ("custom", self._pt("date_mode.custom", "Custom date")),
            ],
        )
        self.add_button.setText(self._pt("add", "Add Images"))
        self.clear_button.setText(self._pt("clear", "Clear All"))
        self.run_button.setText(self._pt("run", "Run Tagger"))
        if not self.preview_label.pixmap():
            self.preview_label.setText(self._pt("preview.empty", "Select an image to preview."))
        self.summary_output.setPlaceholderText(self._pt("summary.placeholder", "Tagger summary will appear here."))
        self._update_custom_date_visibility()
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=700))
        self.description_label.setStyleSheet(muted_text_style(palette))
        self.form_card.setStyleSheet(card_style(palette, radius=14))
        self.preview_label.setStyleSheet(label_surface_style(palette, radius=14) + muted_text_style(palette))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self._pt("dialog.select_images", "Select Images"),
            str(self.services.default_output_path()),
            SUPPORTED_IMAGE_FILTER,
        )
        if not files:
            return
        for file_path in files:
            if file_path not in self.files:
                self.files.append(file_path)
        self._refresh_file_list()
        if self.files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def _clear_files(self) -> None:
        self.files = []
        self.file_list.clear()
        self.preview_label.setPixmap(None)
        self.preview_label.setText(self._pt("preview.empty", "Select an image to preview."))

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        for file_path in self.files:
            item = QListWidgetItem(os.path.basename(file_path))
            item.setToolTip(file_path)
            self.file_list.addItem(item)

    def _show_preview_for_row(self, row: int) -> None:
        if row < 0 or row >= len(self.files):
            return
        path = self.files[row]
        try:
            image = Image.open(path)
            preview_name = self.name_input.text().strip() or self._pt("preview.default_name", "PREVIEW")
            custom_date = self.custom_date_input.text().strip()
            tagged_preview = apply_tag(image, preview_name, self._selected_date_mode(), custom_date)
            self.preview_label.setPixmap(pil_to_pixmap(tagged_preview))
            self.preview_label.setText("")
        except Exception as exc:
            self.preview_label.setPixmap(None)
            self.preview_label.setText(self._pt("preview.error", "Preview error: {message}", message=exc))

    def _run(self) -> None:
        if not self.files:
            QMessageBox.warning(
                self,
                self._pt("error.missing_input.title", "Missing Input"),
                self._pt("error.missing_files", "Add at least one image first."),
            )
            return
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(
                self,
                self._pt("error.missing_input.title", "Missing Input"),
                self._pt("error.missing_name", "Enter a tag name first."),
            )
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            self._pt("dialog.select_output", "Select Output Folder"),
            str(self.services.default_output_path()),
        )
        if not output_dir:
            return

        date_mode = self._selected_date_mode()
        custom_date = self.custom_date_input.text().strip()

        self.run_button.setEnabled(False)
        self.summary_output.clear()
        self.services.run_task(
            lambda context: run_image_tagger_task(
                context,
                list(self.files),
                output_dir,
                name,
                date_mode,
                custom_date,
                translate=self._pt,
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self.summary_output.setPlainText(
            self._pt(
                "summary.done",
                "Batch tagging complete.\nFiles written: {count}\nOutput folder: {output_dir}",
                count=result["count"],
                output_dir=result["output_dir"],
            )
        )
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self._pt("run.success", "Tagged {count} images", count=result["count"]),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown image tagger error")) if isinstance(payload, dict) else str(payload)
        self.summary_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.failed", "Image tagger failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
