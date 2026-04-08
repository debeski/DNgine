from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget

from dngine.core.i18n import apply_widget_direction
from dngine.core.plugin_api import bind_tr, safe_tr, tr


def _pt(translate, key: str, default: str | None = None, **kwargs) -> str:
    return safe_tr(translate, key, default, **kwargs)


def current_language(services) -> str:
    return services.i18n.current_language()


def is_rtl(services) -> bool:
    return services.i18n.is_rtl()


def layout_direction(services) -> Qt.LayoutDirection:
    return services.i18n.layout_direction()


def apply_direction(widget: QWidget | None, services) -> Qt.LayoutDirection:
    direction = layout_direction(services)
    if widget is not None:
        apply_widget_direction(widget, direction)
    return direction
