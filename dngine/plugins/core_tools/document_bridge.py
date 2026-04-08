from __future__ import annotations

from pathlib import Path

from dngine.sdk import (
    Action,
    Choice,
    CommandSpec,
    DeclarativePlugin,
    Output,
    Path as PathField,
    PayloadRequirement,
    Text,
    Toggle,
    _pt,
    before_task_run,
    bind_tr,
    build_runtime_payload,
    convert_docx_to_markdown,
    convert_markdown_to_docx,
    generate_output_filename,
    handle_task_error,
    handle_task_success,
    open_file_or_folder,
    set_runtime_values,
)


MARKDOWN_EXTENSIONS = (".md", ".markdown", ".txt")
DOCX_EXTENSIONS = (".docx",)
MARKDOWN_FILTER = "Markdown Files (*.md *.markdown *.txt);;All Files (*)"
DOCX_FILTER = "Word Documents (*.docx);;All Files (*)"
DOCX_SAVE_FILTER = "Word Documents (*.docx)"
MARKDOWN_SAVE_FILTER = "Markdown Files (*.md)"


def _resolve_output_path(
    source_path: str,
    *,
    output_path: str = "",
    output_dir: str = "",
    operation: str,
    extension: str,
) -> Path:
    if output_path:
        return Path(output_path).expanduser().resolve()

    source = Path(source_path).expanduser().resolve()
    base_dir = Path(output_dir).expanduser().resolve() if output_dir else source.parent
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = generate_output_filename(operation, source.stem, extension)
    return base_dir / filename


def markdown_to_docx_task(context, markdown_path: str, output_path: str, layout_mode: str, font_name: str):
    return convert_markdown_to_docx(
        markdown_path,
        output_path,
        layout_mode=layout_mode,
        font_name=font_name or "Amiri",
        log_cb=context.log,
        progress_cb=context.progress,
    )


def docx_to_markdown_task(context, docx_path: str, output_path: str, extract_images: bool):
    return convert_docx_to_markdown(
        docx_path,
        output_path,
        extract_images=extract_images,
        log_cb=context.log,
        progress_cb=context.progress,
    )


def _mode_value(runtime) -> str:
    return str(runtime.value("mode", "md_to_docx") or "md_to_docx")


def _is_md_mode(runtime) -> bool:
    return _mode_value(runtime) == "md_to_docx"


def _source_extensions_for_mode(mode: str) -> tuple[str, ...]:
    return MARKDOWN_EXTENSIONS if str(mode or "").strip() == "md_to_docx" else DOCX_EXTENSIONS


def _output_extensions_for_mode(mode: str) -> tuple[str, ...]:
    return DOCX_EXTENSIONS if str(mode or "").strip() == "md_to_docx" else (".md",)


def _source_filter(runtime) -> str:
    return MARKDOWN_FILTER if _is_md_mode(runtime) else DOCX_FILTER


def _output_filter(runtime) -> str:
    return DOCX_SAVE_FILTER if _is_md_mode(runtime) else MARKDOWN_SAVE_FILTER


def _suggest_output_path(runtime, source_path: str) -> str:
    source = Path(source_path).expanduser()
    if not source.name:
        return ""
    default_dir = runtime.services.default_output_path()
    if _is_md_mode(runtime):
        name = generate_output_filename("Markdown_To_DOCX", source.stem, ".docx")
    else:
        name = generate_output_filename("DOCX_To_Markdown", source.stem, ".md")
    return str(default_dir / name)


def _resolved_output_path(runtime) -> str:
    source_path = str(runtime.value("source_path", "") or "").strip()
    if not source_path:
        return ""
    output_path = str(runtime.value("output_path", "") or "").strip() or _suggest_output_path(runtime, source_path)
    if output_path and not str(runtime.value("output_path", "") or "").strip():
        runtime.set_field_value("output_path", output_path)
    return output_path


