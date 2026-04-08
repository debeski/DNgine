from __future__ import annotations
import os
from pathlib import Path
from PIL import Image
from dngine.sdk import (
    Action,
    Choice,
    CommandSpec,
    DeclarativePlugin,
    FileList,
    Output,
    PayloadRequirement,
    Preview,
    SUPPORTED_IMAGE_FILTER,
    Text,
    _pt,
    apply_tag,
    before_task_run,
    bind_tr,
    build_runtime_payload,
    handle_task_error,
    handle_task_success,
    pil_to_pixmap,
    safe_output_extension,
)

SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".heic", ".heif")

def run_image_tagger_task(
    context,
    files: list[str],
    output_dir: str,
    name: str,
    date_mode: str = "taken",
    custom_date: str = "",
    *,
    translate=None,
):
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(len(files)))
        context.log(_pt(translate, "log.tagging", "Tagging {file}...", file=os.path.basename(file_path)))
        image = Image.open(file_path)
        tagged = apply_tag(image, name, date_mode, custom_date)
        output_ext = safe_output_extension(file_path, None)
        output_path = os.path.join(output_dir, f"tagged_{Path(file_path).stem}{output_ext}")
        save_format = output_ext.lstrip(".").upper()
        tagged.save(output_path, format="JPEG" if save_format == "JPG" else save_format)
        output_files.append(output_path)
    context.log(_pt(translate, "log.done", "Batch tagging complete. Wrote {count} files.", count=len(output_files)))
    return {"count": len(output_files), "output_dir": output_dir, "files": output_files}

def _preview_name(runtime) -> str:
    return str(runtime.value("name", "") or "").strip() or _pt(runtime.tr, "preview.default_name", "PREVIEW")

def build_image_tagger_preview(runtime):
    path = runtime.selected_file("files")
    if not path:
        return {"pixmap": None, "text": _pt(runtime.tr, "preview.empty", "Select an image to preview.")}
    with Image.open(path) as image:
        tagged_preview = apply_tag(
            image,
            _preview_name(runtime),
            str(runtime.value("date_mode", "taken") or "taken"),
            str(runtime.value("custom_date", "") or "").strip(),
        )
    return {"pixmap": pil_to_pixmap(tagged_preview), "text": ""}

def _build_payload(runtime):
    return build_runtime_payload(
        runtime,
        required=(
            PayloadRequirement(
                "files",
                lambda rt: rt.files("files"),
                _pt(runtime.tr, "error.missing_files", "Add at least one image first."),
                title=_pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            ),
            PayloadRequirement(
                "name",
                lambda rt: str(rt.value("name", "") or "").strip(),
                _pt(runtime.tr, "error.missing_name", "Enter a tag name first."),
                title=_pt(runtime.tr, "error.missing_input.title", "Missing Input"),
            ),
        ),
        choose_directory=("output_dir", _pt(runtime.tr, "dialog.select_output", "Select Output Folder")),
        extras={
            "date_mode": lambda rt: str(rt.value("date_mode", "taken") or "taken"),
            "custom_date": lambda rt: str(rt.value("custom_date", "") or "").strip(),
            "translate": lambda rt: rt.tr,
        },
    )

class ImageTaggerPlugin(DeclarativePlugin):
    plugin_id = "tagger"
    name = "Image Tagger"
    description = "Batch-apply a smart glassmorphic date/name tag to images with live preview and cleaner controls."
    category = "Media & Images"

    def declare_page(self, services):
        tr = bind_tr(services, self.plugin_id)
        return {
            "name": Text(tr("label.name", "Tag Name"), placeholder=tr("placeholder.name", "Name or signature")),
            "date_mode": Choice(
                tr("label.date_source", "Date Source"),
                options=(
                    ("taken", tr("date_mode.taken", "Taken date")),
                    ("today", tr("date_mode.today", "Today's date")),
                    ("custom", tr("date_mode.custom", "Custom date")),
                ),
                default="taken",
            ),
            "custom_date": Text(
                tr("label.custom_date", "Custom Date"),
                placeholder=tr("placeholder.date", "YYYY-MM-DD or any parseable date"),
                visible_when={"date_mode": "custom"},
            ),
            "files": FileList(
                extensions=SUPPORTED_EXTENSIONS,
                add_label=tr("add", "Add Images"),
                clear_label=tr("clear", "Clear All"),
                remove_label=tr("list.remove", "Remove from list"),
                dialog_title=tr("dialog.select_images", "Select Images"),
                file_filter=SUPPORTED_IMAGE_FILTER,
            ),
            "preview": Preview(
                builder=build_image_tagger_preview,
                empty_text=tr("preview.empty", "Select an image to preview."),
                dependencies=("files", "files.__selected_row", "name", "date_mode", "custom_date"),
            ),
            "run": Action(
                tr("run", "Run Tagger"),
                worker=run_image_tagger_task,
                payload_builder=_build_payload,
                before_run=lambda runtime: before_task_run(
                    runtime,
                    _pt(runtime.tr, "summary.running", "Running image tagger..."),
                ),
                on_result=lambda runtime, payload: handle_task_success(
                    runtime,
                    payload,
                    summary=_pt(runtime.tr, "summary.complete", "Image tagger complete."),
                    output=lambda result: _pt(
                        runtime.tr,
                        "summary.done",
                        "Batch tagging complete.\nFiles written: {count}\nOutput folder: {output_dir}",
                        count=result["count"],
                        output_dir=result["output_dir"],
                    ),
                    run_detail=lambda result: _pt(
                        runtime.tr,
                        "run.success",
                        "Tagged {count} images",
                        count=result["count"],
                    ),
                ),
                on_error=lambda runtime, payload: handle_task_error(
                    runtime,
                    payload,
                    summary=_pt(runtime.tr, "summary.failed", "Image tagger failed."),
                    fallback=_pt(runtime.tr, "error.unknown", "Unknown image tagger error"),
                    log_message=_pt(runtime.tr, "log.failed", "Image tagger failed."),
                ),
                running_text=tr("summary.running", "Running image tagger..."),
                success_text=tr("summary.complete", "Image tagger complete."),
                error_text=tr("summary.failed", "Image tagger failed."),
            ),
            "result": Output(
                ready_text=tr("summary.ready", "Choose images and configure the tag to begin."),
                placeholder=tr("summary.placeholder", "Tagger summary will appear here."),
            ),
        }

    def declare_command_specs(self, services):
        tr = bind_tr(services, self.plugin_id)
        return (
            CommandSpec(
                command_id="tool.tagger.run",
                title=tr("command.run.title", "Tag Images"),
                description=tr("command.run.description", "Batch apply date and name tags to images."),
                worker=lambda context, files, output_dir, name, date_mode="taken", custom_date="": run_image_tagger_task(
                    context,
                    files,
                    output_dir,
                    name,
                    date_mode,
                    custom_date,
                    translate=tr,
                ),
                input_adapter=lambda payload, svc=services: {
                    "files": list(payload.get("files", [])),
                    "output_dir": str(payload.get("output_dir") or svc.default_output_path()),
                    "name": str(payload.get("name", "")),
                    "date_mode": str(payload.get("date_mode", "taken")),
                    "custom_date": str(payload.get("custom_date", "")),
                },
            ),
        )