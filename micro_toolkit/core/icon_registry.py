from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QStyle, QWidget

ASSETS_ROOT = Path(__file__).resolve().parents[1] / "assets" / "icons"


@dataclass(frozen=True)
class IconChoice:
    key: str
    label: str
    fallback: QStyle.StandardPixmap
    asset_path: str | None = None


ICON_CHOICES: tuple[IconChoice, ...] = (
    IconChoice("desktop", "Desktop", QStyle.StandardPixmap.SP_DesktopIcon, "window-stack.svg"),
    IconChoice("dashboard", "Dashboard", QStyle.StandardPixmap.SP_DesktopIcon, "speedometer2.svg"),
    IconChoice("home", "Home", QStyle.StandardPixmap.SP_DirHomeIcon, "house-fill.svg"),
    IconChoice("computer", "Computer", QStyle.StandardPixmap.SP_ComputerIcon, "laptop.svg"),
    IconChoice("folder", "Folder", QStyle.StandardPixmap.SP_DirIcon, "folder2.svg"),
    IconChoice("folder-open", "Open Folder", QStyle.StandardPixmap.SP_DirOpenIcon, "folder2-open.svg"),
    IconChoice("file", "File", QStyle.StandardPixmap.SP_FileIcon, "file-text.svg"),
    IconChoice("search", "Search", QStyle.StandardPixmap.SP_FileDialogContentsView, "search.svg"),
    IconChoice("settings", "Settings", QStyle.StandardPixmap.SP_FileDialogDetailedView, "gear.svg"),
    IconChoice("inspect", "Inspector", QStyle.StandardPixmap.SP_FileDialogDetailedView, "bug.svg"),
    IconChoice("tools", "Tools", QStyle.StandardPixmap.SP_DialogApplyButton, "tools.svg"),
    IconChoice("wrench", "Wrench", QStyle.StandardPixmap.SP_DialogApplyButton, "wrench.svg"),
    IconChoice("clipboard", "Clipboard", QStyle.StandardPixmap.SP_FileDialogContentsView, "clipboard/clipboard.svg"),
    IconChoice("workflow", "Workflow", QStyle.StandardPixmap.SP_BrowserReload, "diagram-3.svg"),
    IconChoice("analytics", "Analytics", QStyle.StandardPixmap.SP_DialogApplyButton, "bar-chart-line.svg"),
    IconChoice("chart-line", "Line Chart", QStyle.StandardPixmap.SP_DialogApplyButton, "graph-up.svg"),
    IconChoice("office", "Office", QStyle.StandardPixmap.SP_FileDialogListView, "collection.svg"),
    IconChoice("media", "Media", QStyle.StandardPixmap.SP_MediaPlay, "images.svg"),
    IconChoice("image", "Image", QStyle.StandardPixmap.SP_FileIcon, "image-fill.svg"),
    IconChoice("camera", "Camera", QStyle.StandardPixmap.SP_FileIcon, "media/camera.svg"),
    IconChoice("tag", "Tag", QStyle.StandardPixmap.SP_FileIcon, "tag.svg"),
    IconChoice("network", "Network", QStyle.StandardPixmap.SP_ComputerIcon, "wifi.svg"),
    IconChoice("shield", "Shield", QStyle.StandardPixmap.SP_MessageBoxWarning, "shield.svg"),
    IconChoice("lock", "Lock", QStyle.StandardPixmap.SP_MessageBoxWarning, "lock.svg"),
    IconChoice("terminal", "Terminal", QStyle.StandardPixmap.SP_ComputerIcon, "terminal.svg"),
    IconChoice("plugin", "Plugin", QStyle.StandardPixmap.SP_FileIcon, "plugin.svg"),
    IconChoice("puzzle", "Puzzle", QStyle.StandardPixmap.SP_FileIcon, "puzzle.svg"),
    IconChoice("code", "Code", QStyle.StandardPixmap.SP_FileIcon, "code-slash.svg"),
    IconChoice("database", "Database", QStyle.StandardPixmap.SP_DriveHDIcon, "database-fill.svg"),
    IconChoice("save", "Save", QStyle.StandardPixmap.SP_DialogSaveButton, "save.svg"),
    IconChoice("pin", "Pin", QStyle.StandardPixmap.SP_DialogApplyButton, "pin-angle.svg"),
    IconChoice("unpin", "Unpin", QStyle.StandardPixmap.SP_DialogCancelButton, "pin-angle-fill.svg"),
    IconChoice("open", "Open", QStyle.StandardPixmap.SP_DialogOpenButton, "folder2-open.svg"),
    IconChoice("download", "Download", QStyle.StandardPixmap.SP_ArrowDown, "download.svg"),
    IconChoice("upload", "Upload", QStyle.StandardPixmap.SP_ArrowUp, "upload.svg"),
    IconChoice("sync", "Sync", QStyle.StandardPixmap.SP_BrowserReload, "arrows/arrow-repeat.svg"),
    IconChoice("repeat", "Repeat", QStyle.StandardPixmap.SP_BrowserReload, "arrows/arrow-repeat.svg"),
    IconChoice("check", "Check", QStyle.StandardPixmap.SP_DialogApplyButton, "check-circle.svg"),
    IconChoice("info", "Info", QStyle.StandardPixmap.SP_FileDialogInfoView, "info-circle.svg"),
    IconChoice("warning", "Warning", QStyle.StandardPixmap.SP_MessageBoxWarning, "exclamation-circle.svg"),
    IconChoice("bolt", "Bolt", QStyle.StandardPixmap.SP_CommandLink, "lightning-charge.svg"),
    IconChoice("sun", "Sun", QStyle.StandardPixmap.SP_DialogYesButton, "brightness-alt-high.svg"),
    IconChoice("moon", "Moon", QStyle.StandardPixmap.SP_DialogNoButton, "moon-fill.svg"),
    IconChoice("language", "Language", QStyle.StandardPixmap.SP_FileDialogDetailedView, "translate.svg"),
    IconChoice("keyboard", "Keyboard", QStyle.StandardPixmap.SP_ComputerIcon, "command.svg"),
    IconChoice("globe", "Globe", QStyle.StandardPixmap.SP_DriveNetIcon, "globe-europe-africa.svg"),
    IconChoice("github", "GitHub", QStyle.StandardPixmap.SP_FileDialogInfoView, "link-45deg.svg"),
    IconChoice("book", "Book", QStyle.StandardPixmap.SP_FileDialogInfoView, "book.svg"),
    IconChoice("print", "Print", QStyle.StandardPixmap.SP_DialogSaveButton, "printer.svg"),
    IconChoice("rocket", "Rocket", QStyle.StandardPixmap.SP_ArrowUp, "rocket-takeoff.svg"),
    IconChoice("copy", "Copy", QStyle.StandardPixmap.SP_FileIcon, "copy.svg"),
    IconChoice("trash", "Trash", QStyle.StandardPixmap.SP_TrashIcon, "trash.svg"),
    IconChoice("activity", "Activity", QStyle.StandardPixmap.SP_FileDialogContentsView, "segmented-nav.svg"),
    IconChoice("eye", "Eye", QStyle.StandardPixmap.SP_FileDialogDetailedView, "eye.svg"),
    IconChoice("eye-slash", "Eye Slash", QStyle.StandardPixmap.SP_FileDialogDetailedView, "eye-slash.svg"),
)