def _success_summary(runtime, result: dict[str, object]) -> str:
    if str(result.get("mode", _mode_value(runtime)) or _mode_value(runtime)) == "md_to_docx":
        return _pt(
            runtime.tr,
            "ui.summary.success.md_to_docx",
            "Created DOCX output with {headings} headings, {tables} tables, and {images} images.",
            headings=result.get("headings", 0),
            tables=result.get("tables", 0),
            images=result.get("images", 0),
        )
    return _pt(
        runtime.tr,
        "ui.summary.success.docx_to_md",
        "Created Markdown output with {headings} headings, {tables} tables, and {images} extracted images.",
        headings=result.get("headings", 0),
        tables=result.get("tables", 0),
        images=result.get("images", 0),
    )


def _result_to_output_text(result: dict[str, object]) -> str:
    return "\n".join(
        f"{key}: {value}"
        for key, value in result.items()
        if value not in ("", None, "md_to_docx", "docx_to_md")
    )


def _sync_mode_state(runtime, changed_key: str) -> None:
    mode = _mode_value(runtime)
    is_md_mode = mode == "md_to_docx"
    runtime.set_path_field_constraints("source_path", mode="file", allowed_extensions=_source_extensions_for_mode(mode))
    runtime.set_path_field_constraints("output_path", mode="file", allowed_extensions=_output_extensions_for_mode(mode))
    runtime.set_placeholder(
        "source_path",
        _pt(
            runtime.tr,
            "ui.source.placeholder.md_to_docx" if is_md_mode else "ui.source.placeholder.docx_to_md",
            "Choose a markdown file..." if is_md_mode else "Choose a DOCX file...",
        ),
    )
    runtime.set_placeholder(
        "output_path",
        _pt(
            runtime.tr,
            "ui.output.placeholder.md_to_docx" if is_md_mode else "ui.output.placeholder.docx_to_md",
            "Choose where the DOCX file should be saved..." if is_md_mode else "Choose where the markdown file should be saved...",
        ),
    )
    runtime.set_summary_placeholder(
        _pt(
            runtime.tr,
            "ui.summary.ready.md_to_docx" if is_md_mode else "ui.summary.ready.docx_to_md",
            "Choose a file to begin conversion.",
        )
    )
    if changed_key == "mode":
        runtime.set_value("latest_output_path", "")


def _run_document_bridge_task(
    context,
    *,
    mode: str,
    source_path: str,
    output_path: str,
    layout_mode: str,
    font_name: str,
    extract_images: bool,
):
    if str(mode or "").strip() == "md_to_docx":
        result = markdown_to_docx_task(context, source_path, output_path, layout_mode, font_name)
    else:
        result = docx_to_markdown_task(context, source_path, output_path, extract_images)
    payload = dict(result)
    payload["mode"] = str(mode or "").strip()
    return payload


def _build_payload(runtime) -> dict[str, object] | None:
    return build_runtime_payload(
        runtime,
        required=(
            PayloadRequirement(
                "source_path",
                lambda rt: str(rt.value("source_path", "") or "").strip(),
                _pt(runtime.tr, "ui.missing.source", "Choose a source file first."),
                title=_pt(runtime.tr, "ui.missing.title", "Missing Input"),
            ),
            PayloadRequirement(
                "output_path",
                _resolved_output_path,
                _pt(runtime.tr, "ui.missing.output", "Choose an output file path."),
                title=_pt(runtime.tr, "ui.missing.title", "Missing Input"),
            ),
        ),
        extras={
            "mode": _mode_value,
            "layout_mode": lambda rt: str(rt.value("layout_mode", "auto") or "auto"),
            "font_name": lambda rt: str(rt.value("font_name", "Amiri") or "").strip() or "Amiri",
            "extract_images": lambda rt: bool(rt.value("extract_images", True)),
        },
    )


