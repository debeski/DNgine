from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

from dngine.core.app_utils import generate_output_filename
from dngine.sdk import (
    ActionSpec,
    CommandSpec,
    EnableRule,
    FieldSpec,
    PageSpec,
    ResultSpec,
    SectionSpec,
    StandardPlugin,
    StateSpec,
    TaskBindingSpec,
    TaskSpec,
    _pt,
    bind_tr,
    safe_tr,
)


EXCEL_EXTENSIONS = (".xlsx", ".xlsm", ".xls")
EXCEL_FILTER = "Excel Files (*.xlsx *.xlsm *.xls);;All Files (*)"


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

    context.log(safe_tr(translate, "log.reading", "Reading {path}...", path=file_path))
    dataframe = pd.read_excel(file_path)
    start_rows = len(dataframe)
    context.progress(0.2)

    if trim:
        dataframe = dataframe.apply(lambda column: column.str.strip() if column.dtype == "object" else column)
        context.log(safe_tr(translate, "log.trimmed", "Trimmed whitespace in string cells."))
    context.progress(0.45)

    if drop_empty:
        dataframe = dataframe.dropna(how="all")
        context.log(safe_tr(translate, "log.dropped", "Dropped fully empty rows."))
    context.progress(0.65)

    if fill_nulls:
        dataframe = dataframe.fillna("NULL_VALUE")
        context.log(safe_tr(translate, "log.filled", "Filled null cells with NULL_VALUE."))
    context.progress(0.8)

    source_name = os.path.splitext(os.path.basename(file_path))[0]
    output_name = generate_output_filename("Cleaned", source_name, ".xlsx")
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, output_name)
    dataframe.to_excel(output_path, index=False)
    context.progress(1.0)
    context.log(safe_tr(translate, "log.saved", "Saved cleaned workbook to {path}", path=output_path))

    return {
        "output_path": output_path,
        "start_rows": start_rows,
        "end_rows": len(dataframe),
        "file_name": os.path.basename(file_path),
    }


def _build_run_payload(runtime) -> dict[str, object] | None:
    file_path = str(runtime.value("file_path", "") or "").strip()
    if not file_path:
        runtime.warn(
            _pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            _pt(runtime.tr, "error.missing_file", "Choose a workbook to clean."),
        )
        return None
    return {
        "file_path": file_path,
        "trim": bool(runtime.value("trim", True)),
        "drop_empty": bool(runtime.value("drop_empty", True)),
        "fill_nulls": bool(runtime.value("fill_nulls", True)),
        "output_dir": str(runtime.services.default_output_path()),
    }


def _before_run(runtime) -> None:
    runtime.clear_output()
    runtime.set_value("latest_output_path", "")
    runtime.set_summary(_pt(runtime.tr, "summary.running", "Cleaning workbook..."))


def _handle_result(runtime, payload: object) -> None:
    result = dict(payload)
    output_path = str(result.get("output_path", "") or "")
    runtime.set_value("latest_output_path", output_path)
    runtime.set_summary(
        _pt(
            runtime.tr,
            "summary.done",
            "Cleaned {file_name} and reduced rows from {start_rows} to {end_rows}.",
            file_name=result.get("file_name", ""),
            start_rows=result.get("start_rows", 0),
            end_rows=result.get("end_rows", 0),
        )
    )
    runtime.set_output(
        _pt(
            runtime.tr,
            "output.saved",
            "Saved cleaned workbook to:\n{path}",
            path=output_path,
        )
    )
    runtime.services.record_run(
        runtime.plugin_id,
        "SUCCESS",
        _pt(runtime.tr, "run.success", "Cleaned {file_name}", file_name=result.get("file_name", "")),
    )


def _handle_error(runtime, payload: object) -> None:
    if isinstance(payload, dict):
        message = str(payload.get("message") or _pt(runtime.tr, "error.unknown", "Unknown cleaner error"))
    else:
        message = str(payload or _pt(runtime.tr, "error.unknown", "Unknown cleaner error"))
    runtime.set_summary(message)
    runtime.set_output(message)
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])
    runtime.services.log(_pt(runtime.tr, "log.failed", "Data cleaner failed."), "ERROR")


def _browse_file(runtime) -> None:
    file_path, _ = QFileDialog.getOpenFileName(
        runtime.page,
        _pt(runtime.tr, "dialog.select_workbook", "Select Workbook"),
        str(runtime.services.default_output_path()),
        _pt(runtime.tr, "dialog.excel_filter", EXCEL_FILTER),
    )
    if file_path:
        runtime.set_field_value("file_path", file_path)


