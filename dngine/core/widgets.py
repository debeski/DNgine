from __future__ import annotations

from pathlib import Path

from PySide6.QtCharts import QChart, QChartView, QPieSeries
from PySide6.QtCore import QCoreApplication, QMargins, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractScrollArea,
    QComboBox,
    QLineEdit,
    QListWidget,
    QSizePolicy,
    QSlider,
    QTableWidget,
    QVBoxLayout,
    QLabel,
    QFrame,
    QWidget,
)

from dngine.core.context_menus import MenuActionSpec, attach_list_context_menu


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


class PathLineEdit(QLineEdit):
    path_dropped = Signal(str)

    def __init__(self, parent: QWidget | None = None, *, mode: str = "any", allowed_extensions: list[str] | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._mode = mode
        self.set_allowed_extensions(allowed_extensions)

    def set_allowed_extensions(self, extensions: list[str] | None) -> None:
        self._allowed_extensions = {ext.lower().lstrip('.') for ext in extensions} if extensions else None

    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def _is_valid_url(self, url) -> bool:
        if not self._allowed_extensions:
            return True
        local_path = url.toLocalFile()
        if not local_path:
            return False
        path = Path(local_path)
        if path.is_file():
            ext = path.suffix.lower().lstrip('.')
            return ext in self._allowed_extensions
        return True

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(self._is_valid_url(u) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(self._is_valid_url(u) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return
            
        valid_urls = [u for u in event.mimeData().urls() if self._is_valid_url(u)]
        if not valid_urls:
            super().dropEvent(event)
            return
            
        for url in valid_urls:
            local_path = url.toLocalFile()
            if not local_path:
                continue
            path = Path(local_path)
            if self._mode == "directory":
                chosen = path if path.is_dir() else path.parent
            elif self._mode == "file":
                chosen = path if path.is_file() else path
            else:
                chosen = path
            self.setText(str(chosen))
            self.path_dropped.emit(str(chosen))
            event.acceptProposedAction()
            return

class DroppableListWidget(QListWidget):
    files_dropped = Signal(list)
    remove_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None, *, mode: str = "any", allowed_extensions: list[str] | None = None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._mode = mode
        self.set_allowed_extensions(allowed_extensions)
        self._remove_action_text = "Remove from list"
        attach_list_context_menu(self, self._context_menu_items)
        
    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def set_allowed_extensions(self, extensions: list[str] | None) -> None:
        self._allowed_extensions = {ext.lower().lstrip('.') for ext in extensions} if extensions else None

    def set_remove_action_text(self, text: str) -> None:
        self._remove_action_text = str(text or "").strip() or "Remove from list"

    def _context_menu_items(self, row: int) -> list[MenuActionSpec]:
        return [
            MenuActionSpec(
                label=self._remove_action_text,
                callback=lambda: self.remove_requested.emit(row),
            )
        ]

    def _is_valid_url(self, url) -> bool:
        if not self._allowed_extensions:
            return True
        local_path = url.toLocalFile()
        if not local_path:
            return False
        path = Path(local_path)
        if path.is_file():
            ext = path.suffix.lower().lstrip('.')
            return ext in self._allowed_extensions
        return True

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(self._is_valid_url(u) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(self._is_valid_url(u) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        valid_urls = [u for u in event.mimeData().urls() if self._is_valid_url(u)]
        if not valid_urls:
            super().dropEvent(event)
            return

        paths = []
        for url in valid_urls:
            local_path = url.toLocalFile()
            if not local_path:
                continue
            path = Path(local_path)
            if self._mode == "directory":
                chosen = path if path.is_dir() else path.parent
            elif self._mode == "file":
                chosen = path if path.is_file() else path
            else:
                chosen = path
            
            str_path = str(chosen)
            if str_path not in paths:
                paths.append(str_path)

        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        super().dropEvent(event)

class DroppableTableWidget(QTableWidget):
    files_dropped = Signal(list)

    def __init__(self, rows: int = 0, columns: int = 0, parent: QWidget | None = None, *, mode: str = "any", allowed_extensions: list[str] | None = None):
        super().__init__(rows, columns, parent)
        self.setAcceptDrops(True)
        self._mode = mode
        self.set_allowed_extensions(allowed_extensions)
        
    def set_mode(self, mode: str) -> None:
        self._mode = mode

    def set_allowed_extensions(self, extensions: list[str] | None) -> None:
        self._allowed_extensions = {ext.lower().lstrip('.') for ext in extensions} if extensions else None

    def _is_valid_url(self, url) -> bool:
        if not self._allowed_extensions:
            return True
        local_path = url.toLocalFile()
        if not local_path:
            return False
        path = Path(local_path)
        if path.is_file():
            ext = path.suffix.lower().lstrip('.')
            return ext in self._allowed_extensions
        return True

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(self._is_valid_url(u) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            if any(self._is_valid_url(u) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if not event.mimeData().hasUrls():
            super().dropEvent(event)
            return

        valid_urls = [u for u in event.mimeData().urls() if self._is_valid_url(u)]
        if not valid_urls:
            super().dropEvent(event)
            return

        paths = []
        for url in valid_urls:
            local_path = url.toLocalFile()
            if not local_path:
                continue
            path = Path(local_path)
            if self._mode == "directory":
                chosen = path if path.is_dir() else path.parent
            elif self._mode == "file":
                chosen = path if path.is_file() else path
            else:
                chosen = path
            
            str_path = str(chosen)
            if str_path not in paths:
                paths.append(str_path)

        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()

        super().dropEvent(event)


class MetricDonutWidget(QFrame):
    def __init__(self, title: str):
        super().__init__()
        self._title = title
        self.title_label = QLabel(title)
        self.value_label = QLabel("--")
        self.caption_label = QLabel("")
        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.chart_view.setFixedHeight(122)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(240)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(6)
        layout.addWidget(self.title_label)
        layout.addWidget(self.chart_view, 0, Qt.AlignmentFlag.AlignCenter)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.value_label)
        self.caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption_label.setWordWrap(True)
        layout.addWidget(self.caption_label)
        layout.addStretch(1)

    def set_title(self, title: str) -> None:
        self._title = title
        self.title_label.setText(title)

    def set_metric(self, percent: float, caption: str, accent: str, remainder: str) -> None:
        percent = max(0.0, min(100.0, float(percent)))
        self.value_label.setText(f"{percent:.0f}%")
        self.caption_label.setText(caption)
        self.chart_view.setChart(self._build_chart(percent, accent, remainder))

    def _build_chart(self, percent: float, accent: str, remainder: str) -> QChart:
        series = QPieSeries()
        series.setHoleSize(0.68)
        used = series.append(self._title, percent)
        free = series.append("Remaining", max(0.0, 100.0 - percent))
        used.setColor(QColor(accent))
        used.setBorderColor(QColor(accent))
        free.setColor(QColor(remainder))
        free.setBorderColor(QColor(remainder))
        used.setLabelVisible(False)
        free.setLabelVisible(False)

        chart = QChart()
        chart.addSeries(series)
        chart.legend().hide()
        chart.setBackgroundVisible(False)
        chart.setMargins(QMargins(0, 0, 0, 0))
        return chart


class InfoCardWidget(QFrame):
    def __init__(self, title: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(8)
        self.title_label = QLabel(title)
        self.body_label = QLabel("")
        self.body_label.setWordWrap(True)
        layout.addWidget(self.title_label)
        layout.addWidget(self.body_label)
        layout.addStretch(1)

    def set_rows(self, rows: list[tuple[str, object]]) -> None:
        if not rows:
            self.body_label.setText("")
            return
        self.body_label.setText("\n".join(f"{label}: {value}" for label, value in rows))