def _browse_source(runtime) -> None:
    file_path = runtime.choose_file(
        _pt(
            runtime.tr,
            "ui.dialog.source.md_to_docx" if _is_md_mode(runtime) else "ui.dialog.source.docx_to_md",
            "Select Markdown File" if _is_md_mode(runtime) else "Select DOCX File",
        ),
        _source_filter(runtime),
        start_path=str(runtime.services.default_output_path()),
    )
    if not file_path:
        return
    runtime.set_field_value("source_path", file_path)
    runtime.set_field_value("output_path", _suggest_output_path(runtime, file_path), trigger=True)


def _browse_output(runtime) -> None:
    suggested = str(runtime.value("output_path", "") or "").strip() or _suggest_output_path(
        runtime,
        str(runtime.value("source_path", "") or "").strip(),
    )
    file_path = runtime.choose_save_file(
        _pt(
            runtime.tr,
            "ui.dialog.output.md_to_docx" if _is_md_mode(runtime) else "ui.dialog.output.docx_to_md",
            "Save DOCX File" if _is_md_mode(runtime) else "Save Markdown File",
        ),
        suggested,
        _output_filter(runtime),
    )
    if file_path:
        runtime.set_field_value("output_path", file_path)


def _open_output(runtime) -> None:
    output_path = str(runtime.value("latest_output_path", "") or "").strip()
    if output_path and open_file_or_folder(output_path):
        return
    runtime.warn(
        _pt(runtime.tr, "ui.open_failed.title", "Unable to open result"),
        _pt(runtime.tr, "ui.open_failed.body", "The converted file could not be opened from the saved location."),
    )


def _markdown_to_docx_command_worker(
    context,
    markdown_path: str,
    output_path: str = "",
    output_dir: str = "",
    layout_mode: str = "auto",
    font_name: str = "Amiri",
):
    resolved = _resolve_output_path(
        markdown_path,
        output_path=output_path,
        output_dir=output_dir,
        operation="Markdown_To_DOCX",
        extension=".docx",
    )
    return markdown_to_docx_task(context, markdown_path, str(resolved), layout_mode, font_name)


def _docx_to_markdown_command_worker(
    context,
    docx_path: str,
    output_path: str = "",
    output_dir: str = "",
    extract_images: bool = True,
):
    resolved = _resolve_output_path(
        docx_path,
        output_path=output_path,
        output_dir=output_dir,
        operation="DOCX_To_Markdown",
        extension=".md",
    )
    return docx_to_markdown_task(context, docx_path, str(resolved), bool(extract_images))


