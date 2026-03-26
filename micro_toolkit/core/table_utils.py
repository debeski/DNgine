from __future__ import annotations

from collections.abc import Mapping

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QHeaderView, QTableView, QTableWidget


class _InitialTableFitFilter(QObject):
    def __init__(
        self,
        table: QTableView | QTableWidget,
        *,
        column_count: int,
        stretch_columns: set[int],
        resize_to_contents_columns: set[int],
        default_widths: Mapping[int, int],
        minimum_section_size: int,
    ) -> None:
        super().__init__(table)
        self._table = table
        self._column_count = column_count
        self._stretch_columns = set(stretch_columns)
        self._resize_to_contents_columns = set(resize_to_contents_columns)
        self._default_widths = dict(default_widths)
        self._minimum_section_size = minimum_section_size

    def eventFilter(self, watched, event) -> bool:
        if watched is self._table and event.type() in {
            QEvent.Type.Show,
            QEvent.Type.ShowToParent,
            QEvent.Type.Resize,
            QEvent.Type.LayoutRequest,
            QEvent.Type.Polish,
            QEvent.Type.PolishRequest,
        }:
            if bool(self._table.property("_micro_initial_table_fit_pending")):
                _queue_fit_attempts(
                    self._table,
                    column_count=self._column_count,
                    stretch_columns=self._stretch_columns,
                    resize_to_contents_columns=self._resize_to_contents_columns,
                    default_widths=self._default_widths,
                    minimum_section_size=self._minimum_section_size,
                )
        return super().eventFilter(watched, event)

    def _trigger_fit(self) -> None:
        _fit_table_columns_once(
            self._table,
            column_count=self._column_count,
            stretch_columns=self._stretch_columns,
            resize_to_contents_columns=self._resize_to_contents_columns,
            default_widths=self._default_widths,
            minimum_section_size=self._minimum_section_size,
        )


def configure_resizable_table(
    table: QTableView | QTableWidget,
    *,
    stretch_columns: set[int] | None = None,
    resize_to_contents_columns: set[int] | None = None,
    default_widths: Mapping[int, int] | None = None,
    minimum_section_size: int = 44,
) -> None:
    header = table.horizontalHeader()
    stretch_columns = stretch_columns or set()
    resize_to_contents_columns = resize_to_contents_columns or set()
    default_widths = default_widths or {}
    try:
        column_count = int(table.model().columnCount()) if table.model() is not None else 0
    except Exception:
        column_count = 0

    header.setSectionsMovable(False)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(minimum_section_size)
    header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

    for column in resize_to_contents_columns:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)

    for column in stretch_columns:
        header.setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

    for column, width in default_widths.items():
        try:
            table.setColumnWidth(int(column), int(width))
        except Exception:
            continue

    if column_count > 0:
        table.setProperty("_micro_initial_table_fit_pending", True)
        if table.property("_micro_initial_table_fit_filter") is None:
            fit_filter = _InitialTableFitFilter(
                table,
                column_count=column_count,
                stretch_columns=stretch_columns,
                resize_to_contents_columns=resize_to_contents_columns,
                default_widths=default_widths,
                minimum_section_size=minimum_section_size,
            )
            table.setProperty("_micro_initial_table_fit_filter", fit_filter)
            table.installEventFilter(fit_filter)
        QTimer.singleShot(
            0,
            lambda tbl=table,
            cols=column_count,
            stretch=set(stretch_columns),
            sized=set(resize_to_contents_columns),
            widths=dict(default_widths),
            minimum=minimum_section_size: _queue_fit_attempts(
                tbl,
                column_count=cols,
                stretch_columns=stretch,
                resize_to_contents_columns=sized,
                default_widths=widths,
                minimum_section_size=minimum,
            ),
        )


def _queue_fit_attempts(
    table: QTableView | QTableWidget,
    *,
    column_count: int,
    stretch_columns: set[int],
    resize_to_contents_columns: set[int],
    default_widths: Mapping[int, int],
    minimum_section_size: int,
) -> None:
    for delay in (0, 40, 140, 320):
        QTimer.singleShot(
            delay,
            lambda tbl=table,
            cols=column_count,
            stretch=set(stretch_columns),
            sized=set(resize_to_contents_columns),
            widths=dict(default_widths),
            minimum=minimum_section_size: _fit_table_columns_once(
                tbl,
                column_count=cols,
                stretch_columns=stretch,
                resize_to_contents_columns=sized,
                default_widths=widths,
                minimum_section_size=minimum,
            ),
        )


def _fit_table_columns_once(
    table: QTableView | QTableWidget,
    *,
    column_count: int,
    stretch_columns: set[int],
    resize_to_contents_columns: set[int],
    default_widths: Mapping[int, int],
    minimum_section_size: int,
) -> None:
    if not bool(table.property("_micro_initial_table_fit_pending")):
        return
    if not table.isVisible():
        return

    header = table.horizontalHeader()
    viewport_width = max(0, table.viewport().width())
    if viewport_width <= 0:
        QTimer.singleShot(
            30,
            lambda tbl=table,
            cols=column_count,
            stretch=set(stretch_columns),
            sized=set(resize_to_contents_columns),
            widths=dict(default_widths),
            minimum=minimum_section_size: _fit_table_columns_once(
                tbl,
                column_count=cols,
                stretch_columns=stretch,
                resize_to_contents_columns=sized,
                default_widths=widths,
                minimum_section_size=minimum,
            ),
        )
        return
    table.setProperty("_micro_initial_table_fit_pending", False)

    try:
        table.resizeColumnsToContents()
    except Exception:
        pass

    fixed_columns: set[int] = set()
    occupied_width = 0

    for column in range(column_count):
        if column in resize_to_contents_columns:
            fixed_columns.add(column)
            occupied_width += max(minimum_section_size, header.sectionSize(column))
            continue
        if stretch_columns and column not in stretch_columns:
            fixed_columns.add(column)
            if column in default_widths:
                table.setColumnWidth(column, max(minimum_section_size, int(default_widths[column])))
            occupied_width += max(minimum_section_size, header.sectionSize(column))

    flexible_columns = [column for column in range(column_count) if column not in fixed_columns]
    if not flexible_columns:
        return

    available_width = max(minimum_section_size * len(flexible_columns), viewport_width - occupied_width - 4)
    weight_map = {column: max(1, int(default_widths.get(column, 1))) for column in flexible_columns}
    total_weight = max(1, sum(weight_map.values()))

    assigned = 0
    for index, column in enumerate(flexible_columns):
        if index == len(flexible_columns) - 1:
            width = max(minimum_section_size, available_width - assigned)
        else:
            width = max(minimum_section_size, int(round(available_width * weight_map[column] / total_weight)))
            assigned += width
        table.setColumnWidth(column, width)
