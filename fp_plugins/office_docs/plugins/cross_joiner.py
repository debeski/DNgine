from __future__ import annotations

import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog

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


def cross_join_task(context, file_a: str, col_a: str, file_b: str, col_b: str, output_dir: str, *, translate=None):
    import pandas as pd

    context.log(safe_tr(translate, "log.load_a", "Loading dataset A..."))
    dataframe_a = pd.read_excel(file_a)
    context.log(safe_tr(translate, "log.load_b", "Loading dataset B..."))
    dataframe_b = pd.read_excel(file_b)
    context.progress(0.3)

    if col_a not in dataframe_a.columns or col_b not in dataframe_b.columns:
        raise ValueError(
            safe_tr(
                translate,
                "error.columns_missing",
                "Columns '{col_a}' or '{col_b}' were not found in the selected workbooks.",
                col_a=col_a,
                col_b=col_b,
            )
        )

    context.log(safe_tr(translate, "log.compute", "Computing matches and deltas..."))
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
        raise ValueError(safe_tr(translate, "error.no_outputs", "No join outputs were generated."))

    context.progress(1.0)
    context.log(safe_tr(translate, "log.done", "Cross join complete with {count} output files.", count=len(outputs)))
    return {
        "outputs": outputs,
        "file_a": os.path.basename(file_a),
        "file_b": os.path.basename(file_b),
    }


def _has_output(runtime, state_id: str) -> bool:
    return bool(str(runtime.value(state_id, "") or "").strip())


def _build_run_payload(runtime) -> dict[str, object] | None:
    file_a = str(runtime.value("file_a", "") or "").strip()
    col_a = str(runtime.value("col_a", "") or "").strip()
    file_b = str(runtime.value("file_b", "") or "").strip()
    col_b = str(runtime.value("col_b", "") or "").strip()
    if not all([file_a, col_a, file_b, col_b]):
        runtime.warn(
            _pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            _pt(runtime.tr, "error.missing_inputs", "Choose both workbooks and both match columns."),
        )
        return None
    return {
        "file_a": file_a,
        "col_a": col_a,
        "file_b": file_b,
        "col_b": col_b,
        "output_dir": str(runtime.services.default_output_path()),
    }


def _before_run(runtime) -> None:
    runtime.clear_output()
    runtime.set_value("matches_path", "")
    runtime.set_value("only_a_path", "")
    runtime.set_value("only_b_path", "")
    runtime.set_summary(_pt(runtime.tr, "summary.running", "Running cross join..."))


def _handle_result(runtime, payload: object) -> None:
    result = dict(payload)
    output_map = {str(label): str(path) for label, path, _row_count in result.get("outputs", [])}
    runtime.set_value("matches_path", output_map.get("matches", ""))
    runtime.set_value("only_a_path", output_map.get("only_a", ""))
    runtime.set_value("only_b_path", output_map.get("only_b", ""))

    lines = [
        _pt(
            runtime.tr,
            "summary.compared",
            "Compared {file_a} against {file_b}.",
            file_a=result.get("file_a", ""),
            file_b=result.get("file_b", ""),
        )
    ]
    for label_key, path, row_count in result.get("outputs", []):
        label = _pt(runtime.tr, f"output.{label_key}", label_key)
        lines.append(
            _pt(
                runtime.tr,
                "summary.output_line",
                "{label}: {row_count} rows -> {path}",
                label=label,
                row_count=row_count,
                path=path,
            )
        )

    runtime.set_output("\n".join(lines))
    runtime.set_summary(
        _pt(runtime.tr, "summary.generated", "Generated {count} result file(s).", count=len(result.get("outputs", [])))
    )
    runtime.services.record_run(
        runtime.plugin_id,
        "SUCCESS",
        _pt(
            runtime.tr,
            "run.success",
            "Joined {file_a} and {file_b}",
            file_a=result.get("file_a", ""),
            file_b=result.get("file_b", ""),
        ),
    )


def _handle_error(runtime, payload: object) -> None:
    if isinstance(payload, dict):
        message = str(payload.get("message") or _pt(runtime.tr, "error.unknown", "Unknown cross join error"))
    else:
        message = str(payload or _pt(runtime.tr, "error.unknown", "Unknown cross join error"))
    runtime.set_output(message)
    runtime.set_summary(message)
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])
    runtime.services.log(_pt(runtime.tr, "log.failed", "Cross join failed."), "ERROR")


def _browse_workbook(runtime, field_id: str) -> None:
    file_path, _ = QFileDialog.getOpenFileName(
        runtime.page,
        _pt(runtime.tr, "dialog.select_workbook", "Select Workbook"),
        str(runtime.services.default_output_path()),
        _pt(runtime.tr, "dialog.excel_filter", EXCEL_FILTER),
    )
    if file_path:
        runtime.set_field_value(field_id, file_path)


def _open_output(runtime, state_id: str) -> None:
    output_path = str(runtime.value(state_id, "") or "").strip()
    if output_path:
        QDesktopServices.openUrl(QUrl.fromLocalFile(output_path))


