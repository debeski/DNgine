from __future__ import annotations

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.app_utils import generate_output_filename
from micro_toolkit.core.plugin_api import QtPlugin


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


def sanitize_data_task(
    context,
    file_path: str,
    trim: bool,
    drop_empty: bool,
    fill_nulls: bool,
    output_dir: str,
    *,
    translate=None,
):
    import pandas as pd

    context.log(_tr(translate, "log.reading", "Reading {path}...", path=file_path))
    dataframe = pd.read_excel(file_path)
    start_rows = len(dataframe)
    context.progress(0.2)

    if trim:
        dataframe = dataframe.apply(lambda column: column.str.strip() if column.dtype == "object" else column)
        context.log(_tr(translate, "log.trimmed", "Trimmed whitespace in string cells."))
    context.progress(0.45)

    if drop_empty:
        dataframe = dataframe.dropna(how="all")
        context.log(_tr(translate, "log.dropped", "Dropped fully empty rows."))
    context.progress(0.65)

    if fill_nulls:
        dataframe = dataframe.fillna("NULL_VALUE")
        context.log(_tr(translate, "log.filled", "Filled null cells with NULL_VALUE."))
    context.progress(0.8)

    source_name = os.path.splitext(os.path.basename(file_path))[0]
    output_name = generate_output_filename("Cleaned", source_name, ".xlsx")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_name)
    dataframe.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(_tr(translate, "log.saved", "Saved cleaned workbook to {path}", path=output_path))

    return {
        "output_path": output_path,
        "start_rows": start_rows,
        "end_rows": len(dataframe),
        "file_name": os.path.basename(file_path),
    }


class DataCleanerPlugin(QtPlugin):
    plugin_id = "cleaner"
    name = "Data Cleaner"
    description = "Trim strings, drop empty rows, fill nulls, and save a cleaned workbook to the configured output path."
    category = "Office Utilities"

    def create_widget(self, services) -> QWidget:
        return DataCleanerPage(services, self.plugin_id)


class DataCleanerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._latest_output_path = None
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)

    def _pt(self, key: str, default: str, **kwargs) -> str:
        return self.services.plugin_text(self.plugin_id, key, default, **kwargs)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 26px; font-weight: 700; color: #10232c;")
        layout.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        self.description_label.setStyleSheet("font-size: 14px; color: #43535c;")
        layout.addWidget(self.description_label)

        file_row = QHBoxLayout()
        file_row.setSpacing(10)
        self.file_input = QLineEdit()
        file_row.addWidget(self.file_input, 1)
        self.browse_button = QPushButton()
        self.browse_button.clicked.connect(self._browse_file)
        file_row.addWidget(self.browse_button)
        layout.addLayout(file_row)

        options_card = QFrame()
        options_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        options_layout = QVBoxLayout(options_card)
        options_layout.setContentsMargins(16, 14, 16, 14)
        options_layout.setSpacing(8)

        self.trim_checkbox = QCheckBox()
        self.trim_checkbox.setChecked(True)
        options_layout.addWidget(self.trim_checkbox)

        self.drop_checkbox = QCheckBox()
        self.drop_checkbox.setChecked(True)
        options_layout.addWidget(self.drop_checkbox)

        self.fill_checkbox = QCheckBox()
        self.fill_checkbox.setChecked(True)
        options_layout.addWidget(self.fill_checkbox)
        layout.addWidget(options_card)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.open_output_button = QPushButton()
        self.open_output_button.setEnabled(False)
        self.open_output_button.clicked.connect(self._open_output)
        controls.addWidget(self.open_output_button, 0, Qt.AlignmentFlag.AlignLeft)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        controls.addWidget(self.progress, 1)
        layout.addLayout(controls)

        summary_card = QFrame()
        summary_card.setStyleSheet(
            "QFrame { background: #fffdf9; border: 1px solid #eadfce; border-radius: 14px; }"
        )
        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setStyleSheet("font-size: 13px; color: #43535c;")
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(summary_card)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

    def _apply_texts(self) -> None:
        self.title_label.setText(self._pt("title", "Data Cleaner"))
        self.description_label.setText(
            self._pt(
                "description",
                "Clean an Excel workbook and write the resulting file to your configured output directory.",
            )
        )
        self.file_input.setPlaceholderText(self._pt("placeholder.file", "Select an Excel workbook..."))
        self.browse_button.setText(self._pt("browse", "Browse"))
        self.trim_checkbox.setText(self._pt("option.trim", "Trim surrounding whitespace"))
        self.drop_checkbox.setText(self._pt("option.drop", "Drop rows that are completely empty"))
        self.fill_checkbox.setText(self._pt("option.fill", "Fill remaining null cells with NULL_VALUE"))
        self.run_button.setText(self._pt("run", "Run Cleaner"))
        self.open_output_button.setText(self._pt("open_result", "Open Result"))
        self.summary_label.setText(self._pt("summary.ready", "Choose a workbook to begin cleaning."))
        self.output.setPlaceholderText(self._pt("summary.placeholder", "Run details will appear here."))

    def _browse_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("dialog.select_workbook", "Select Workbook"),
            str(self.services.default_output_path()),
            self._pt("dialog.excel_filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            self.file_input.setText(file_path)

    def _run(self) -> None:
        file_path = self.file_input.text().strip()
        if not file_path:
            QMessageBox.warning(
                self,
                self._pt("error.missing_input.title", "Missing Input"),
                self._pt("error.missing_file", "Choose a workbook to clean."),
            )
            return

        self.run_button.setEnabled(False)
        self.open_output_button.setEnabled(False)
        self.progress.setValue(0)
        self.output.setPlainText("")
        self.summary_label.setText(self._pt("summary.running", "Cleaning workbook..."))

        output_dir = str(self.services.default_output_path())
        self.services.run_task(
            lambda context: sanitize_data_task(
                context,
                file_path,
                self.trim_checkbox.isChecked(),
                self.drop_checkbox.isChecked(),
                self.fill_checkbox.isChecked(),
                output_dir,
                translate=self._pt,
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
            on_progress=self._handle_progress,
        )

    def _handle_progress(self, value: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, value)) * 100))

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        self._latest_output_path = result["output_path"]
        self.summary_label.setText(
            self._pt(
                "summary.done",
                "Cleaned {file_name} and reduced rows from {start_rows} to {end_rows}.",
                file_name=result["file_name"],
                start_rows=result["start_rows"],
                end_rows=result["end_rows"],
            )
        )
        self.output.setPlainText(self._pt("output.saved", "Saved cleaned workbook to:\n{path}", path=result["output_path"]))
        self.open_output_button.setEnabled(True)
        self.services.record_run(self.plugin_id, "SUCCESS", self._pt("run.success", "Cleaned {file_name}", file_name=result["file_name"]))

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown cleaner error")) if isinstance(payload, dict) else str(payload)
        self.summary_label.setText(message)
        self.output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.failed", "Data cleaner failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)

    def _open_output(self) -> None:
        if self._latest_output_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._latest_output_path))
