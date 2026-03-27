from __future__ import annotations

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from micro_toolkit.core.page_style import card_style, muted_text_style, page_title_style
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


def cross_join_task(context, file_a: str, col_a: str, file_b: str, col_b: str, output_dir: str, *, translate=None):
    import pandas as pd

    context.log(_tr(translate, "log.load_a", "Loading dataset A..."))
    dataframe_a = pd.read_excel(file_a)
    context.log(_tr(translate, "log.load_b", "Loading dataset B..."))
    dataframe_b = pd.read_excel(file_b)
    context.progress(0.3)

    if col_a not in dataframe_a.columns or col_b not in dataframe_b.columns:
        raise ValueError(
            _tr(
                translate,
                "error.columns_missing",
                "Columns '{col_a}' or '{col_b}' were not found in the selected workbooks.",
                col_a=col_a,
                col_b=col_b,
            )
        )

    context.log(_tr(translate, "log.compute", "Computing matches and deltas..."))
    merged = pd.merge(dataframe_a, dataframe_b, left_on=col_a, right_on=col_b, how="inner")
    context.progress(0.55)
    delta_a = dataframe_a[~dataframe_a[col_a].isin(dataframe_b[col_b])]
    context.progress(0.75)
    delta_b = dataframe_b[~dataframe_b[col_b].isin(dataframe_a[col_a])]
    context.progress(0.9)

    os.makedirs(output_dir, exist_ok=True)
    outputs = []
    if not merged.empty:
        path = os.path.join(output_dir, "CrossMatched_Results.xlsx")
        merged.to_excel(path, index=False)
        outputs.append(("matches", path, len(merged)))
    if not delta_a.empty:
        path = os.path.join(output_dir, "DeltaMissing_In_B.xlsx")
        delta_a.to_excel(path, index=False)
        outputs.append(("only_a", path, len(delta_a)))
    if not delta_b.empty:
        path = os.path.join(output_dir, "DeltaMissing_In_A.xlsx")
        delta_b.to_excel(path, index=False)
        outputs.append(("only_b", path, len(delta_b)))

    if not outputs:
        raise ValueError(_tr(translate, "error.no_outputs", "No join outputs were generated."))

    context.progress(1.0)
    context.log(_tr(translate, "log.done", "Cross join complete with {count} output files.", count=len(outputs)))
    return {
        "outputs": outputs,
        "file_a": os.path.basename(file_a),
        "file_b": os.path.basename(file_b),
    }


class CrossJoinerPlugin(QtPlugin):
    plugin_id = "cross_joiner"
    name = "Data Cross Joiner"
    description = "Compare two Excel datasets, export matches and deltas, and open the generated result files."
    category = "Office Utilities"

    def create_widget(self, services) -> QWidget:
        return CrossJoinerPage(services, self.plugin_id)


class CrossJoinerPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self._result_buttons = []
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._apply_texts)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

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

        self.file_a_input, self.col_a_input, self.dataset_a_label, self.dataset_a_browse = self._add_dataset_row(layout)
        self.file_b_input, self.col_b_input, self.dataset_b_label, self.dataset_b_browse = self._add_dataset_row(layout)

        controls = QHBoxLayout()
        controls.setSpacing(12)
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)

        layout.addLayout(controls)

        self.summary_card = QFrame()
        summary_layout = QVBoxLayout(self.summary_card)
        summary_layout.setContentsMargins(16, 14, 16, 14)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        summary_layout.addWidget(self.summary_label)
        layout.addWidget(self.summary_card)

        self.results_host = QFrame()
        self.results_layout = QVBoxLayout(self.results_host)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
        layout.addWidget(self.results_host)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        layout.addWidget(self.output, 1)

    def _apply_texts(self) -> None:
        self.title_label.setText(self._pt("title", "Data Cross Joiner"))
        self.description_label.setText(
            self._pt(
                "description",
                "Load two workbooks, choose the match columns, and export joined rows plus dataset deltas.",
            )
        )
        self.dataset_a_label.setText(self._pt("dataset.a", "Dataset A"))
        self.dataset_b_label.setText(self._pt("dataset.b", "Dataset B"))
        self.file_a_input.setPlaceholderText(self._pt("placeholder.workbook", "Workbook..."))
        self.file_b_input.setPlaceholderText(self._pt("placeholder.workbook", "Workbook..."))
        self.dataset_a_browse.setText(self._pt("browse", "Browse"))
        self.dataset_b_browse.setText(self._pt("browse", "Browse"))
        self.col_a_input.setPlaceholderText(self._pt("placeholder.column", "Match column"))
        self.col_b_input.setPlaceholderText(self._pt("placeholder.column", "Match column"))
        self.run_button.setText(self._pt("run", "Run Cross Join"))
        self.summary_label.setText(self._pt("summary.ready", "Choose two workbooks and their match columns."))
        self.output.setPlaceholderText(self._pt("summary.placeholder", "Cross join summary will appear here."))
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        self.title_label.setStyleSheet(page_title_style(palette, size=26, weight=700))
        self.description_label.setStyleSheet(muted_text_style(palette))
        self.summary_card.setStyleSheet(card_style(palette, radius=14))
        self.summary_label.setStyleSheet(muted_text_style(palette, size=13))

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _add_dataset_row(self, parent_layout):
        row = QHBoxLayout()
        row.setSpacing(10)

        label = QLabel()
        label.setFixedWidth(90)
        row.addWidget(label)

        file_input = QLineEdit()
        row.addWidget(file_input, 1)

        browse_button = QPushButton()
        browse_button.clicked.connect(lambda: self._browse_file(file_input))
        row.addWidget(browse_button)

        col_input = QLineEdit()
        col_input.setFixedWidth(180)
        row.addWidget(col_input)

        parent_layout.addLayout(row)
        return file_input, col_input, label, browse_button

    def _browse_file(self, target_input: QLineEdit) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            self._pt("dialog.select_workbook", "Select Workbook"),
            str(self.services.default_output_path()),
            self._pt("dialog.excel_filter", "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"),
        )
        if file_path:
            target_input.setText(file_path)

    def _clear_result_buttons(self) -> None:
        while self.results_layout.count():
            item = self.results_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _run(self) -> None:
        file_a = self.file_a_input.text().strip()
        col_a = self.col_a_input.text().strip()
        file_b = self.file_b_input.text().strip()
        col_b = self.col_b_input.text().strip()
        if not all([file_a, col_a, file_b, col_b]):
            QMessageBox.warning(
                self,
                self._pt("error.missing_input.title", "Missing Input"),
                self._pt("error.missing_inputs", "Choose both workbooks and both match columns."),
            )
            return

        self.run_button.setEnabled(False)
        self.output.setPlainText("")
        self._clear_result_buttons()
        self.summary_label.setText(self._pt("summary.running", "Running cross join..."))

        self.services.run_task(
            lambda context: cross_join_task(
                context,
                file_a,
                col_a,
                file_b,
                col_b,
                str(self.services.default_output_path()),
                translate=self._pt,
            ),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        lines = [
            self._pt(
                "summary.compared",
                "Compared {file_a} against {file_b}.",
                file_a=result["file_a"],
                file_b=result["file_b"],
            )
        ]
        for label_key, path, row_count in result["outputs"]:
            label = self._pt(f"output.{label_key}", label_key)
            lines.append(self._pt("summary.output_line", "{label}: {row_count} rows -> {path}", label=label, row_count=row_count, path=path))
            button = QPushButton(self._pt("open_label", "Open {label}", label=label))
            button.clicked.connect(lambda _checked=False, file_path=path: QDesktopServices.openUrl(QUrl.fromLocalFile(file_path)))
            self.results_layout.addWidget(button, 0, Qt.AlignmentFlag.AlignLeft)

        self.output.setPlainText("\n".join(lines))
        self.summary_label.setText(self._pt("summary.generated", "Generated {count} result file(s).", count=len(result["outputs"])))
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self._pt("run.success", "Joined {file_a} and {file_b}", file_a=result["file_a"], file_b=result["file_b"]),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown cross join error")) if isinstance(payload, dict) else str(payload)
        self.output.setPlainText(message)
        self.summary_label.setText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.failed", "Cross join failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
