from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QGuiApplication, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class ScreenCapture:
    geometry: QRect
    pixmap: QPixmap


class ScreenColorPickerOverlay(QWidget):
    color_picked = Signal(QColor)
    canceled = Signal()

    def __init__(self, geometry: QRect, captures: list[ScreenCapture]):
        super().__init__(None)
        self._geometry = QRect(geometry)
        self._captures = list(captures)
        self._cursor_pos = QPoint(0, 0)
        self._hover_color = QColor()
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(Qt.WindowType.BypassWindowManagerHint, False)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setGeometry(self._geometry)
        self._update_hover(QCursor.pos())

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.activateWindow()
        self.raise_()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        self._update_hover(event.globalPosition().toPoint())
        event.accept()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.color_picked.emit(self._hover_color)
            event.accept()
            return
        if event.button() in {Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton}:
            self.canceled.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for capture in self._captures:
            target_rect = QRect(capture.geometry)
            target_rect.moveTopLeft(capture.geometry.topLeft() - self._geometry.topLeft())
            painter.drawPixmap(target_rect, capture.pixmap)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 18))

        if not self._cursor_pos.isNull():
            cross_pen = QPen(QColor("#ffffff"), 1)
            painter.setPen(cross_pen)
            painter.drawLine(self._cursor_pos.x(), 0, self._cursor_pos.x(), self.height())
            painter.drawLine(0, self._cursor_pos.y(), self.width(), self._cursor_pos.y())
            painter.fillRect(self._cursor_pos.x() - 6, self._cursor_pos.y() - 6, 12, 12, self._hover_color)
            painter.setPen(QPen(QColor(0, 0, 0, 160), 2))
            painter.drawRect(self._cursor_pos.x() - 6, self._cursor_pos.y() - 6, 12, 12)
            self._paint_info_chip(painter)
        painter.end()

    def _paint_info_chip(self, painter: QPainter) -> None:
        hex_text = self._hover_color.name().upper() if self._hover_color.isValid() else "#000000"
        chip_rect = QRect(self._cursor_pos.x() + 18, self._cursor_pos.y() + 18, 124, 34)
        if chip_rect.right() > self.width() - 8:
            chip_rect.moveLeft(self._cursor_pos.x() - chip_rect.width() - 18)
        if chip_rect.bottom() > self.height() - 8:
            chip_rect.moveTop(self._cursor_pos.y() - chip_rect.height() - 18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(18, 24, 31, 232))
        painter.drawRoundedRect(chip_rect, 10, 10)
        swatch_rect = QRect(chip_rect.left() + 8, chip_rect.top() + 8, 18, 18)
        painter.setBrush(self._hover_color)
        painter.drawRoundedRect(swatch_rect, 4, 4)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(chip_rect.adjusted(34, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter, hex_text)

    def _update_hover(self, global_pos: QPoint) -> None:
        self._cursor_pos = self.mapFromGlobal(global_pos)
        self._hover_color = self._sample_color(self._cursor_pos)
        self.update()

    def _sample_color(self, local_pos: QPoint) -> QColor:
        global_pos = local_pos + self._geometry.topLeft()
        for capture in self._captures:
            if not capture.geometry.contains(global_pos):
                continue
            if capture.pixmap.isNull():
                break
            image = capture.pixmap.toImage()
            local_screen_pos = global_pos - capture.geometry.topLeft()
            dpr = max(1.0, float(capture.pixmap.devicePixelRatio()))
            x = max(0, min(image.width() - 1, int(local_screen_pos.x() * dpr)))
            y = max(0, min(image.height() - 1, int(local_screen_pos.y() * dpr)))
            return image.pixelColor(x, y)
        return QColor("#000000")


class ScreenColorPickerSession(QObject):
    color_picked = Signal(QColor)
    canceled = Signal()

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._overlay: ScreenColorPickerOverlay | None = None

    def start(self) -> bool:
        screens = QGuiApplication.screens()
        if not screens:
            return False
        self._close_all()
        geometry = self._virtual_geometry(screens)
        captures = self._capture_screens(screens)
        if geometry.isNull() or not captures:
            return False
        overlay = ScreenColorPickerOverlay(geometry, captures)
        overlay.color_picked.connect(self._handle_color_picked)
        overlay.canceled.connect(self._handle_canceled)
        self._overlay = overlay
        overlay.show()
        return True

    def _handle_color_picked(self, color: QColor) -> None:
        self._close_all()
        self.color_picked.emit(color)

    def _handle_canceled(self) -> None:
        self._close_all()
        self.canceled.emit()

    def _close_all(self) -> None:
        if self._overlay is not None:
            try:
                self._overlay.close()
            except Exception:
                pass
            self._overlay.deleteLater()
            self._overlay = None

    def _virtual_geometry(self, screens) -> QRect:
        geometry = QRect()
        for screen in screens:
            geometry = geometry.united(screen.geometry())
        return geometry

    def _capture_screens(self, screens) -> list[ScreenCapture]:
        captures: list[ScreenCapture] = []
        for screen in screens:
            shot = screen.grabWindow(0)
            if shot.isNull():
                continue
            captures.append(ScreenCapture(screen.geometry(), shot))
        return captures