ICON_MAP = {choice.key: choice for choice in ICON_CHOICES}


@lru_cache(maxsize=1)
def _svg_stem_index() -> dict[str, Path]:
    mapping: dict[str, Path] = {}
    for path in ASSETS_ROOT.rglob("*.svg"):
        stem = path.stem.lower()
        mapping.setdefault(stem, path)
    return mapping


def icon_choices(widget: QWidget) -> list[tuple[str, str, QIcon]]:
    return [(choice.key, choice.label, icon_from_name(choice.key, widget) or QIcon()) for choice in ICON_CHOICES]


def icon_from_name(icon_name: str, widget: QWidget) -> QIcon | None:
    key = str(icon_name or "").strip()
    if not key:
        return None

    choice = ICON_MAP.get(key.lower())
    if choice is not None:
        icon = _asset_icon(_resolve_asset_path(choice.asset_path), widget)
        if icon is not None:
            return icon
        return widget.style().standardIcon(choice.fallback)

    icon = _asset_icon(_resolve_asset_path(key), widget)
    if icon is not None:
        return icon
    return None


def qtawesome_available() -> bool:
    return False


def used_icon_asset_paths() -> list[Path]:
    seen: set[Path] = set()
    ordered: list[Path] = []
    for choice in ICON_CHOICES:
        path = _resolve_asset_path(choice.asset_path)
        if path is not None and path.exists() and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _resolve_asset_path(icon_name: str | None) -> Path | None:
    if not icon_name:
        return None
    candidate = Path(icon_name)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None
    direct = ASSETS_ROOT / candidate
    if direct.exists():
        return direct
    normalized = str(icon_name).strip().lower()
    if not normalized.endswith(".svg"):
        stem_match = _svg_stem_index().get(normalized)
        if stem_match is not None:
            return stem_match
        direct_svg = ASSETS_ROOT / f"{normalized}.svg"
        if direct_svg.exists():
            return direct_svg
    return None


def _asset_icon(path: Path | None, widget: QWidget) -> QIcon | None:
    if path is None or not path.exists():
        return None
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return None

    color = _theme_color(widget, "text_primary", fallback="#16313d")
    disabled = _theme_color(widget, "text_muted", fallback="#70838d")
    icon = QIcon()
    for size in (16, 18, 20, 22, 24, 28, 32, 36, 48):
        normal_pm = _render_svg_pixmap(renderer, size, color)
        disabled_pm = _render_svg_pixmap(renderer, size, disabled)
        if not normal_pm.isNull():
            icon.addPixmap(normal_pm, QIcon.Mode.Normal, QIcon.State.Off)
            icon.addPixmap(normal_pm, QIcon.Mode.Active, QIcon.State.Off)
            icon.addPixmap(normal_pm, QIcon.Mode.Selected, QIcon.State.Off)
        if not disabled_pm.isNull():
            icon.addPixmap(disabled_pm, QIcon.Mode.Disabled, QIcon.State.Off)
    return icon if not icon.isNull() else None


def _render_svg_pixmap(renderer: QSvgRenderer, size: int, color: QColor) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    if not painter.isActive():
        return QPixmap()
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    painter.fillRect(pixmap.rect(), color)
    painter.end()
    return pixmap


def _solid_color(color: QColor, *, fallback: str) -> QColor:
    if not color.isValid():
        color = QColor(fallback)
    elif color.alpha() < 255:
        color = QColor(color)
        color.setAlpha(255)
    return color


def _theme_color(widget: QWidget, role: str, *, fallback: str) -> QColor:
    current = widget
    while current is not None:
        services = getattr(current, "services", None)
        theme_manager = getattr(services, "theme_manager", None)
        if theme_manager is not None:
            try:
                value = getattr(theme_manager.current_palette(), role, fallback)
                return _solid_color(QColor(str(value)), fallback=fallback)
            except Exception:
                break
        current = current.parentWidget()
    return _solid_color(widget.palette().color(QPalette.ColorRole.WindowText), fallback=fallback)
