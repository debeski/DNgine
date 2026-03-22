from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QColor, QIcon, QPalette
from PySide6.QtWidgets import QStyle, QWidget

try:
    import qtawesome as qta
except Exception:  # pragma: no cover - optional dependency
    qta = None


@dataclass(frozen=True)
class IconChoice:
    key: str
    label: str
    fallback: QStyle.StandardPixmap
    qtawesome_name: str | None = None


ICON_CHOICES: tuple[IconChoice, ...] = (
    IconChoice("desktop", "Desktop", QStyle.StandardPixmap.SP_DesktopIcon, "fa5s.desktop"),
    IconChoice("dashboard", "Dashboard", QStyle.StandardPixmap.SP_DesktopIcon, "fa5s.tachometer-alt"),
    IconChoice("home", "Home", QStyle.StandardPixmap.SP_DirHomeIcon, "fa5s.home"),
    IconChoice("computer", "Computer", QStyle.StandardPixmap.SP_ComputerIcon, "fa5s.laptop"),
    IconChoice("folder", "Folder", QStyle.StandardPixmap.SP_DirIcon, "fa5s.folder"),
    IconChoice("folder-open", "Open Folder", QStyle.StandardPixmap.SP_DirOpenIcon, "fa5s.folder-open"),
    IconChoice("file", "File", QStyle.StandardPixmap.SP_FileIcon, "fa5s.file"),
    IconChoice("search", "Search", QStyle.StandardPixmap.SP_FileDialogContentsView, "fa5s.search"),
    IconChoice("settings", "Settings", QStyle.StandardPixmap.SP_FileDialogDetailedView, "fa5s.cog"),
    IconChoice("tools", "Tools", QStyle.StandardPixmap.SP_DialogApplyButton, "fa5s.tools"),
    IconChoice("wrench", "Wrench", QStyle.StandardPixmap.SP_DialogApplyButton, "fa5s.wrench"),
    IconChoice("clipboard", "Clipboard", QStyle.StandardPixmap.SP_FileDialogContentsView, "fa5s.clipboard"),
    IconChoice("workflow", "Workflow", QStyle.StandardPixmap.SP_BrowserReload, "fa5s.project-diagram"),
    IconChoice("analytics", "Analytics", QStyle.StandardPixmap.SP_DialogApplyButton, "fa5s.chart-bar"),
    IconChoice("chart-line", "Line Chart", QStyle.StandardPixmap.SP_DialogApplyButton, "fa5s.chart-line"),
    IconChoice("office", "Office", QStyle.StandardPixmap.SP_FileDialogListView, "fa5s.briefcase"),
    IconChoice("media", "Media", QStyle.StandardPixmap.SP_MediaPlay, "fa5s.image"),
    IconChoice("image", "Image", QStyle.StandardPixmap.SP_FileIcon, "fa5s.image"),
    IconChoice("camera", "Camera", QStyle.StandardPixmap.SP_FileIcon, "fa5s.camera"),
    IconChoice("tag", "Tag", QStyle.StandardPixmap.SP_FileIcon, "fa5s.tag"),
    IconChoice("network", "Network", QStyle.StandardPixmap.SP_ComputerIcon, "fa5s.network-wired"),
    IconChoice("shield", "Shield", QStyle.StandardPixmap.SP_MessageBoxWarning, "fa5s.shield-alt"),
    IconChoice("lock", "Lock", QStyle.StandardPixmap.SP_MessageBoxWarning, "fa5s.lock"),
    IconChoice("terminal", "Terminal", QStyle.StandardPixmap.SP_ComputerIcon, "fa5s.code"),
    IconChoice("plugin", "Plugin", QStyle.StandardPixmap.SP_FileIcon, "fa5s.plug"),
    IconChoice("puzzle", "Puzzle", QStyle.StandardPixmap.SP_FileIcon, "fa5s.puzzle-piece"),
    IconChoice("code", "Code", QStyle.StandardPixmap.SP_FileIcon, "fa5s.code"),
    IconChoice("database", "Database", QStyle.StandardPixmap.SP_DriveHDIcon, "fa5s.database"),
    IconChoice("save", "Save", QStyle.StandardPixmap.SP_DialogSaveButton, "fa5s.save"),
    IconChoice("open", "Open", QStyle.StandardPixmap.SP_DialogOpenButton, "fa5s.folder-open"),
    IconChoice("download", "Download", QStyle.StandardPixmap.SP_ArrowDown, "fa5s.download"),
    IconChoice("upload", "Upload", QStyle.StandardPixmap.SP_ArrowUp, "fa5s.upload"),
    IconChoice("sync", "Sync", QStyle.StandardPixmap.SP_BrowserReload, "fa5s.sync-alt"),
    IconChoice("repeat", "Repeat", QStyle.StandardPixmap.SP_BrowserReload, "fa5s.redo-alt"),
    IconChoice("check", "Check", QStyle.StandardPixmap.SP_DialogApplyButton, "fa5s.check-circle"),
    IconChoice("info", "Info", QStyle.StandardPixmap.SP_FileDialogInfoView, "fa5s.info-circle"),
    IconChoice("warning", "Warning", QStyle.StandardPixmap.SP_MessageBoxWarning, "fa5s.exclamation-triangle"),
    IconChoice("bolt", "Bolt", QStyle.StandardPixmap.SP_CommandLink, "fa5s.bolt"),
    IconChoice("sun", "Sun", QStyle.StandardPixmap.SP_DialogYesButton, "fa5s.sun"),
    IconChoice("moon", "Moon", QStyle.StandardPixmap.SP_DialogNoButton, "fa5s.moon"),
    IconChoice("language", "Language", QStyle.StandardPixmap.SP_FileDialogDetailedView, "fa5s.language"),
    IconChoice("keyboard", "Keyboard", QStyle.StandardPixmap.SP_ComputerIcon, "fa5s.keyboard"),
    IconChoice("globe", "Globe", QStyle.StandardPixmap.SP_DriveNetIcon, "fa5s.globe"),
    IconChoice("github", "GitHub", QStyle.StandardPixmap.SP_FileDialogInfoView, "fa5b.github"),
    IconChoice("book", "Book", QStyle.StandardPixmap.SP_FileDialogInfoView, "fa5s.book"),
    IconChoice("print", "Print", QStyle.StandardPixmap.SP_DialogSaveButton, "fa5s.print"),
    IconChoice("rocket", "Rocket", QStyle.StandardPixmap.SP_ArrowUp, "fa5s.rocket"),
)

