from __future__ import annotations

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QAbstractScrollArea, QComboBox, QSlider, QWidget


def width_breakpoint(width: int, *, compact_max: int = 900, medium_max: int = 1280) -> str:
    current_width = max(0, int(width))
    if current_width < compact_max:
        return "compact"
    if current_width < medium_max:
        return "medium"
    return "wide"


def adaptive_columns(
    available_width: int,
    *,
    item_width: int,
    spacing: int = 0,
    max_columns: int,
    min_columns: int = 1,
) -> int:
    width = max(0, int(available_width))
    unit = max(1, int(item_width))
    gap = max(0, int(spacing))
    upper = max(1, int(max_columns))
    lower = max(1, min(int(min_columns), upper))
    for columns in range(upper, lower - 1, -1):
        required = (unit * columns) + (gap * max(0, columns - 1))
        if width >= required:
            return columns
    return lower


def adaptive_grid_columns(
    available_width: int,
    *,
    item_widths: list[int] | tuple[int, ...],
    spacing: int = 0,
    min_columns: int = 1,
) -> int:
    width = max(0, int(available_width))
    widths = [max(1, int(item_width)) for item_width in item_widths]
    if not widths:
        return 1
    upper = len(widths)
    lower = max(1, min(int(min_columns), upper))
    gap = max(0, int(spacing))
    for columns in range(upper, lower - 1, -1):
        column_widths = [0] * columns
        for index, item_width in enumerate(widths):
            column = index % columns
            column_widths[column] = max(column_widths[column], item_width)
        required = sum(column_widths) + (gap * max(0, columns - 1))
        if width >= required:
            return columns
    return lower


def _wheel_forward_target(widget: QWidget) -> QWidget | None:
    parent = widget.parentWidget()
    fallback = parent
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            viewport = parent.viewport()
            if viewport is not None:
                return viewport
        fallback = parent
        parent = parent.parentWidget()
    return fallback


def visible_parent_width(widget: QWidget) -> int:
    width = widget.contentsRect().width() or widget.width()
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractScrollArea):
            viewport = parent.viewport()
            if viewport is not None:
                return min(width, viewport.contentsRect().width() or viewport.width())
            return width
        parent = parent.parentWidget()
    return width


class ScrollSafeComboBox(QComboBox):
    def wheelEvent(self, event) -> None:
        if self.view().isVisible():
            super().wheelEvent(event)
            return

        target = _wheel_forward_target(self)
        event.ignore()
        if target is not None:
            QCoreApplication.sendEvent(target, event.clone())


class ScrollSafeSlider(QSlider):
    def wheelEvent(self, event) -> None:
        if self.isSliderDown():
            super().wheelEvent(event)
            return

        target = _wheel_forward_target(self)
        event.ignore()
        if target is not None:
            QCoreApplication.sendEvent(target, event.clone())
