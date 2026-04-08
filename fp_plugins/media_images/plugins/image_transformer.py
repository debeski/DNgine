from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from dngine.sdk import (
    ActionSpec,
    ChoiceOption,
    CommandSpec,
    EnableRule,
    FieldSpec,
    FileListBehaviorSpec,
    PageSpec,
    PreviewBindingSpec,
    ResultSpec,
    SectionSpec,
    StandardPlugin,
    StateReactionSpec,
    StateSpec,
    SUPPORTED_IMAGE_FILTER,
    TaskBindingSpec,
    TaskSpec,
    _pt,
    bind_tr,
    pil_to_pixmap,
    safe_output_extension,
    transform_image,
)


SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".heic")


def run_image_transform_task(context, files: list[str], output_dir: str, options: dict, *, translate=None):
    os.makedirs(output_dir, exist_ok=True)
    transformed_files: list[str] = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        context.log(_pt(translate, "log.transforming", "Transforming {file}...", file=os.path.basename(file_path)))
        image = Image.open(file_path)
        transformed, requested_format = transform_image(
            image,
            rotate_value=options.get("rotate_value"),
            resize_enabled=options.get("resize_enabled", False),
            resize_type=options.get("resize_type", "pixels"),
            width_value=options.get("resize_width", ""),
            height_value=options.get("resize_height", ""),
            format_value=options.get("format_value"),
        )

        base_name = Path(file_path).stem
        output_ext = safe_output_extension(file_path, requested_format)
        output_name = f"trans_{base_name}{output_ext}"
        output_path = os.path.join(output_dir, output_name)

        save_format = output_ext.lstrip(".").upper()
        if save_format == "JPG":
            save_format = "JPEG"
        transformed.save(output_path, format=save_format)
        transformed_files.append(output_path)

    context.log(_pt(translate, "log.done", "Batch transform complete. Wrote {count} files.", count=len(transformed_files)))
    return {
        "count": len(transformed_files),
        "output_dir": output_dir,
        "files": transformed_files,
    }


def _rotate_value(runtime) -> str | None:
    if not runtime.value("rotate_enabled", False):
        return None
    return str(runtime.value("rotate_mode", "90°") or "90°")


def _resize_mode_value(runtime) -> str:
    return str(runtime.value("resize_mode", "pixels") or "pixels")


def _format_mode_value(runtime) -> str:
    return str(runtime.value("format_mode", "png") or "png")


def _transform_options(runtime) -> dict[str, object]:
    return {
        "rotate_value": _rotate_value(runtime),
        "resize_enabled": bool(runtime.value("resize_enabled", False)),
        "resize_type": _resize_mode_value(runtime),
        "resize_width": str(runtime.value("resize_width", "") or "").strip(),
        "resize_height": str(runtime.value("resize_height", "") or "").strip(),
        "format_value": _format_mode_value(runtime) if runtime.value("format_enabled", False) else None,
    }


def _selected_file(runtime) -> str | None:
    return runtime.selected_file("files")


def _compute_aspect_for_file(runtime) -> float | None:
    path = _selected_file(runtime)
    if not path:
        return None
    with Image.open(path) as image:
        transformed, _ = transform_image(
            image,
            rotate_value=_rotate_value(runtime),
            resize_enabled=False,
            resize_type="pixels",
            width_value="",
            height_value="",
            format_value=None,
        )
    return transformed.width / float(transformed.height) if transformed.height else None


def _numeric_text(value: object) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _sync_transform_state(runtime, changed_key: str) -> None:
    if runtime.flag("transform_sync_lock", False):
        return
    runtime.set_flag("transform_sync_lock", True)
    try:
        if changed_key in {"files", "selected_file_row", "rotate_enabled", "rotate_mode"}:
            runtime.set_value("current_aspect", _compute_aspect_for_file(runtime))

        current_aspect = runtime.value("current_aspect")
        if not runtime.value("resize_enabled", False) or not runtime.value("keep_aspect", False) or not current_aspect:
            return

        resize_mode = _resize_mode_value(runtime)
        width_text = str(runtime.value("resize_width", "") or "").strip()
        height_text = str(runtime.value("resize_height", "") or "").strip()

        if changed_key in {"files", "selected_file_row", "rotate_enabled", "rotate_mode", "resize_enabled", "keep_aspect", "resize_mode"}:
            if resize_mode == "pixels" and not width_text and not height_text:
                path = _selected_file(runtime)
                if path:
                    with Image.open(path) as image:
                        transformed, _ = transform_image(
                            image,
                            rotate_value=_rotate_value(runtime),
                            resize_enabled=False,
                            resize_type="pixels",
                            width_value="",
                            height_value="",
                            format_value=None,
                        )
                    runtime.set_field_value("resize_width", str(transformed.width))
                    runtime.set_field_value("resize_height", str(transformed.height))
            return

        if changed_key == "resize_width":
            width_number = _numeric_text(width_text)
            if width_number is None:
                return
            if resize_mode == "percent":
                runtime.set_field_value("resize_height", width_text)
            else:
                runtime.set_field_value("resize_height", str(int(width_number / float(current_aspect))))
            return

        if changed_key == "resize_height":
            height_number = _numeric_text(height_text)
            if height_number is None:
                return
            if resize_mode == "percent":
                runtime.set_field_value("resize_width", height_text)
            else:
                runtime.set_field_value("resize_width", str(int(height_number * float(current_aspect))))
    finally:
        runtime.set_flag("transform_sync_lock", False)


