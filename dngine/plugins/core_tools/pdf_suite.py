from __future__ import annotations

import os



from dngine.sdk import (
    Action,
    CommandSpec,
    DeclarativePlugin,
    FileList,
    Output,
    Path,
    PayloadRequirement,
    _pt,
    before_task_run,
    bind_tr,
    build_runtime_payload,
    handle_task_error,
    handle_task_success,
    open_file_or_folder,
    set_runtime_values,
)


PDF_EXTENSIONS = (".pdf",)
PDF_FILTER = "PDF Documents (*.pdf)"


def merge_pdfs_task(context, file_paths: list[str], output_dir: str, *, translate=None):
    try:
        import PyPDF2
    except ImportError as exc:
        raise RuntimeError(_pt(translate, "error.pypdf2", "PyPDF2 is required to merge PDFs.")) from exc

    merger = PyPDF2.PdfMerger()
    total = len(file_paths)
    for index, file_path in enumerate(file_paths, start=1):
        context.progress(index / float(total))
        merger.append(file_path)
        context.log(_pt(translate, "log.added", "Added {file}", file=os.path.basename(file_path)))

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, "Merged_Document_Output.pdf")
    merger.write(output_path)
    merger.close()
    context.progress(1.0)
    context.log(_pt(translate, "log.saved", "Merged PDF written to {path}", path=output_path))
    return {
        "output_path": output_path,
        "file_count": len(file_paths),
    }


def _build_payload(runtime) -> dict[str, object] | None:
    output_dir = str(runtime.value("output_dir", "") or "").strip()
    if not output_dir:
        output_dir = str(runtime.services.default_output_path())
        runtime.set_field_value("output_dir", output_dir)

    return build_runtime_payload(
        runtime,
        required=(
            PayloadRequirement(
                "file_paths",
                lambda rt: rt.files("files"),
                _pt(runtime.tr, "error.missing_files", "Add at least one PDF file."),
                title=_pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            ),
        ),
        extras={
            "output_dir": output_dir,
            "translate": lambda rt: rt.tr,
        },
    )


class PDFSuitePlugin(DeclarativePlugin):
    plugin_id = "pdf_suite"
    name = "PDF Core Engine"
    description = "Merge multiple PDF files into one output document."
    category = "Office & Docs"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "files": FileList(
                extensions=PDF_EXTENSIONS,
                add_label=tr("add", "Add PDFs"),
                clear_label=tr("clear", "Clear List"),
                dialog_title=tr("dialog.select_pdfs", "Select PDF Files"),
                file_filter=PDF_FILTER,
            ),
            "output_dir": Path(
                tr("output_folder", "Output Folder"),
                default=str(services.default_output_path()),
                placeholder=tr("output_folder.placeholder", "Choose an output folder..."),
                mode="directory",
            ),
            "run": Action(
                tr("run", "Merge PDFs"),
                worker=merge_pdfs_task,
                payload_builder=_build_payload,
                before_run=lambda runtime: set_runtime_values(runtime, latest_output_path="") or before_task_run(
                    runtime,
                    _pt(runtime.tr, "summary.running", "Merging PDFs..."),
                ),
                on_result=lambda runtime, payload: set_runtime_values(
                    runtime,
                    latest_output_path=str(dict(payload).get("output_path", "") or ""),
                ) or handle_task_success(
                    runtime,
                    payload,
                    summary=_pt(runtime.tr, "summary.complete", "PDF merge complete."),
                    output=lambda merged: _pt(
                        runtime.tr,
                        "output.done",
                        "PDF merge complete.\nFiles merged: {file_count}\nOutput: {path}",
                        file_count=merged.get("file_count", 0),
                        path=merged.get("output_path", ""),
                    ),
                    run_detail=lambda merged: _pt(
                        runtime.tr,
                        "run.success",
                        "Merged {count} PDFs",
                        count=merged.get("file_count", 0),
                    ),
                ),
                on_error=lambda runtime, payload: handle_task_error(
                    runtime,
                    payload,
                    summary=_pt(runtime.tr, "summary.failed", "PDF suite failed."),
                    fallback=_pt(runtime.tr, "error.unknown", "Unknown PDF suite error"),
                    log_message=_pt(runtime.tr, "log.failed", "PDF suite failed."),
                ),
                running_text=tr("summary.running", "Merging PDFs..."),
                success_text=tr("summary.complete", "PDF merge complete."),
                error_text=tr("summary.failed", "PDF suite failed."),
                enabled_when=lambda runtime: bool(runtime.files("files")),
            ),
            "open_output": Action(
                tr("open_output", "Open Output"),
                kind="secondary",
                on_trigger=lambda runtime: open_file_or_folder(
                    str(runtime.value("latest_output_path", "") or "").strip()
                ),
                enabled_when=lambda runtime: bool(str(runtime.value("latest_output_path", "") or "").strip()),
            ),
            "result": Output(
                ready_text=tr("summary.ready", "Add PDF files to begin."),
                placeholder=tr("summary.placeholder", "PDF merge summary will appear here."),
            ),
        }

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        return (
            CommandSpec(
                command_id="tool.pdf_suite.merge",
                title=tr("run", "Merge PDFs"),
                description=tr("plugin.description", "Merge multiple PDF files into one output document."),
                worker=lambda context, file_paths, output_dir: merge_pdfs_task(
                    context,
                    file_paths,
                    output_dir,
                    translate=tr,
                ),
                input_adapter=lambda payload, svc=services: {
                    "file_paths": list(payload.get("file_paths", [])),
                    "output_dir": str(payload.get("output_dir") or svc.default_output_path()),
                },
            ),
        )