ICON_MAP = {choice.key: choice for choice in ICON_CHOICES}


def icon_choices(widget: QWidget) -> list[tuple[str, str, QIcon]]:
    return [(choice.key, choice.label, icon_from_name(choice.key, widget) or QIcon()) for choice in ICON_CHOICES]


def icon_from_name(icon_name: str, widget: QWidget) -> QIcon | None:
    key = str(icon_name or "").strip()
    if not key:
        return None

    choice = ICON_MAP.get(key.lower())
    if choice is not None:
        icon = _qtawesome_icon(choice.qtawesome_name, widget)
        if icon is not None:
            return icon
        return widget.style().standardIcon(choice.fallback)

    icon = _qtawesome_icon(key, widget)
    if icon is not None:
        return icon
    return None


def qtawesome_available() -> bool:
    return qta is not None


def _qtawesome_icon(name: str | None, widget: QWidget) -> QIcon | None:
    if qta is None or not name:
        return None
    try:
        color = _solid_color(widget.palette().color(QPalette.ColorRole.WindowText), fallback="#16313d")
        disabled = _solid_color(widget.palette().color(QPalette.ColorRole.Mid), fallback="#70838d")
        color_hex = color.name(QColor.NameFormat.HexRgb)
        disabled_hex = disabled.name(QColor.NameFormat.HexRgb)
        return qta.icon(
            name,
            color=color_hex,
            color_active=color_hex,
            color_selected=color_hex,
            color_disabled=disabled_hex,
            color_on=color_hex,
            color_off=color_hex,
            color_on_active=color_hex,
            color_off_active=color_hex,
            color_on_selected=color_hex,
            color_off_selected=color_hex,
            color_on_disabled=disabled_hex,
            color_off_disabled=disabled_hex,
        )
    except Exception:
        return None


def _solid_color(color: QColor, *, fallback: str) -> QColor:
    if not color.isValid():
        color = QColor(fallback)
    elif color.alpha() < 255:
        color = QColor(color)
        color.setAlpha(255)
    return color