def build_image_transform_preview(runtime):
    path = _selected_file(runtime)
    if not path:
        return {"pixmap": None, "text": _pt(runtime.tr, "preview.empty", "Select an image to preview.")}
    with Image.open(path) as image:
        transformed, _ = transform_image(image, **_transform_options(runtime))
    return {"pixmap": pil_to_pixmap(transformed), "text": ""}


def _build_transform_payload(runtime):
    files = runtime.files("files")
    if not files:
        runtime.warn(
            _pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            _pt(runtime.tr, "error.missing_files", "Add at least one image first."),
        )
        return None
    output_dir = runtime.choose_directory(_pt(runtime.tr, "dialog.select_output", "Select Output Folder"))
    if not output_dir:
        return None
    return {
        "files": files,
        "output_dir": output_dir,
        "options": _transform_options(runtime),
        "translate": runtime.tr,
    }


def _before_transform_run(runtime) -> None:
    runtime.clear_output()
    runtime.set_summary(_pt(runtime.tr, "summary.running", "Running image transform..."))


def _handle_transform_result(runtime, payload: object) -> None:
    result = dict(payload)
    runtime.set_summary(_pt(runtime.tr, "summary.complete", "Image transform complete."))
    runtime.set_output(
        _pt(
            runtime.tr,
            "summary.done",
            "Batch transform complete.\nFiles written: {count}\nOutput folder: {output_dir}",
            count=result["count"],
            output_dir=result["output_dir"],
        )
    )
    runtime.services.record_run(
        runtime.plugin_id,
        "SUCCESS",
        _pt(runtime.tr, "run.success", "Transformed {count} images", count=result["count"]),
    )


def _handle_transform_error(runtime, payload: object) -> None:
    if isinstance(payload, dict):
        message = str(payload.get("message") or _pt(runtime.tr, "error.unknown", "Unknown image transformer error"))
    else:
        message = str(payload or _pt(runtime.tr, "error.unknown", "Unknown image transformer error"))
    runtime.set_summary(_pt(runtime.tr, "summary.failed", "Image transform failed."))
    runtime.set_output(message)
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])
    runtime.services.log(_pt(runtime.tr, "log.failed", "Image transformer failed."), "ERROR")


