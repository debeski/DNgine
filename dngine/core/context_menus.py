from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QListWidget, QMenu, QTableView, QTableWidget, QWidget


@dataclass(frozen=True)
class MenuActionSpec:
    label: str = ""
    callback: Callable[[], None] | None = None
    enabled: bool = True
    separator: bool = False


def show_context_menu(
    parent: QWidget | None,
    global_position: QPoint,
    items: list[MenuActionSpec] | tuple[MenuActionSpec, ...],
) -> QAction | None:
    menu = QMenu(parent)
    chosen_action: QAction | None = None
    callbacks: dict[QAction, Callable[[], None] | None] = {}

    for item in items:
        if item.separator:
            menu.addSeparator()
            continue
        action = menu.addAction(str(item.label))
        action.setEnabled(bool(item.enabled))
        callbacks[action] = item.callback

    chosen_action = menu.exec(global_position)
    if chosen_action is None:
        return None
    callback = callbacks.get(chosen_action)
    if callback is not None:
        callback()
    return chosen_action


def attach_list_context_menu(
    list_widget: QListWidget,
    action_builder: Callable[[int], list[MenuActionSpec] | tuple[MenuActionSpec, ...]],
) -> None:
    def _show(position: QPoint) -> None:
        item = list_widget.itemAt(position)
        if item is None:
            return
        row = list_widget.row(item)
        if row < 0:
            return
        items = list(action_builder(row) or [])
        if not items:
            return
        show_context_menu(list_widget, list_widget.viewport().mapToGlobal(position), items)

    list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    list_widget.customContextMenuRequested.connect(_show)


def attach_table_context_menu(
    table_widget: QTableWidget | QTableView,
    action_builder: Callable[[int], list[MenuActionSpec] | tuple[MenuActionSpec, ...]],
) -> None:
    def _show(position: QPoint) -> None:
        if isinstance(table_widget, QTableWidget):
            item = table_widget.itemAt(position)
            row = item.row() if item is not None else table_widget.currentRow()
        else:
            index = table_widget.indexAt(position)
            row = index.row() if index.isValid() else -1
        if row < 0:
            return
        items = list(action_builder(row) or [])
        if not items:
            return
        show_context_menu(table_widget, table_widget.viewport().mapToGlobal(position), items)

    table_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    table_widget.customContextMenuRequested.connect(_show)
