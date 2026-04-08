from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QBoxLayout, QFormLayout, QWidget


RTL_LANGUAGES = {"ar", "fa", "he", "ur"}


def _apply_layout_direction(layout, direction: Qt.LayoutDirection) -> None:
    rtl = direction == Qt.LayoutDirection.RightToLeft
    if isinstance(layout, QFormLayout):
        horizontal_alignment = (
            Qt.AlignmentFlag.AlignRight if rtl else Qt.AlignmentFlag.AlignLeft
        )
        layout.setLabelAlignment(horizontal_alignment | Qt.AlignmentFlag.AlignVCenter)
        layout.setFormAlignment(horizontal_alignment | Qt.AlignmentFlag.AlignTop)
    elif isinstance(layout, QBoxLayout):
        current_direction = layout.direction()
        if current_direction in {
            QBoxLayout.Direction.LeftToRight,
            QBoxLayout.Direction.RightToLeft,
        }:
            layout.setDirection(
                QBoxLayout.Direction.RightToLeft if rtl else QBoxLayout.Direction.LeftToRight
            )
    layout.invalidate()
    for index in range(layout.count()):
        child_layout = layout.itemAt(index).layout()
        if child_layout is not None:
            _apply_layout_direction(child_layout, direction)
    layout.activate()


def apply_widget_direction(widget: QWidget | None, direction: Qt.LayoutDirection) -> Qt.LayoutDirection:
    if widget is None:
        return direction
    widget.setLayoutDirection(direction)
    layout = widget.layout()
    if layout is not None:
        _apply_layout_direction(layout, direction)
    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        apply_widget_direction(child, direction)
    widget.updateGeometry()
    widget.update()
    return direction


class TranslationManager(QObject):
    language_changed = Signal(str)
    direction_changed = Signal(object)

    def __init__(self, config, locales_root: Path):
        super().__init__()
        self.config = config
        self.locales_root = Path(locales_root)
        self._catalogs = self._load_catalogs()
        configured = str(self.config.get("language") or "en").strip().lower()
        self._current_language = configured if configured in self._catalogs else "en"

    def available_languages(self) -> list[tuple[str, str]]:
        supported = []
        for code, data in sorted(self._catalogs.items()):
            supported.append((code, data.get("_meta", {}).get("label", code)))
        return supported or [("en", "English")]

    def current_language(self) -> str:
        return self._current_language

    def set_language(self, language: str) -> None:
        normalized = (language or "en").strip().lower()
        if normalized not in self._catalogs:
            normalized = "en"
        self._current_language = normalized
        app = QApplication.instance()
        if app is not None:
            app.setLayoutDirection(self.layout_direction())
        self.language_changed.emit(normalized)
        self.direction_changed.emit(self.layout_direction())

    def save_to_config(self) -> None:
        self.config.set("language", self._current_language)

    def load_from_config(self) -> str:
        configured = str(self.config.get("language") or "en").strip().lower()
        self._current_language = configured if configured in self._catalogs else "en"
        return self._current_language

    def tr(self, key: str, default: str | None = None, **kwargs) -> str:
        catalog = self._catalogs.get(self.current_language(), {})
        text = catalog.get(key)
        if text is None:
            text = self._catalogs.get("en", {}).get(key, default if default is not None else key)
        if kwargs:
            try:
                text = text.format(**kwargs)
            except Exception:
                pass
        return text

    def is_rtl(self) -> bool:
        return self.current_language() in RTL_LANGUAGES

    def layout_direction(self) -> Qt.LayoutDirection:
        return Qt.LayoutDirection.RightToLeft if self.is_rtl() else Qt.LayoutDirection.LeftToRight

    def apply(self, app) -> None:
        app.setLayoutDirection(self.layout_direction())
        self.language_changed.emit(self.current_language())
        self.direction_changed.emit(self.layout_direction())

    def _load_catalogs(self) -> dict[str, dict]:
        catalogs: dict[str, dict] = {}
        if not self.locales_root.exists():
            return {"en": {}}
        for file_path in sorted(self.locales_root.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(payload, dict):
                catalogs[file_path.stem.lower()] = payload
        return catalogs or {"en": {}}