class ImageTransformerPlugin(StandardPlugin):
    plugin_id = "img_trans"
    name = "Image Transformer"
    description = "Batch rotate, resize, and convert images with a cleaner desktop workflow and live preview."
    category = "Media & Images"

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        return PageSpec(
            archetype="file_batch_preview",
            title=tr("title", "Image Transformer"),
            description=tr(
                "description",
                "Batch rotate, resize, and convert images with a more structured workflow and per-image preview.",
            ),
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec("rotate_enabled", "toggle", tr("label.rotate", "Rotate"), placeholder=tr("toggle.enable", "Enable")),
                        FieldSpec(
                            "rotate_mode",
                            "choice",
                            tr("label.rotate_mode", "Rotate Angle"),
                            default="90°",
                            options=(
                                ChoiceOption("90°", "90°"),
                                ChoiceOption("180°", "180°"),
                                ChoiceOption("270°", "270°"),
                            ),
                        ),
                        FieldSpec("resize_enabled", "toggle", tr("label.resize", "Resize"), placeholder=tr("toggle.enable", "Enable")),
                        FieldSpec(
                            "resize_mode",
                            "choice",
                            tr("label.resize_mode", "Resize Mode"),
                            default="pixels",
                            options=(
                                ChoiceOption("pixels", tr("resize_mode.pixels", "Pixels")),
                                ChoiceOption("percent", tr("resize_mode.percent", "Percent")),
                            ),
                        ),
                        FieldSpec("resize_width", "text", tr("label.width", "Width"), placeholder=tr("placeholder.width", "W")),
                        FieldSpec("resize_height", "text", tr("label.height", "Height"), placeholder=tr("placeholder.height", "H")),
                        FieldSpec("keep_aspect", "toggle", tr("label.keep_aspect", "Keep Aspect"), placeholder=tr("toggle.keep_aspect", "Keep aspect"), default=True),
                        FieldSpec("format_enabled", "toggle", tr("label.format", "Format"), placeholder=tr("toggle.enable", "Enable")),
                        FieldSpec(
                            "format_mode",
                            "choice",
                            tr("label.format_mode", "Format Type"),
                            default="png",
                            options=(
                                ChoiceOption("png", "PNG"),
                                ChoiceOption("jpg", "JPG"),
                                ChoiceOption("webp", "WEBP"),
                            ),
                        ),
                    ),
                ),
                SectionSpec(
                    section_id="top_actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("add_files", tr("add", "Add Images"), kind="secondary"),
                        ActionSpec("clear_files", tr("clear", "Clear All"), kind="secondary"),
                    ),
                ),
                SectionSpec(
                    section_id="files_panel",
                    kind="file_list",
                    fields=(
                        FieldSpec("files", "file_list", "", allowed_extensions=SUPPORTED_EXTENSIONS),
                    ),
                    stretch=1,
                ),
                SectionSpec(
                    section_id="preview_panel",
                    kind="preview_pane",
                    fields=(
                        FieldSpec(
                            "preview",
                            "preview",
                            "",
                            placeholder=tr("preview.empty", "Select an image to preview."),
                            semantic_class="preview_class",
                        ),
                    ),
                    stretch=2,
                ),
                SectionSpec(
                    section_id="run_actions",
                    kind="actions_row",
                    actions=(ActionSpec("run", tr("run", "Run Transform")),),
                ),
                SectionSpec(
                    section_id="result",
                    kind="summary_output_pane",
                    description=tr("summary.ready", "Choose images and configure the transform to begin."),
                    semantic_class="output_class",
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("summary.ready", "Choose images and configure the transform to begin."),
                output_placeholder=tr("summary.placeholder", "Transform summary will appear here."),
                preview_placeholder=tr("preview.empty", "Select an image to preview."),
            ),
            state=(
                StateSpec("files", []),
                StateSpec("selected_file_row", -1),
                StateSpec("current_aspect", None),
            ),
            task_specs=(
                TaskSpec(
                    task_id="run_transform",
                    worker=run_image_transform_task,
                    running_text=tr("summary.running", "Running image transform..."),
                    success_text=tr("summary.complete", "Image transform complete."),
                    error_text=tr("summary.failed", "Image transform failed."),
                ),
            ),
            enable_rules=(
                EnableRule(("rotate_mode",), predicate=lambda runtime: bool(runtime.value("rotate_enabled", False)), depends_on=("rotate_enabled",)),
                EnableRule(
                    ("resize_mode", "resize_width", "resize_height", "keep_aspect"),
                    predicate=lambda runtime: bool(runtime.value("resize_enabled", False)),
                    depends_on=("resize_enabled",),
                ),
                EnableRule(("format_mode",), predicate=lambda runtime: bool(runtime.value("format_enabled", False)), depends_on=("format_enabled",)),
            ),
            file_behaviors=(
                FileListBehaviorSpec(
                    widget_id="files",
                    state_id="files",
                    add_action_id="add_files",
                    clear_action_id="clear_files",
                    selection_state_id="selected_file_row",
                    dialog_title=tr("dialog.select_images", "Select Images"),
                    file_filter=SUPPORTED_IMAGE_FILTER,
                    remove_action_text=tr("list.remove", "Remove from list"),
                ),
            ),
            preview_bindings=(
                PreviewBindingSpec(
                    widget_id="preview",
                    builder=build_image_transform_preview,
                    dependencies=(
                        "files",
                        "selected_file_row",
                        "rotate_enabled",
                        "rotate_mode",
                        "resize_enabled",
                        "resize_mode",
                        "resize_width",
                        "resize_height",
                        "format_enabled",
                        "format_mode",
                    ),
                    empty_text=tr("preview.empty", "Select an image to preview."),
                ),
            ),
            state_reactions=(
                StateReactionSpec(
                    depends_on=(
                        "files",
                        "selected_file_row",
                        "rotate_enabled",
                        "rotate_mode",
                        "resize_enabled",
                        "resize_mode",
                        "resize_width",
                        "resize_height",
                        "keep_aspect",
                    ),
                    handler=_sync_transform_state,
                ),
            ),
            task_bindings=(
                TaskBindingSpec(
                    action_id="run",
                    task_id="run_transform",
                    payload_builder=_build_transform_payload,
                    before_run=_before_transform_run,
                    on_result=_handle_transform_result,
                    on_error=_handle_transform_error,
                ),
            ),
        )

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        return (
            CommandSpec(
                command_id="tool.img_trans.run",
                title=tr("command.run.title", "Transform Images"),
                description=tr("command.run.description", "Batch transform images using rotate, resize, and format options."),
                worker=lambda context, files, output_dir, options: run_image_transform_task(
                    context,
                    files,
                    output_dir,
                    options,
                    translate=tr,
                ),
                input_adapter=lambda payload, svc=services: {
                    "files": list(payload.get("files", [])),
                    "output_dir": str(payload.get("output_dir") or svc.default_output_path()),
                    "options": dict(payload.get("options", {})),
                },
            ),
        )