def _open_output(runtime) -> None:
    output_path = str(runtime.value("latest_output_path", "") or "").strip()
    if output_path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))


class DataCleanerPlugin(StandardPlugin):
    plugin_id = "cleaner"
    name = "Data Cleaner"
    description = "Trim strings, drop empty rows, fill nulls, and save a cleaned workbook to the configured output path."
    category = "Office & Docs"

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        return PageSpec(
            archetype="data_cleaner",
            title=tr("title", "Data Cleaner"),
            description=tr(
                "description",
                "Clean an Excel workbook and write the resulting file to your configured output directory.",
            ),
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec(
                            "file_path",
                            "path",
                            tr("field.file", "Workbook"),
                            placeholder=tr("placeholder.file", "Select an Excel workbook..."),
                            allowed_extensions=EXCEL_EXTENSIONS,
                        ),
                        FieldSpec("trim", "toggle", tr("option.trim", "Trim surrounding whitespace"), default=True, placeholder=tr("option.trim", "Trim surrounding whitespace")),
                        FieldSpec("drop_empty", "toggle", tr("option.drop", "Drop rows that are completely empty"), default=True, placeholder=tr("option.drop", "Drop rows that are completely empty")),
                        FieldSpec("fill_nulls", "toggle", tr("option.fill", "Fill remaining null cells with NULL_VALUE"), default=True, placeholder=tr("option.fill", "Fill remaining null cells with NULL_VALUE")),
                    ),
                ),
                SectionSpec(
                    section_id="actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("browse_file", tr("browse", "Browse"), kind="secondary"),
                        ActionSpec("run", tr("run", "Run Cleaner")),
                        ActionSpec("open_result", tr("open_result", "Open Result"), kind="secondary", enabled=False),
                    ),
                ),
                SectionSpec(
                    section_id="result",
                    kind="summary_output_pane",
                    description=tr("summary.ready", "Choose a workbook to begin cleaning."),
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("summary.ready", "Choose a workbook to begin cleaning."),
                output_placeholder=tr("summary.placeholder", "Run details will appear here."),
            ),
            state=(
                StateSpec("latest_output_path", ""),
            ),
            task_specs=(
                TaskSpec(
                    task_id="clean_data",
                    worker=lambda context, file_path, trim, drop_empty, fill_nulls, output_dir: sanitize_data_task(
                        context,
                        file_path,
                        trim,
                        drop_empty,
                        fill_nulls,
                        output_dir,
                        translate=tr,
                    ),
                    running_text=tr("summary.running", "Cleaning workbook..."),
                    success_text=tr("summary.done", "Workbook cleaning complete."),
                    error_text=tr("error.unknown", "Unknown cleaner error"),
                ),
            ),
            enable_rules=(
                EnableRule(("open_result",), predicate=lambda runtime: bool(str(runtime.value("latest_output_path", "") or "").strip()), depends_on=("latest_output_path",)),
            ),
            task_bindings=(
                TaskBindingSpec(
                    action_id="run",
                    task_id="clean_data",
                    payload_builder=_build_run_payload,
                    before_run=_before_run,
                    on_result=_handle_result,
                    on_error=_handle_error,
                    disable_actions=("run", "open_result"),
                ),
            ),
        )

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        default_output_dir = str(services.default_output_path())
        return (
            CommandSpec(
                command_id="tool.cleaner.run",
                title=tr("command.run.title", "Run Data Cleaner"),
                description=tr("command.run.description", "Clean an Excel workbook and write a new output file."),
                worker=lambda context, file_path, trim=True, drop_empty=True, fill_nulls=True, output_dir=default_output_dir: sanitize_data_task(
                    context,
                    file_path,
                    bool(trim),
                    bool(drop_empty),
                    bool(fill_nulls),
                    output_dir,
                    translate=tr,
                ),
                input_adapter=lambda payload, _default_dir=default_output_dir: {
                    "file_path": payload.get("file_path", ""),
                    "trim": bool(payload.get("trim", True)),
                    "drop_empty": bool(payload.get("drop_empty", True)),
                    "fill_nulls": bool(payload.get("fill_nulls", True)),
                    "output_dir": payload.get("output_dir", "") or _default_dir,
                },
            ),
        )

    def configure_page(self, page, services) -> None:
        super().configure_page(page, services)
        runtime = getattr(page, "_sdk_runtime", None)
        if runtime is None:
            return
        browse_button = page.generated_actions.get("browse_file")
        if browse_button is not None:
            browse_button.clicked.connect(lambda _checked=False: _browse_file(runtime))
        open_output = page.generated_actions.get("open_result")
        if open_output is not None:
            open_output.clicked.connect(lambda _checked=False: _open_output(runtime))