class DocumentBridgePlugin(DeclarativePlugin):
    plugin_id = "doc_bridge"
    name = "Document Bridge"
    description = "Convert Markdown reports into DOCX files and DOCX documents back into Markdown."
    category = "Office & Docs"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "mode": Choice(
                tr("ui.mode.label", "Mode"),
                options=(
                    ("md_to_docx", tr("ui.mode.md_to_docx", "Markdown -> DOCX")),
                    ("docx_to_md", tr("ui.mode.docx_to_md", "DOCX -> Markdown")),
                ),
                default="md_to_docx",
                on_change=_sync_mode_state,
            ),
            "source_path": PathField(
                tr("ui.source.label", "Source File"),
                placeholder=tr("ui.source.placeholder.md_to_docx", "Choose a markdown file..."),
                mode="file",
                allowed_extensions=MARKDOWN_EXTENSIONS,
            ),
            "output_path": PathField(
                tr("ui.output.label", "Output File"),
                placeholder=tr("ui.output.placeholder.md_to_docx", "Choose where the DOCX file should be saved..."),
                mode="file",
                allowed_extensions=DOCX_EXTENSIONS,
            ),
            "layout_mode": Choice(
                tr("ui.layout.label", "Layout Direction"),
                options=(
                    ("auto", tr("ui.layout.auto", "Auto Detect")),
                    ("ltr", tr("ui.layout.ltr", "Force LTR")),
                    ("rtl", tr("ui.layout.rtl", "Force RTL")),
                ),
                default="auto",
                visible_when={"mode": "md_to_docx"},
            ),
            "font_name": Text(
                tr("ui.font.label", "Preferred Font"),
                default="Amiri",
                visible_when={"mode": "md_to_docx"},
            ),
            "extract_images": Toggle(
                tr("ui.extract_images.label", "Extract Images"),
                default=True,
                help_text=tr("ui.extract_images", "Extract embedded images into a sibling media folder"),
                visible_when=lambda runtime: not _is_md_mode(runtime),
            ),
            "browse_source": Action(
                tr("ui.source.browse", "Browse"),
                kind="secondary",
                on_trigger=_browse_source,
            ),
            "browse_output": Action(
                tr("ui.output.browse", "Save As"),
                kind="secondary",
                on_trigger=_browse_output,
            ),
            "run": Action(
                tr("ui.run", "Convert"),
                worker=_run_document_bridge_task,
                payload_builder=_build_payload,
                before_run=lambda runtime: set_runtime_values(runtime, latest_output_path="") or before_task_run(
                    runtime,
                    _pt(runtime.tr, "ui.summary.running", "Converting document..."),
                ),
                on_result=lambda runtime, payload: set_runtime_values(
                    runtime,
                    latest_output_path=str(dict(payload).get("output_path", "") or ""),
                ) or handle_task_success(
                    runtime,
                    payload,
                    summary=lambda result: _success_summary(runtime, result),
                    output=_result_to_output_text,
                    run_detail=lambda result: str(result.get("output_path", "") or "")[:500],
                ),
                on_error=lambda runtime, payload: handle_task_error(
                    runtime,
                    payload,
                    summary=_pt(runtime.tr, "ui.summary.failed", "Document conversion failed."),
                    fallback=_pt(runtime.tr, "ui.error.unknown", "Unknown conversion error"),
                    log_message=_pt(runtime.tr, "ui.log.failed", "Document Bridge failed."),
                ),
                running_text=tr("ui.summary.running", "Converting document..."),
                success_text=tr("ui.summary.complete", "Conversion complete."),
                error_text=tr("ui.summary.failed", "Document conversion failed."),
                disable_actions=("run", "open_result"),
            ),
            "open_result": Action(
                tr("ui.open_result", "Open Result"),
                kind="secondary",
                on_trigger=_open_output,
                enabled_when=lambda runtime: bool(str(runtime.value("latest_output_path", "") or "").strip()),
            ),
            "result": Output(
                ready_text=tr("ui.summary.ready.md_to_docx", "Choose a markdown file and an output location to generate a DOCX document."),
                placeholder=tr("ui.log.placeholder", "Conversion details will appear here."),
            ),
        }

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        default_output_dir = str(services.default_output_path())
        return (
            CommandSpec(
                command_id="tool.doc_bridge.md_to_docx",
                title=tr("ui.mode.md_to_docx", "Markdown -> DOCX"),
                description=tr("plugin.description", "Convert Markdown reports into DOCX files and DOCX documents back into Markdown."),
                worker=_markdown_to_docx_command_worker,
                input_adapter=lambda payload, _default_dir=default_output_dir: {
                    "markdown_path": payload.get("markdown_path", ""),
                    "output_path": payload.get("output_path", ""),
                    "output_dir": payload.get("output_dir", "") or _default_dir,
                    "layout_mode": payload.get("layout_mode", "auto"),
                    "font_name": payload.get("font_name", "Amiri"),
                },
            ),
            CommandSpec(
                command_id="tool.doc_bridge.docx_to_md",
                title=tr("ui.mode.docx_to_md", "DOCX -> Markdown"),
                description=tr("plugin.description", "Convert Markdown reports into DOCX files and DOCX documents back into Markdown."),
                worker=_docx_to_markdown_command_worker,
                input_adapter=lambda payload, _default_dir=default_output_dir: {
                    "docx_path": payload.get("docx_path", ""),
                    "output_path": payload.get("output_path", ""),
                    "output_dir": payload.get("output_dir", "") or _default_dir,
                    "extract_images": payload.get("extract_images", True),
                },
            ),
        )
