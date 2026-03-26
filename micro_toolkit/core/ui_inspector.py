from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QRect, QEvent, Signal, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QAbstractButton, QLabel, QTreeWidget, QWidget


@dataclass(frozen=True)
class InspectorSnapshot:
    class_name: str
    object_name: str
    window_title: str
    geometry: str
    global_geometry: str
    visible: bool
    enabled: bool
    stylesheet: str
    layout_margins: str
    dynamic_properties: dict[str, str]
    palette_roles: dict[str, str]
    parent_chain: list[str]
    child_count: int

    def to_payload(self) -> dict[str, object]:
        return {
            "class_name": self.class_name,
            "object_name": self.object_name,
            "window_title": self.window_title,
            "geometry": self.geometry,
            "global_geometry": self.global_geometry,
            "visible": self.visible,
            "enabled": self.enabled,
            "stylesheet": self.stylesheet,
            "layout_margins": self.layout_margins,
            "dynamic_properties": dict(self.dynamic_properties),
            "palette_roles": dict(self.palette_roles),
            "parent_chain": list(self.parent_chain),
            "child_count": self.child_count,
        }


class InspectorOverlay(QWidget):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._target_rect = QRect()
        self.hide()
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def set_target_rect(self, rect: QRect) -> None:
        self._target_rect = QRect(rect)
        self.setGeometry(self.parentWidget().rect())
        self.setVisible(not self._target_rect.isNull())
        self.raise_()
        self.update()

    def clear(self) -> None:
        self._target_rect = QRect()
        self.hide()
        self.update()

    def paintEvent(self, _event) -> None:
        if self._target_rect.isNull():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        fill = QColor(59, 167, 187, 38)
        border = QColor(59, 167, 187, 220)
        painter.fillRect(self._target_rect, fill)
        pen = QPen(border, 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(self._target_rect.adjusted(1, 1, -1, -1))
        painter.end()


class UIInspector(QObject):
    snapshot_changed = Signal(dict)
    inspect_mode_changed = Signal(bool)
    text_unlock_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._application: QApplication | None = None
        self._main_window: QWidget | None = None
        self._overlay: InspectorOverlay | None = None
        self._enabled = False
        self._inspect_mode = False
        self._text_unlock_enabled = False
        self._last_payload: dict[str, object] = {}

    def attach_application(self, application: QApplication) -> None:
        if self._application is application:
            return
        if self._application is not None:
            self._application.removeEventFilter(self)
        self._application = application
        self._application.installEventFilter(self)

    def attach_main_window(self, main_window: QWidget) -> None:
        self._main_window = main_window
        self._overlay = InspectorOverlay(main_window)

    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self.set_inspect_mode(False)
            self.set_text_unlock_enabled(False)

    def inspect_mode(self) -> bool:
        return self._inspect_mode

    def set_inspect_mode(self, enabled: bool) -> bool:
        target = bool(enabled) and self._enabled and self._application is not None and self._main_window is not None
        if self._inspect_mode == target:
            return self._inspect_mode
        self._inspect_mode = target
        if not target and self._overlay is not None:
            self._overlay.clear()
        self.inspect_mode_changed.emit(self._inspect_mode)
        return self._inspect_mode

    def toggle_inspect_mode(self) -> bool:
        return self.set_inspect_mode(not self._inspect_mode)

    def text_unlock_enabled(self) -> bool:
        return self._text_unlock_enabled

    def set_text_unlock_enabled(self, enabled: bool) -> bool:
        target = bool(enabled) and self._enabled and self._application is not None
        if self._text_unlock_enabled == target:
            return self._text_unlock_enabled
        self._text_unlock_enabled = target
        self._apply_text_unlock_to_all_widgets()
        self.text_unlock_changed.emit(self._text_unlock_enabled)
        return self._text_unlock_enabled

    def last_snapshot(self) -> dict[str, object]:
        return dict(self._last_payload)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if self._text_unlock_enabled:
            if event.type() == QEvent.Type.ChildAdded:
                child = getattr(event, "child", lambda: None)()
                if isinstance(child, QWidget):
                    self._apply_text_unlock_widget(child)
            elif event.type() in {QEvent.Type.Show, QEvent.Type.Polish} and isinstance(watched, QWidget):
                self._apply_text_unlock_widget(watched)
        if not self._inspect_mode or self._application is None or self._main_window is None:
            return False
        if event.type() == QEvent.Type.KeyPress and getattr(event, "key", lambda: None)() == Qt.Key.Key_Escape:
            self.set_inspect_mode(False)
            return True
        if event.type() not in {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick}:
            return False

        widget = self._resolve_target_widget()
        self._highlight_widget(widget)

        if event.type() in {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick}:
            button = getattr(event, "button", lambda: None)()
            if button == Qt.MouseButton.RightButton and widget is not None:
                if self._navigate_with_secondary_click(widget):
                    return True

        if event.type() in {QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick}:
            button = getattr(event, "button", lambda: None)()
            if button == Qt.MouseButton.LeftButton and widget is not None:
                try:
                    snapshot = self._snapshot_widget(widget)
                except Exception:
                    self.set_inspect_mode(False)
                    return True
                self._last_payload = snapshot.to_payload()
                self.snapshot_changed.emit(dict(self._last_payload))
                self.set_inspect_mode(False)
                return True
        return False

    def _resolve_target_widget(self) -> QWidget | None:
        if self._application is None or self._main_window is None:
            return None
        widget = self._application.widgetAt(QCursor.pos())
        if widget is None:
            return None
        if self._overlay is not None and (widget is self._overlay or self._overlay.isAncestorOf(widget)):
            return None
        if widget is self._main_window or self._main_window.isAncestorOf(widget):
            return widget
        return None

    def _highlight_widget(self, widget: QWidget | None) -> None:
        if self._overlay is None or self._main_window is None or widget is None:
            if self._overlay is not None:
                self._overlay.clear()
            return
        top_left = widget.mapToGlobal(QPoint(0, 0))
        local_top_left = self._main_window.mapFromGlobal(top_left)
        rect = QRect(local_top_left, widget.size()).adjusted(0, 0, -1, -1)
        self._overlay.set_target_rect(rect)

    def _snapshot_widget(self, widget: QWidget) -> InspectorSnapshot:
        top_left = widget.mapToGlobal(QPoint(0, 0))
        rect = QRect(top_left, widget.size())
        parent_chain: list[str] = []
        parent = widget.parentWidget()
        while parent is not None:
            label = parent.metaObject().className()
            if parent.objectName():
                label += f"#{parent.objectName()}"
            parent_chain.append(label)
            parent = parent.parentWidget()

        layout = widget.layout()
        if layout is None:
            margins = "None"
        else:
            m = layout.contentsMargins()
            margins = f"{m.left()}, {m.top()}, {m.right()}, {m.bottom()}"

        properties: dict[str, str] = {}
        for name in widget.dynamicPropertyNames():
            key = bytes(name).decode("utf-8", errors="ignore")
            try:
                value = widget.property(key)
            except Exception:
                continue
            try:
                properties[key] = str(value)
            except Exception:
                properties[key] = f"<unserializable:{type(value).__name__}>"

        palette = widget.palette()
        palette_roles = {
            "window": palette.color(widget.backgroundRole()).name(),
            "window_text": palette.color(widget.foregroundRole()).name(),
            "base": palette.color(palette.ColorRole.Base).name(),
            "button": palette.color(palette.ColorRole.Button).name(),
            "highlight": palette.color(palette.ColorRole.Highlight).name(),
        }

        return InspectorSnapshot(
            class_name=widget.metaObject().className(),
            object_name=widget.objectName(),
            window_title=widget.windowTitle(),
            geometry=f"{widget.x()}, {widget.y()}, {widget.width()} x {widget.height()}",
            global_geometry=f"{rect.x()}, {rect.y()}, {rect.width()} x {rect.height()}",
            visible=widget.isVisible(),
            enabled=widget.isEnabled(),
            stylesheet=widget.styleSheet().strip(),
            layout_margins=margins,
            dynamic_properties=properties,
            palette_roles=palette_roles,
            parent_chain=parent_chain,
            child_count=len(widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly)),
        )

    def _apply_text_unlock_to_all_widgets(self) -> None:
        if self._application is None:
            return
        for widget in self._application.allWidgets():
            self._apply_text_unlock_widget(widget)

    def _apply_text_unlock_widget(self, root: QWidget) -> None:
        if isinstance(root, QLabel):
            self._set_label_text_unlock(root)
        for label in root.findChildren(QLabel):
            self._set_label_text_unlock(label)

    def _set_label_text_unlock(self, label: QLabel) -> None:
        property_name = "_micro_inspector_original_text_flags"
        if self._text_unlock_enabled:
            if label.property(property_name) is None:
                label.setProperty(property_name, label.textInteractionFlags())
            label.setTextInteractionFlags(
                label.textInteractionFlags()
                | Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.TextSelectableByKeyboard
            )
            return

        original_flags = label.property(property_name)
        if original_flags is not None:
            label.setTextInteractionFlags(original_flags)
            label.setProperty(property_name, None)

    def _navigate_with_secondary_click(self, widget: QWidget) -> bool:
        tree = self._find_tree_ancestor(widget)
        if tree is not None:
            item = tree.itemAt(tree.viewport().mapFromGlobal(QCursor.pos()))
            if item is not None:
                plugin_role = Qt.ItemDataRole.UserRole + 1
                if item.data(0, plugin_role):
                    tree.setCurrentItem(item)
                elif item.childCount() > 0:
                    item.setExpanded(not item.isExpanded())
                else:
                    return False
                return True

        button = self._find_button_ancestor(widget)
        if button is not None and button.isEnabled():
            button.click()
            return True
        return False

    def _find_button_ancestor(self, widget: QWidget | None) -> QAbstractButton | None:
        current = widget
        while current is not None:
            if isinstance(current, QAbstractButton):
                return current
            current = current.parentWidget()
        return None

    def _find_tree_ancestor(self, widget: QWidget | None) -> QTreeWidget | None:
        current = widget
        while current is not None:
            if isinstance(current, QTreeWidget):
                return current
            current = current.parentWidget()
        return None
