from __future__ import annotations

import io
import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageFilter
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from dngine.core.media_utils import SUPPORTED_IMAGE_FILTER, pil_to_pixmap
from dngine.core.page_style import apply_page_chrome, apply_semantic_class
from dngine.core.plugin_api import QtPlugin, bind_tr, safe_tr
from dngine.core.widgets import DroppableListWidget, ScrollSafeComboBox


QComboBox = ScrollSafeComboBox

SUPPORTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".heic"]
PREVIEW_MASK_MAX_SIDE = 960
PREVIEW_MASK_MAX_PIXELS = 1_200_000
RUN_MASK_MAX_SIDE = 2048
RUN_MASK_MAX_PIXELS = 4_200_000


def _pt(translate, key: str, default: str | None = None, **kwargs) -> str:
    return safe_tr(translate, key, default, **kwargs)


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


class SmartBackgroundRemoverPlugin(QtPlugin):
    plugin_id = "smart_bg"
    name = "SMART Background Remover"
    description = "Cut image backgrounds with AI-assisted masking, creative fallback strategies, and clean export options."
    category = "Media & Images"

    def create_widget(self, services) -> QWidget:
        return SmartBackgroundRemoverPage(services, self.plugin_id)


class SmartBackgroundRemoverPage(QWidget):
    def __init__(self, services, plugin_id: str):
        super().__init__()
        self.services = services
        self.plugin_id = plugin_id
        self.tr = bind_tr(services, plugin_id)
        self.files: list[str] = []
        self._preview_request_id = 0
        self._preview_loading_key = ""
        self._preview_cached_key = ""
        self._preview_cached_image: Image.Image | None = None
        self._preview_cached_alpha: Image.Image | None = None
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(140)
        self._preview_timer.timeout.connect(self._start_preview_refresh)
        self._build_ui()
        self._apply_texts()
        self.services.i18n.language_changed.connect(self._handle_language_change)
        self.services.theme_manager.theme_changed.connect(self._handle_theme_change)

    def _pt(self, key: str, default: str | None = None, **kwargs) -> str:
        return _pt(self.tr, key, default, **kwargs)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 28, 28, 28)
        outer.setSpacing(16)

        self.title_label = QLabel()
        outer.addWidget(self.title_label)

        self.description_label = QLabel()
        self.description_label.setWordWrap(True)
        outer.addWidget(self.description_label)

        self.settings_card = QFrame()
        settings_layout = QGridLayout(self.settings_card)
        settings_layout.setContentsMargins(16, 14, 16, 14)
        settings_layout.setHorizontalSpacing(12)
        settings_layout.setVerticalSpacing(10)

        self.strategy_label = QLabel()
        settings_layout.addWidget(self.strategy_label, 0, 0)
        self.strategy_combo = QComboBox()
        self.strategy_combo.currentIndexChanged.connect(self._refresh_preview)
        settings_layout.addWidget(self.strategy_combo, 0, 1)

        self.background_label = QLabel()
        settings_layout.addWidget(self.background_label, 1, 0)
        background_row = QHBoxLayout()
        self.background_combo = QComboBox()
        self.background_combo.currentIndexChanged.connect(self._handle_background_mode_change)
        self.color_input = QLineEdit()
        self.color_input.textChanged.connect(self._refresh_preview)
        background_row.addWidget(self.background_combo, 1)
        background_row.addWidget(self.color_input)
        settings_layout.addLayout(background_row, 1, 1)

        self.crop_checkbox = QCheckBox()
        self.crop_checkbox.toggled.connect(self._refresh_preview)
        settings_layout.addWidget(self.crop_checkbox, 2, 1)

        self.files_label = QLabel()
        settings_layout.addWidget(self.files_label, 3, 0)
        files_row = QHBoxLayout()
        self.add_button = QPushButton()
        self.add_button.clicked.connect(self._add_files)
        self.clear_button = QPushButton()
        self.clear_button.clicked.connect(self._clear_files)
        files_row.addWidget(self.add_button)
        files_row.addWidget(self.clear_button)
        files_row.addStretch(1)
        settings_layout.addLayout(files_row, 3, 1)

        outer.addWidget(self.settings_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(splitter, 1)

        left_panel = QWidget()
        apply_semantic_class(left_panel, "transparent_class")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        self.file_list = DroppableListWidget(mode="file", allowed_extensions=SUPPORTED_EXTENSIONS)
        self.file_list.remove_requested.connect(self._remove_file_at)
        self.file_list.currentRowChanged.connect(self._show_preview_for_row)
        self.file_list.files_dropped.connect(self._handle_files_dropped)
        left_layout.addWidget(self.file_list, 1)
        splitter.addWidget(left_panel)

        right_panel = QWidget()
        apply_semantic_class(right_panel, "transparent_class")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumHeight(320)
        apply_semantic_class(self.preview_label, "preview_class")
        right_layout.addWidget(self.preview_label, 1)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        controls = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.clicked.connect(self._run)
        controls.addWidget(self.run_button, 0, Qt.AlignmentFlag.AlignLeft)
        controls.addStretch(1)
        outer.addLayout(controls)

        self.summary_output = QPlainTextEdit()
        self.summary_output.setReadOnly(True)
        apply_semantic_class(self.summary_output, "output_class")
        outer.addWidget(self.summary_output, 1)

    def _set_combo_items(self, combo: QComboBox, items: list[tuple[str, str]]) -> None:
        current_value = str(combo.currentData() or combo.currentText() or "")
        combo.blockSignals(True)
        combo.clear()
        for value, label in items:
            combo.addItem(label, value)
        index = combo.findData(current_value)
        combo.setCurrentIndex(max(0, index))
        combo.blockSignals(False)

    def _strategy_value(self) -> str:
        return str(self.strategy_combo.currentData() or self.strategy_combo.currentText() or "auto")

    def _background_mode_value(self) -> str:
        return str(self.background_combo.currentData() or self.background_combo.currentText() or "transparent")

    def _preview_cache_key(self, path: str) -> str:
        try:
            stat = Path(path).stat()
            stamp = f"{stat.st_mtime_ns}:{stat.st_size}"
        except Exception:
            stamp = "missing"
        return f"{path}|{stamp}|{self._strategy_value()}"

    def _reset_preview_cache(self) -> None:
        self._preview_loading_key = ""
        self._preview_cached_key = ""
        self._preview_cached_image = None
        self._preview_cached_alpha = None

    def _handle_language_change(self) -> None:
        self._apply_texts()
        self._refresh_file_list()
        self._refresh_preview()

    def _apply_texts(self) -> None:
        self.title_label.setText(self._pt("title", "SMART Background Remover"))
        self.description_label.setText(
            self._pt(
                "description",
                "Remove image backgrounds with AI-assisted masking, edge-aware fallback passes, and flexible export styling.",
            )
        )
        self.strategy_label.setText(self._pt("label.strategy", "Strategy"))
        self.background_label.setText(self._pt("label.background", "Output Background"))
        self.crop_checkbox.setText(self._pt("option.crop", "Crop to subject"))
        self.files_label.setText(self._pt("label.files", "Files"))
        self.color_input.setPlaceholderText(self._pt("placeholder.color", "#ffffff"))
        self._set_combo_items(
            self.strategy_combo,
            [
                ("auto", self._pt("strategy.auto", "Auto Smart")),
                ("edge", self._pt("strategy.edge", "Edge Sweep")),
                ("backdrop", self._pt("strategy.backdrop", "Backdrop Key")),
            ],
        )
        self._set_combo_items(
            self.background_combo,
            [
                ("transparent", self._pt("background.transparent", "Transparent PNG")),
                ("white", self._pt("background.white", "Solid White")),
                ("black", self._pt("background.black", "Solid Black")),
                ("custom", self._pt("background.custom", "Custom Color")),
            ],
        )
        self.add_button.setText(self._pt("add", "Add Images"))
        self.clear_button.setText(self._pt("clear", "Clear All"))
        self.file_list.set_remove_action_text(self._pt("list.remove", "Remove from list"))
        self.run_button.setText(self._pt("run", "Run SMART Cutout"))
        self.summary_output.setPlaceholderText(self._pt("summary.placeholder", "SMART background-removal activity will appear here."))
        if not self.preview_label.pixmap():
            self.preview_label.setText(self._pt("preview.empty", "Select an image to preview the cutout."))
        self._handle_background_mode_change()
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        palette = self.services.theme_manager.current_palette()
        apply_page_chrome(
            palette,
            title_label=self.title_label,
            description_label=self.description_label,
            cards=(self.settings_card,),
            title_size=26,
            title_weight=700,
            card_radius=14,
        )

    def _handle_theme_change(self, _mode: str) -> None:
        self._apply_theme_styles()

    def _handle_background_mode_change(self) -> None:
        mode = self._background_mode_value()
        self.color_input.setVisible(mode == "custom")
        self._refresh_preview()

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            self._pt("dialog.select_images", "Select Images"),
            str(self.services.default_output_path()),
            SUPPORTED_IMAGE_FILTER,
        )
        if files:
            self._append_files(files)

    def _append_files(self, paths: list[str]) -> None:
        first_new_index: int | None = None
        for path in paths:
            if path not in self.files:
                if first_new_index is None:
                    first_new_index = len(self.files)
                self.files.append(path)
        self._refresh_file_list()
        if first_new_index is not None:
            self.file_list.setCurrentRow(first_new_index)
        elif self.files and self.file_list.currentRow() < 0:
            self.file_list.setCurrentRow(0)

    def _clear_files(self) -> None:
        self.files = []
        self._preview_timer.stop()
        self._reset_preview_cache()
        self.file_list.clear()
        self.preview_label.clear()
        self.preview_label.setToolTip("")
        self.preview_label.setText(self._pt("preview.empty", "Select an image to preview the cutout."))

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        self.file_list.addItems([os.path.basename(path) for path in self.files])

    def _handle_files_dropped(self, paths: list[str]) -> None:
        self._append_files(paths)

    def _remove_file_at(self, row: int) -> None:
        if row < 0 or row >= len(self.files):
            return
        del self.files[row]
        self._preview_timer.stop()
        self._reset_preview_cache()
        self._refresh_file_list()
        if not self.files:
            self.preview_label.clear()
            self.preview_label.setToolTip("")
            self.preview_label.setText(self._pt("preview.empty", "Select an image to preview the cutout."))
            return
        self.file_list.setCurrentRow(min(row, len(self.files) - 1))

    def _show_preview_for_row(self, row: int) -> None:
        if row < 0 or row >= len(self.files):
            return
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            return
        path = self.files[row]
        cache_key = self._preview_cache_key(path)
        if (
            cache_key == self._preview_cached_key
            and self._preview_cached_image is not None
            and self._preview_cached_alpha is not None
        ):
            self._apply_cached_preview()
            return
        if cache_key == self._preview_loading_key:
            return
        self.preview_label.clear()
        self.preview_label.setToolTip(
            self._pt(
                "preview.safe_mode",
                "Preview uses a reduced, non-AI cutout to keep the app responsive.",
            )
        )
        self.preview_label.setText(self._pt("preview.loading", "Building preview..."))
        self._preview_timer.start()

    def _start_preview_refresh(self) -> None:
        row = self.file_list.currentRow()
        if row < 0 or row >= len(self.files):
            return
        path = self.files[row]
        cache_key = self._preview_cache_key(path)
        if (
            cache_key == self._preview_cached_key
            and self._preview_cached_image is not None
            and self._preview_cached_alpha is not None
        ):
            self._apply_cached_preview()
            return
        if cache_key == self._preview_loading_key:
            return

        self._preview_request_id += 1
        request_id = self._preview_request_id
        self._preview_loading_key = cache_key
        strategy = self._strategy_value()
        self.preview_label.clear()
        self.preview_label.setToolTip(
            self._pt(
                "preview.safe_mode",
                "Preview uses a reduced, non-AI cutout to keep the app responsive.",
            )
        )
        self.preview_label.setText(self._pt("preview.loading", "Building preview..."))
        self.services.run_task(
            lambda _context: build_preview_payload(path, strategy),
            on_result=lambda payload, rid=request_id, key=cache_key: self._handle_preview_result(rid, key, payload),
            on_error=lambda payload, rid=request_id, key=cache_key: self._handle_preview_error(rid, key, payload),
        )

    def _handle_preview_result(self, request_id: int, cache_key: str, payload: object) -> None:
        if request_id != self._preview_request_id:
            return
        result = dict(payload) if isinstance(payload, dict) else {}
        preview_image = result.get("preview_image")
        preview_alpha = result.get("preview_alpha")
        if not isinstance(preview_image, Image.Image) or not isinstance(preview_alpha, Image.Image):
            self._handle_preview_error(request_id, cache_key, {"message": "Preview payload was invalid."})
            return
        self._preview_loading_key = ""
        self._preview_cached_key = cache_key
        self._preview_cached_image = preview_image.copy()
        self._preview_cached_alpha = preview_alpha.copy()
        self._apply_cached_preview()

    def _handle_preview_error(self, request_id: int, cache_key: str, payload: object) -> None:
        if request_id != self._preview_request_id:
            return
        if self._preview_loading_key == cache_key:
            self._preview_loading_key = ""
        message = payload.get("message", "Preview failed.") if isinstance(payload, dict) else str(payload)
        self.preview_label.clear()
        self.preview_label.setToolTip("")
        self.preview_label.setText(self._pt("preview.error", "Preview error: {message}", message=str(message)))

    def _apply_cached_preview(self) -> None:
        if self._preview_cached_image is None or self._preview_cached_alpha is None:
            return
        try:
            result = _compose_background_result(
                self._preview_cached_image,
                self._preview_cached_alpha,
                background_mode=self._background_mode_value(),
                custom_color=self.color_input.text().strip(),
                crop_to_subject=self.crop_checkbox.isChecked(),
            )
            self.preview_label.setPixmap(pil_to_pixmap(result))
            self.preview_label.setText("")
            self.preview_label.setToolTip(
                self._pt(
                    "preview.safe_mode",
                    "Preview uses a reduced, non-AI cutout to keep the app responsive.",
                )
            )
        except Exception as exc:
            self.preview_label.clear()
            self.preview_label.setToolTip("")
            self.preview_label.setText(self._pt("preview.error", "Preview error: {message}", message=str(exc)))

    def _run(self) -> None:
        if not self.files:
            QMessageBox.warning(
                self,
                self._pt("error.missing_input.title", "Missing Input"),
                self._pt("error.missing_files", "Add at least one image first."),
            )
            return
        output_dir = QFileDialog.getExistingDirectory(
            self,
            self._pt("dialog.select_output", "Select Output Folder"),
            str(self.services.default_output_path()),
        )
        if not output_dir:
            return

        options = {
            "strategy": self._strategy_value(),
            "background_mode": self._background_mode_value(),
            "custom_color": self.color_input.text().strip(),
            "crop_to_subject": self.crop_checkbox.isChecked(),
        }

        self.run_button.setEnabled(False)
        self.summary_output.clear()
        self.services.run_task(
            lambda context: run_smart_background_task(context, list(self.files), output_dir, options, translate=self.tr),
            on_result=self._handle_result,
            on_error=self._handle_error,
            on_finished=self._finish_run,
        )

    def _handle_result(self, payload: object) -> None:
        result = dict(payload)
        skipped_lines = "\n".join(f"- {entry}" for entry in result.get("skipped", []))
        summary = self._pt(
            "summary.done",
            "SMART background removal complete.\nFiles written: {count}\nSkipped: {skipped}\nOutput folder: {output_dir}",
            count=result["count"],
            skipped=result["skipped_count"],
            output_dir=result["output_dir"],
        )
        if skipped_lines:
            summary = f"{summary}\n\n{self._pt('summary.skipped', 'Skipped files:')}\n{skipped_lines}"
        self.summary_output.setPlainText(summary)
        self.services.record_run(
            self.plugin_id,
            "SUCCESS",
            self._pt("run.success", "Generated {count} cutout images", count=result["count"]),
        )

    def _handle_error(self, payload: object) -> None:
        message = payload.get("message", self._pt("error.unknown", "Unknown SMART background-removal error")) if isinstance(payload, dict) else str(payload)
        self.summary_output.setPlainText(message)
        self.services.record_run(self.plugin_id, "ERROR", message[:500])
        self.services.log(self._pt("log.failed", "SMART background removal failed."), "ERROR")

    def _finish_run(self) -> None:
        self.run_button.setEnabled(True)
