from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageFilter
from PySide6.QtCore import QTimer

from dngine.sdk import (
    ActionSpec,
    ChoiceOption,
    EnableRule,
    FieldSpec,
    FileListBehaviorSpec,
    PageSpec,
    PreviewBindingSpec,
    ResultSpec,
    SectionSpec,
    SUPPORTED_IMAGE_FILTER,
    StandardPlugin,
    StateReactionSpec,
    StateSpec,
    TaskBindingSpec,
    TaskSpec,
    VisibilityRule,
    _pt,
    bind_tr,
    pil_to_pixmap,
)

SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".heic"]
PREVIEW_MASK_MAX_SIDE = 960
PREVIEW_MASK_MAX_PIXELS = 1_200_000
RUN_MASK_MAX_SIDE = 2048
RUN_MASK_MAX_PIXELS = 4_200_000
def _clamp(value: int) -> int:
    return max(0, min(255, int(value)))


def _parse_color(value: str) -> tuple[int, int, int]:
    try:
        return ImageColor.getrgb((value or "").strip() or "#ffffff")
    except Exception:
        return (255, 255, 255)


@dataclass(frozen=True)
class _AiRuntimeStatus:
    available: bool
    reason: str = ""


def _sample_points(image: Image.Image) -> list[tuple[int, int, int]]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    points = [
        (0, 0),
        (width - 1, 0),
        (0, height - 1),
        (width - 1, height - 1),
        (width // 2, 0),
        (width // 2, height - 1),
        (0, height // 2),
        (width - 1, height // 2),
    ]
    pixels = rgb.load()
    samples: list[tuple[int, int, int]] = []
    for x, y in points:
        samples.append(tuple(int(channel) for channel in pixels[max(0, x), max(0, y)]))
    return samples


def _distance(color: tuple[int, int, int], sample: tuple[int, int, int]) -> int:
    return abs(color[0] - sample[0]) + abs(color[1] - sample[1]) + abs(color[2] - sample[2])


def _background_similarity_mask(image: Image.Image, samples: list[tuple[int, int, int]], *, threshold: int, feather: int) -> Image.Image:
    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels = rgb.load()
    matte = Image.new("L", rgb.size, 0)
    matte_pixels = matte.load()
    feather = max(1, feather)
    for y in range(height):
        for x in range(width):
            color = tuple(int(channel) for channel in pixels[x, y])
            distance = min(_distance(color, sample) for sample in samples)
            if distance <= threshold:
                value = 0
            else:
                scaled = (distance - threshold) * 255 // feather
                value = _clamp(scaled)
            matte_pixels[x, y] = value
    return matte


def _refine_alpha(alpha: Image.Image) -> Image.Image:
    matte = alpha.convert("L")
    matte = matte.filter(ImageFilter.MaxFilter(5))
    matte = matte.filter(ImageFilter.MinFilter(3))
    matte = matte.filter(ImageFilter.GaussianBlur(radius=1.8))
    return matte.point(lambda value: 255 if value >= 220 else (0 if value <= 12 else value))


@lru_cache(maxsize=1)
def _probe_ai_runtime() -> _AiRuntimeStatus:
    try:
        import onnxruntime as ort
    except Exception as exc:
        return _AiRuntimeStatus(False, str(exc))

    try:
        providers = tuple(str(item) for item in ort.get_available_providers())
    except Exception as exc:
        return _AiRuntimeStatus(False, str(exc))
    if providers and "CPUExecutionProvider" not in providers:
        return _AiRuntimeStatus(False, "CPU execution provider is unavailable.")

    try:
        from rembg import remove
    except Exception as exc:
        return _AiRuntimeStatus(False, str(exc))
    _ = remove
    return _AiRuntimeStatus(True, "")


@lru_cache(maxsize=1)
def _get_ai_session():
    status = _probe_ai_runtime()
    if not status.available:
        return None
    from rembg import new_session

    try:
        return new_session(providers=["CPUExecutionProvider"])
    except TypeError:
        return new_session()
    except Exception:
        return None


def _prepare_working_image(
    image: Image.Image,
    *,
    max_side: int,
    max_pixels: int,
) -> tuple[Image.Image, bool]:
    rgba = image.convert("RGBA")
    width, height = rgba.size
    if width <= 0 or height <= 0:
        return rgba, False

    scale = 1.0
    longest_side = max(width, height)
    if longest_side > max_side > 0:
        scale = min(scale, float(max_side) / float(longest_side))

    total_pixels = width * height
    if total_pixels > max_pixels > 0:
        scale = min(scale, math.sqrt(float(max_pixels) / float(total_pixels)))

    if scale >= 0.999:
        return rgba, False

    target_size = (
        max(1, int(round(width * scale))),
        max(1, int(round(height * scale))),
    )
    return rgba.resize(target_size, Image.Resampling.LANCZOS), True


def _ai_alpha(image: Image.Image) -> tuple[Image.Image | None, str]:
    status = _probe_ai_runtime()
    if not status.available:
        return None, status.reason

    try:
        from rembg import remove

        session = _get_ai_session()
        if session is None:
            return None, "CPU AI session could not be created."
        result = remove(image, session=session)
        if isinstance(result, Image.Image):
            return result.convert("RGBA").getchannel("A"), ""
        if isinstance(result, bytes):
            return Image.open(io.BytesIO(result)).convert("RGBA").getchannel("A"), ""
    except Exception as exc:
        return None, str(exc)
    return None, "AI output was unavailable."


def build_background_mask(
    image: Image.Image,
    strategy: str,
    *,
    allow_ai: bool = True,
    preview_mode: bool = False,
) -> tuple[Image.Image, list[str]]:
    notes: list[str] = []
    working_image, scaled = _prepare_working_image(
        image,
        max_side=PREVIEW_MASK_MAX_SIDE if preview_mode else RUN_MASK_MAX_SIDE,
        max_pixels=PREVIEW_MASK_MAX_PIXELS if preview_mode else RUN_MASK_MAX_PIXELS,
    )
    if scaled and not preview_mode:
        notes.append("scaled_mask")
    strategy = str(strategy or "auto").strip().lower()
    samples = _sample_points(working_image)
    corner_mask = _background_similarity_mask(working_image, samples[:4], threshold=64, feather=96)
    edge_mask = _background_similarity_mask(working_image, samples, threshold=52, feather=90)
    heuristic = ImageChops.lighter(corner_mask, edge_mask)
    if strategy == "edge":
        alpha = _refine_alpha(edge_mask)
    elif strategy == "backdrop":
        alpha = _refine_alpha(corner_mask)
    else:
        alpha = _refine_alpha(heuristic)
        if allow_ai and not preview_mode:
            ai_mask, ai_error = _ai_alpha(working_image)
            if ai_mask is not None:
                hybrid = ImageChops.lighter(ai_mask.convert("L"), heuristic)
                alpha = _refine_alpha(hybrid)
            elif ai_error:
                notes.append("ai_fallback")
    if alpha.size != image.size:
        alpha = alpha.resize(image.size, Image.Resampling.LANCZOS)
    return alpha, notes


def _compose_background_result(
    image: Image.Image,
    alpha: Image.Image,
    *,
    background_mode: str,
    custom_color: str,
    crop_to_subject: bool,
) -> Image.Image:
    rgba = image.convert("RGBA").copy()
    matte = alpha.convert("L").copy()
    rgba.putalpha(matte)

    bbox = matte.point(lambda value: 255 if value >= 24 else 0).getbbox()
    if crop_to_subject and bbox:
        rgba = rgba.crop(bbox)

    mode = str(background_mode or "transparent").strip().lower()
    if mode == "transparent":
        return rgba

    if mode == "custom":
        fill = _parse_color(custom_color)
    elif mode == "black":
        fill = (0, 0, 0)
    else:
        fill = (255, 255, 255)

    background = Image.new("RGBA", rgba.size, fill + (255,))
    return Image.alpha_composite(background, rgba).convert("RGBA")


def build_preview_payload(file_path: str, strategy: str) -> dict[str, object]:
    with Image.open(file_path) as image:
        preview_image, _ = _prepare_working_image(
            image,
            max_side=PREVIEW_MASK_MAX_SIDE,
            max_pixels=PREVIEW_MASK_MAX_PIXELS,
        )
        alpha, _ = build_background_mask(
            preview_image,
            strategy,
            allow_ai=False,
            preview_mode=False,
        )
    return {
        "preview_image": preview_image.copy(),
        "preview_alpha": alpha.copy(),
    }


def apply_background_removal(
    image: Image.Image,
    *,
    strategy: str,
    background_mode: str,
    custom_color: str,
    crop_to_subject: bool,
    allow_ai: bool = True,
    preview_mode: bool = False,
) -> tuple[Image.Image, list[str]]:
    rgba = image.convert("RGBA")
    alpha, notes = build_background_mask(
        rgba,
        strategy,
        allow_ai=allow_ai,
        preview_mode=preview_mode,
    )
    return (
        _compose_background_result(
            rgba,
            alpha,
            background_mode=background_mode,
            custom_color=custom_color,
            crop_to_subject=crop_to_subject,
        ),
        notes,
    )


def run_smart_background_task(
    context,
    files: list[str],
    output_dir: str,
    options: dict[str, object],
    *,
    translate=None,
):
    os.makedirs(output_dir, exist_ok=True)
    written_files: list[str] = []
    skipped: list[str] = []
    warned_files: set[tuple[str, str]] = set()
    strategy_value = str(options.get("strategy", "auto"))
    if strategy_value == "auto":
        ai_status = _probe_ai_runtime()
        if ai_status.available:
            context.log(
                _pt(
                    translate,
                    "log.preparing_ai",
                    "Preparing AI background-removal runtime. First use may take longer while the model is readied.",
                )
            )
        else:
            context.log(
                _pt(
                    translate,
                    "log.ai_runtime_unavailable",
                    "AI runtime is unavailable in this session. SMART Background Remover will use fallback masking.",
                ),
                "WARNING",
            )
    for index, file_path in enumerate(files, start=1):
        context.progress(index / float(max(1, len(files))))
        context.log(_pt(translate, "log.processing", "Removing background from {file}...", file=os.path.basename(file_path)))
        try:
            with Image.open(file_path) as image:
                result, notes = apply_background_removal(
                    image,
                    strategy=strategy_value,
                    background_mode=str(options.get("background_mode", "transparent")),
                    custom_color=str(options.get("custom_color", "#ffffff")),
                    crop_to_subject=bool(options.get("crop_to_subject", False)),
                    allow_ai=True,
                    preview_mode=False,
                )
            file_name = os.path.basename(file_path)
            for note in notes:
                dedupe_key = (file_name, note)
                if dedupe_key in warned_files:
                    continue
                warned_files.add(dedupe_key)
                if note == "scaled_mask":
                    context.log(
                        _pt(
                            translate,
                            "log.large_image",
                            "Large image detected for {file}. Using a reduced working mask to keep memory usage stable.",
                            file=file_name,
                        ),
                        "WARNING",
                    )
                elif note == "ai_fallback":
                    context.log(
                        _pt(
                            translate,
                            "log.ai_fallback",
                            "AI runtime is unavailable for {file}. Using fallback masking only.",
                            file=file_name,
                        ),
                        "WARNING",
                    )
            output_name = f"smart_bg_{Path(file_path).stem}.png"
            output_path = os.path.join(output_dir, output_name)
            result.save(output_path, format="PNG")
            written_files.append(output_path)
        except Exception as exc:
            skipped.append(f"{os.path.basename(file_path)}: {exc}")
            context.log(_pt(translate, "log.skipped", "Skipped {file}: {reason}", file=os.path.basename(file_path), reason=str(exc)), "WARNING")

    context.log(
        _pt(
            translate,
            "log.done",
            "SMART background removal finished. Wrote {count} files and skipped {skipped}.",
            count=len(written_files),
            skipped=len(skipped),
        )
    )
    return {
        "count": len(written_files),
        "skipped_count": len(skipped),
        "output_dir": output_dir,
        "files": written_files,
        "skipped": skipped,
    }
def _background_options(runtime) -> dict[str, object]:
    return {
        "strategy": str(runtime.value("strategy", "auto") or "auto"),
        "background_mode": str(runtime.value("background_mode", "transparent") or "transparent"),
        "custom_color": str(runtime.value("custom_color", "#ffffff") or "").strip(),
        "crop_to_subject": bool(runtime.value("crop_to_subject", False)),
    }


def _preview_source_key(runtime, path: str) -> str:
    try:
        stat = Path(path).stat()
        stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
    except Exception:
        stamp = "missing"
    return f"{path}|{stamp}|{runtime.value('strategy', 'auto')}"


def _preview_widget(runtime):
    return runtime.widget("preview")


def _stop_preview_timer(runtime) -> None:
    timer = runtime.flag("smart_bg_preview_timer")
    if timer is not None:
        timer.stop()


def _reset_preview_cache(runtime) -> None:
    runtime.set_flag("smart_bg_loading_key", "")
    runtime.set_flag("smart_bg_cached_key", "")
    runtime.set_flag("smart_bg_cached_image", None)
    runtime.set_flag("smart_bg_cached_alpha", None)


def _sync_preview_tooltip(runtime, _changed_key: str = "") -> None:
    widget = _preview_widget(runtime)
    if widget is None:
        return
    status = str(runtime.value("preview_status", "empty") or "empty")
    if runtime.selected_file("files") and status in {"loading", "ready"}:
        widget.setToolTip(
            _pt(
                runtime.tr,
                "preview.safe_mode",
                "Preview uses a reduced, non-AI cutout to keep the app responsive.",
            )
        )
        return
    widget.setToolTip("")


def _preview_binding(runtime):
    path = runtime.selected_file("files")
    if not path:
        return {"pixmap": None, "text": _pt(runtime.tr, "preview.empty", "Select an image to preview the cutout.")}

    status = str(runtime.value("preview_status", "empty") or "empty")
    if status == "loading":
        return {"pixmap": None, "text": _pt(runtime.tr, "preview.loading", "Building preview...")}
    if status == "error":
        return {
            "pixmap": None,
            "text": _pt(
                runtime.tr,
                "preview.error",
                "Preview error: {message}",
                message=str(runtime.value("preview_error", "Preview failed.") or "Preview failed."),
            ),
        }

    preview_image = runtime.flag("smart_bg_cached_image")
    preview_alpha = runtime.flag("smart_bg_cached_alpha")
    if not isinstance(preview_image, Image.Image) or not isinstance(preview_alpha, Image.Image):
        return {"pixmap": None, "text": _pt(runtime.tr, "preview.empty", "Select an image to preview the cutout.")}

    try:
        result = _compose_background_result(
            preview_image,
            preview_alpha,
            background_mode=str(runtime.value("background_mode", "transparent") or "transparent"),
            custom_color=str(runtime.value("custom_color", "#ffffff") or "").strip(),
            crop_to_subject=bool(runtime.value("crop_to_subject", False)),
        )
    except Exception as exc:
        return {
            "pixmap": None,
            "text": _pt(runtime.tr, "preview.error", "Preview error: {message}", message=str(exc)),
        }
    return {"pixmap": pil_to_pixmap(result), "text": ""}


def _handle_preview_result(runtime, request_id: int, cache_key: str, payload: object) -> None:
    if request_id != int(runtime.flag("smart_bg_request_id", 0) or 0):
        return
    result = dict(payload) if isinstance(payload, dict) else {}
    preview_image = result.get("preview_image")
    preview_alpha = result.get("preview_alpha")
    if not isinstance(preview_image, Image.Image) or not isinstance(preview_alpha, Image.Image):
        _handle_preview_error(runtime, request_id, cache_key, {"message": "Preview payload was invalid."})
        return
    runtime.set_flag("smart_bg_loading_key", "")
    runtime.set_flag("smart_bg_cached_key", cache_key)
    runtime.set_flag("smart_bg_cached_image", preview_image.copy())
    runtime.set_flag("smart_bg_cached_alpha", preview_alpha.copy())
    runtime.set_value("preview_error", "")
    runtime.set_value("preview_status", "ready")


def _handle_preview_error(runtime, request_id: int, cache_key: str, payload: object) -> None:
    if request_id != int(runtime.flag("smart_bg_request_id", 0) or 0):
        return
    if runtime.flag("smart_bg_loading_key", "") == cache_key:
        runtime.set_flag("smart_bg_loading_key", "")
    message = payload.get("message", "Preview failed.") if isinstance(payload, dict) else str(payload)
    runtime.set_value("preview_error", str(message))
    runtime.set_value("preview_status", "error")


def _start_preview_refresh(runtime) -> None:
    path = runtime.selected_file("files")
    if not path:
        runtime.set_value("preview_error", "")
        runtime.set_value("preview_status", "empty")
        _sync_preview_tooltip(runtime)
        return

    cache_key = _preview_source_key(runtime, path)
    cached_key = str(runtime.flag("smart_bg_cached_key", "") or "")
    cached_image = runtime.flag("smart_bg_cached_image")
    cached_alpha = runtime.flag("smart_bg_cached_alpha")
    if (
        cache_key == cached_key
        and isinstance(cached_image, Image.Image)
        and isinstance(cached_alpha, Image.Image)
    ):
        runtime.set_value("preview_error", "")
        runtime.set_value("preview_status", "ready")
        _sync_preview_tooltip(runtime)
        return

    if cache_key == str(runtime.flag("smart_bg_loading_key", "") or ""):
        return

    request_id = int(runtime.flag("smart_bg_request_id", 0) or 0) + 1
    runtime.set_flag("smart_bg_request_id", request_id)
    runtime.set_flag("smart_bg_loading_key", cache_key)
    runtime.set_value("preview_error", "")
    runtime.set_value("preview_status", "loading")
    _sync_preview_tooltip(runtime)

    strategy = str(runtime.value("strategy", "auto") or "auto")
    runtime.services.run_task(
        lambda _context: build_preview_payload(path, strategy),
        on_result=lambda payload, rid=request_id, key=cache_key: _handle_preview_result(runtime, rid, key, payload),
        on_error=lambda payload, rid=request_id, key=cache_key: _handle_preview_error(runtime, rid, key, payload),
    )


def _schedule_preview_refresh(runtime, _changed_key: str, *, immediate: bool = False) -> None:
    timer = runtime.flag("smart_bg_preview_timer")
    path = runtime.selected_file("files")
    if not path:
        _stop_preview_timer(runtime)
        _reset_preview_cache(runtime)
        runtime.set_value("preview_error", "")
        runtime.set_value("preview_status", "empty")
        _sync_preview_tooltip(runtime)
        return

    cache_key = _preview_source_key(runtime, path)
    cached_key = str(runtime.flag("smart_bg_cached_key", "") or "")
    cached_image = runtime.flag("smart_bg_cached_image")
    cached_alpha = runtime.flag("smart_bg_cached_alpha")
    if (
        cache_key == cached_key
        and isinstance(cached_image, Image.Image)
        and isinstance(cached_alpha, Image.Image)
    ):
        runtime.set_value("preview_error", "")
        runtime.set_value("preview_status", "ready")
        _sync_preview_tooltip(runtime)
        return

    runtime.set_value("preview_error", "")
    runtime.set_value("preview_status", "loading")
    _sync_preview_tooltip(runtime)
    if timer is None or immediate:
        _start_preview_refresh(runtime)
        return
    timer.stop()
    timer.start()


def _build_run_payload(runtime) -> dict[str, object] | None:
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
        "options": _background_options(runtime),
        "translate": runtime.tr,
    }


def _before_run(runtime) -> None:
    runtime.clear_output()
    runtime.set_summary(_pt(runtime.tr, "summary.running", "Running SMART background removal..."))


def _handle_run_result(runtime, payload: object) -> None:
    result = dict(payload)
    skipped_lines = "\n".join(f"- {entry}" for entry in result.get("skipped", []))
    output = _pt(
        runtime.tr,
        "summary.done",
        "SMART background removal complete.\nFiles written: {count}\nSkipped: {skipped}\nOutput folder: {output_dir}",
        count=result["count"],
        skipped=result["skipped_count"],
        output_dir=result["output_dir"],
    )
    if skipped_lines:
        output = f"{output}\n\n{_pt(runtime.tr, 'summary.skipped', 'Skipped files:')}\n{skipped_lines}"
    runtime.set_summary(_pt(runtime.tr, "summary.complete", "SMART background removal complete."))
    runtime.set_output(output)
    runtime.services.record_run(
        runtime.plugin_id,
        "SUCCESS",
        _pt(runtime.tr, "run.success", "Generated {count} cutout images", count=result["count"]),
    )


def _handle_task_error(runtime, payload: object) -> None:
    if isinstance(payload, dict):
        message = str(payload.get("message") or _pt(runtime.tr, "error.unknown", "Unknown SMART background-removal error"))
    else:
        message = str(payload or _pt(runtime.tr, "error.unknown", "Unknown SMART background-removal error"))
    runtime.set_summary(_pt(runtime.tr, "summary.failed", "SMART background removal failed."))
    runtime.set_output(message)
    runtime.services.record_run(runtime.plugin_id, "ERROR", message[:500])
    runtime.services.log(_pt(runtime.tr, "log.failed", "SMART background removal failed."), "ERROR")


class SmartBackgroundRemoverPlugin(StandardPlugin):
    plugin_id = "smart_bg"
    name = "SMART Background Remover"
    description = "Cut image backgrounds with AI-assisted masking, creative fallback strategies, and clean export options."
    category = "Media & Images"

    def declare_page_spec(self, services):
        tr = bind_tr(services, self.plugin_id)
        return PageSpec(
            archetype="file_batch_preview",
            title=tr("title", "SMART Background Remover"),
            description=tr(
                "description",
                "Remove image backgrounds with AI-assisted masking, edge-aware fallback passes, and flexible export styling.",
            ),
            sections=(
                SectionSpec(
                    section_id="settings",
                    kind="settings_card",
                    fields=(
                        FieldSpec(
                            "strategy",
                            "choice",
                            tr("label.strategy", "Strategy"),
                            default="auto",
                            options=(
                                ChoiceOption("auto", tr("strategy.auto", "Auto Smart")),
                                ChoiceOption("edge", tr("strategy.edge", "Edge Sweep")),
                                ChoiceOption("backdrop", tr("strategy.backdrop", "Backdrop Key")),
                            ),
                        ),
                        FieldSpec(
                            "background_mode",
                            "choice",
                            tr("label.background", "Output Background"),
                            default="transparent",
                            options=(
                                ChoiceOption("transparent", tr("background.transparent", "Transparent PNG")),
                                ChoiceOption("white", tr("background.white", "Solid White")),
                                ChoiceOption("black", tr("background.black", "Solid Black")),
                                ChoiceOption("custom", tr("background.custom", "Custom Color")),
                            ),
                        ),
                        FieldSpec("custom_color", "text", tr("label.custom_color", "Custom Color"), default="#ffffff", placeholder=tr("placeholder.color", "#ffffff")),
                        FieldSpec("crop_to_subject", "toggle", tr("label.crop", "Crop"), placeholder=tr("option.crop", "Crop to subject")),
                    ),
                ),
                SectionSpec(
                    section_id="file_actions",
                    kind="actions_row",
                    actions=(
                        ActionSpec("add_files", tr("add", "Add Images"), kind="secondary"),
                        ActionSpec("clear_files", tr("clear", "Clear All"), kind="secondary"),
                    ),
                ),
                SectionSpec(
                    section_id="files_panel",
                    kind="file_list",
                    fields=(FieldSpec("files", "file_list", tr("label.files", "Files"), allowed_extensions=tuple(SUPPORTED_EXTENSIONS)),),
                    stretch=1,
                ),
                SectionSpec(
                    section_id="preview_panel",
                    kind="preview_pane",
                    fields=(FieldSpec("preview", "preview", "", placeholder=tr("preview.empty", "Select an image to preview the cutout.")),),
                    stretch=2,
                ),
                SectionSpec(
                    section_id="run_actions",
                    kind="actions_row",
                    actions=(ActionSpec("run", tr("run", "Run SMART Cutout")),),
                ),
                SectionSpec(
                    section_id="result",
                    kind="summary_output_pane",
                    description=tr("summary.ready", "Choose images and refine the cutout settings to begin."),
                    semantic_class="output_class",
                    stretch=1,
                ),
            ),
            result_spec=ResultSpec(
                summary_placeholder=tr("summary.ready", "Choose images and refine the cutout settings to begin."),
                output_placeholder=tr("summary.placeholder", "SMART background-removal activity will appear here."),
                preview_placeholder=tr("preview.empty", "Select an image to preview the cutout."),
            ),
            state=(
                StateSpec("files", []),
                StateSpec("selected_file_row", -1),
                StateSpec("preview_status", "empty"),
                StateSpec("preview_error", ""),
            ),
            task_specs=(
                TaskSpec(
                    task_id="run_smart_background",
                    worker=run_smart_background_task,
                    running_text=tr("summary.running", "Running SMART background removal..."),
                    success_text=tr("summary.complete", "SMART background removal complete."),
                    error_text=tr("summary.failed", "SMART background removal failed."),
                ),
            ),
            enable_rules=(
                EnableRule(("clear_files", "run"), predicate=lambda runtime: bool(runtime.files("files")), depends_on=("files",)),
            ),
            visibility_rules=(
                VisibilityRule(
                    ("custom_color", "custom_color.label"),
                    predicate=lambda runtime: str(runtime.value("background_mode", "transparent") or "transparent") == "custom",
                    depends_on=("background_mode",),
                ),
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
                    builder=_preview_binding,
                    dependencies=(
                        "files",
                        "selected_file_row",
                        "background_mode",
                        "custom_color",
                        "crop_to_subject",
                        "preview_status",
                        "preview_error",
                    ),
                    empty_text=tr("preview.empty", "Select an image to preview the cutout."),
                ),
            ),
            state_reactions=(
                StateReactionSpec(
                    depends_on=("files", "selected_file_row", "strategy"),
                    handler=_schedule_preview_refresh,
                ),
                StateReactionSpec(
                    depends_on=("files", "selected_file_row", "preview_status"),
                    handler=_sync_preview_tooltip,
                ),
            ),
            task_bindings=(
                TaskBindingSpec(
                    action_id="run",
                    task_id="run_smart_background",
                    payload_builder=_build_run_payload,
                    before_run=_before_run,
                    on_result=_handle_run_result,
                    on_error=_handle_task_error,
                ),
            ),
        )

    def configure_page(self, page, services) -> None:
        super().configure_page(page, services)
        runtime = getattr(page, "_sdk_runtime", None)
        preview = page.generated_widgets.get("preview")
        if preview is not None:
            preview.setMinimumHeight(320)
        if runtime is None:
            return
        timer = QTimer(page)
        timer.setSingleShot(True)
        timer.setInterval(140)
        timer.timeout.connect(lambda: _start_preview_refresh(runtime))
        runtime.set_flag("smart_bg_preview_timer", timer)
        runtime.set_flag("smart_bg_request_id", 0)
        runtime.set_flag("smart_bg_loading_key", "")
        runtime.set_flag("smart_bg_cached_key", "")
        runtime.set_flag("smart_bg_cached_image", None)
        runtime.set_flag("smart_bg_cached_alpha", None)
        page.refresh_preview = lambda immediate=False: _schedule_preview_refresh(runtime, "", immediate=bool(immediate))
        _sync_preview_tooltip(runtime)