class CrossJoinerPlugin(StandardPlugin):
    plugin_id = "cross_joiner"
    name = "Data Cross Joiner"
    description = "Compare two Excel datasets, export matches and deltas, and open the generated result files."
    category = "Office & Docs"

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        return PageSpec(
            archetype="cross_joiner",
            title=tr("title", "Data Cross Joiner"),
            description=tr(
                "description",
                "Load two workbooks, choose the match columns, and export joined rows plus dataset deltas.",
            ),
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec("file_a", "path", tr("field.file_a", "Dataset A Workbook"), placeholder=tr("placeholder.workbook", "Workbook..."), allowed_extensions=EXCEL_EXTENSIONS),
                        FieldSpec("col_a", "text", tr("field.col_a", "Match Column A"), placeholder=tr("placeholder.column", "Match column")),
                        FieldSpec("file_b", "path", tr("field.file_b", "Dataset B Workbook"), placeholder=tr("placeholder.workbook", "Workbook..."), allowed_extensions=EXCEL_EXTENSIONS),
                        FieldSpec("col_b", "text", tr("field.col_b", "Match Column B"), placeholder=tr("placeholder.column", "Match column")),
                    ),
                ),
                SectionSpec(
                    section_id="actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("browse_a", tr("browse.a", "Browse A"), kind="secondary"),
                        ActionSpec("browse_b", tr("browse.b", "Browse B"), kind="secondary"),
                        ActionSpec("run", tr("run", "Run Cross Join")),
                        ActionSpec("open_matches", tr("open.matches", "Open Matches"), kind="secondary", enabled=False),
                        ActionSpec("open_only_a", tr("open.only_a", "Open Only In A"), kind="secondary", enabled=False),
                        ActionSpec("open_only_b", tr("open.only_b", "Open Only In B"), kind="secondary", enabled=False),
                    ),
                ),
                SectionSpec(
                    section_id="result",
                    kind="summary_output_pane",
                    description=tr("summary.ready", "Choose two workbooks and their match columns."),
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("summary.ready", "Choose two workbooks and their match columns."),
                output_placeholder=tr("summary.placeholder", "Cross join summary will appear here."),
            ),
            state=(
                StateSpec("matches_path", ""),
                StateSpec("only_a_path", ""),
                StateSpec("only_b_path", ""),
            ),
            task_specs=(
                TaskSpec(
                    task_id="run_cross_join",
                    worker=lambda context, file_a, col_a, file_b, col_b, output_dir: cross_join_task(
                        context,
                        file_a,
                        col_a,
                        file_b,
                        col_b,
                        output_dir,
                        translate=tr,
                    ),
                    running_text=tr("summary.running", "Running cross join..."),
                    success_text=tr("summary.generated", "Generated result files."),
                    error_text=tr("error.unknown", "Unknown cross join error"),
                ),
            ),
            enable_rules=(
                EnableRule(("open_matches",), predicate=lambda runtime: _has_output(runtime, "matches_path"), depends_on=("matches_path",)),
                EnableRule(("open_only_a",), predicate=lambda runtime: _has_output(runtime, "only_a_path"), depends_on=("only_a_path",)),
                EnableRule(("open_only_b",), predicate=lambda runtime: _has_output(runtime, "only_b_path"), depends_on=("only_b_path",)),
            ),
            task_bindings=(
                TaskBindingSpec(
                    action_id="run",
                    task_id="run_cross_join",
                    payload_builder=_build_run_payload,
                    before_run=_before_run,
                    on_result=_handle_result,
                    on_error=_handle_error,
                    disable_actions=("run", "open_matches", "open_only_a", "open_only_b"),
                ),
            ),
        )

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        default_output_dir = str(services.default_output_path())
        return (
            CommandSpec(
                command_id="tool.cross_joiner.run",
                title=tr("command.run.title", "Run Cross Join"),
                description=tr("command.run.description", "Compare two workbooks and export matches and deltas."),
                worker=lambda context, file_a, col_a, file_b, col_b, output_dir=default_output_dir: cross_join_task(
                    context,
                    file_a,
                    col_a,
                    file_b,
                    col_b,
                    output_dir,
                    translate=tr,
                ),
                input_adapter=lambda payload, _default_dir=default_output_dir: {
                    "file_a": payload.get("file_a", ""),
                    "col_a": payload.get("col_a", ""),
                    "file_b": payload.get("file_b", ""),
                    "col_b": payload.get("col_b", ""),
                    "output_dir": payload.get("output_dir", "") or _default_dir,
                },
            ),
        )

    def configure_page(self, page, services) -> None:
        super().configure_page(page, services)
        runtime = getattr(page, "_sdk_runtime", None)
        if runtime is None:
            return
        browse_a = page.generated_actions.get("browse_a")
        if browse_a is not None:
            browse_a.clicked.connect(lambda _checked=False: _browse_workbook(runtime, "file_a"))
        browse_b = page.generated_actions.get("browse_b")
        if browse_b is not None:
            browse_b.clicked.connect(lambda _checked=False: _browse_workbook(runtime, "file_b"))
        open_matches = page.generated_actions.get("open_matches")
        if open_matches is not None:
            open_matches.clicked.connect(lambda _checked=False: _open_output(runtime, "matches_path"))
        open_only_a = page.generated_actions.get("open_only_a")
        if open_only_a is not None:
            open_only_a.clicked.connect(lambda _checked=False: _open_output(runtime, "only_a_path"))
        open_only_b = page.generated_actions.get("open_only_b")
        if open_only_b is not None:
            open_only_b.clicked.connect(lambda _checked=False: _open_output(runtime, "only_b_path"))
