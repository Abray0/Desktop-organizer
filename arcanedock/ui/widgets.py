"""Custom-painted pieces: the glass backdrop, flow grid, tiles and group rows."""
from __future__ import annotations

from PySide6.QtCore import (QMimeData, QPoint, QPointF, QRect, QRectF, QSize,
                            Qt, Signal)
from PySide6.QtGui import (QColor, QDrag, QFont, QFontMetrics, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap,
                           QRadialGradient)
from PySide6.QtWidgets import QApplication, QLayout, QSizePolicy, QWidget

from . import theme

RADIUS = 8  # matches the DWM corner radius, so the curves coincide


def fit_lines(metrics: QFontMetrics, text: str, width: int, max_lines: int = 2) -> list[str]:
    """Greedy word wrap into at most max_lines, eliding whatever still overflows."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for index, word in enumerate(words):
        trial = f"{current} {word}".strip()
        if not current or metrics.horizontalAdvance(trial) <= width:
            current = trial
            continue
        lines.append(current)
        if len(lines) == max_lines - 1:
            current = " ".join(words[index:])
            break
        current = word
    if current:
        lines.append(current)
    return [metrics.elidedText(line, Qt.ElideRight, width) for line in lines[:max_lines]]


class GlassRoot(QWidget):
    """Rounded translucent pane. The wash is rendered once per size and blitted."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._backdrop: QPixmap | None = None

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._backdrop = None

    def discard_backdrop(self) -> None:
        self._backdrop = None
        self.update()

    def _build_backdrop(self) -> QPixmap:
        ratio = self.devicePixelRatioF()
        pixmap = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        pixmap.setDevicePixelRatio(ratio)
        pixmap.fill(Qt.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, RADIUS, RADIUS)
        painter.setClipPath(path)

        base = QLinearGradient(rect.topLeft(), rect.bottomRight())
        base.setColorAt(0.0, theme.GLASS[0])
        base.setColorAt(0.55, theme.GLASS[1])
        base.setColorAt(1.0, theme.GLASS[2])
        painter.fillPath(path, base)

        for cx, cy, radius, color in theme.AURORA:
            center = QPointF(rect.width() * cx, rect.height() * cy)
            glow = QRadialGradient(center, rect.width() * radius)
            glow.setColorAt(0.0, color)
            glow.setColorAt(1.0, QColor(color.red(), color.green(), color.blue(), 0))
            painter.fillRect(rect, glow)
        painter.end()
        return pixmap

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)

        if self._backdrop is None:
            self._backdrop = self._build_backdrop()
        painter.drawPixmap(0, 0, self._backdrop)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor(255, 255, 255, 38), 1))
        painter.drawRoundedRect(rect, RADIUS, RADIUS)
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.drawLine(QPointF(rect.left() + RADIUS, rect.top() + 1.0),
                         QPointF(rect.right() - RADIUS, rect.top() + 1.0))


class FlowLayout(QLayout):
    """Left-to-right wrapping layout for the tile grid."""

    def __init__(self, parent=None, margin=0, spacing=12):
        super().__init__(parent)
        self._items: list = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._arrange(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._arrange(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QSize(margins.left() + margins.right(),
                            margins.top() + margins.bottom())

    def _arrange(self, rect, test_only):
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(),
                             -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        space = self.spacing()
        for item in self._items:
            hint = item.sizeHint()
            if x + hint.width() > area.right() + 1 and line_height > 0:
                x = area.x()
                y += line_height + space
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + space
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class Tile(QWidget):
    """An icon + label chip. Used for launcher apps and for desktop items."""

    activated = Signal(object)
    menu_requested = Signal(object, QPoint)

    def __init__(self, payload, name: str, icon, width: int = 116, height: int = 112,
                 icon_size: int = 46, double_click: bool = False,
                 drag_data: tuple[str, bytes] | None = None, parent=None):
        super().__init__(parent)
        self.payload = payload
        self.name = name
        self.icon_size = icon_size
        self.double_click = double_click
        self.drag_data = drag_data
        self._icon = icon
        self._glow = 0.0
        self._press: QPoint | None = None

        self.setFixedSize(width, height)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(name)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.payload, self.mapToGlobal(pos)))

    def _set_glow(self, value: float) -> None:
        self._glow = value
        self.update()

    def enterEvent(self, event):
        self._set_glow(1.0)

    def leaveEvent(self, event):
        self._set_glow(0.0)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press = event.position().toPoint()

    def mouseMoveEvent(self, event):
        if self.drag_data is None or self._press is None:
            return
        if not (event.buttons() & Qt.LeftButton):
            return
        moved = (event.position().toPoint() - self._press).manhattanLength()
        if moved < QApplication.startDragDistance():
            return
        mime = QMimeData()
        mime.setData(self.drag_data[0], self.drag_data[1])
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(self._icon.pixmap(QSize(48, 48)))
        drag.setHotSpot(QPoint(24, 24))
        self._press = None
        self._set_glow(0.0)
        drag.exec(Qt.MoveAction)

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.position().toPoint())
        if event.button() == Qt.LeftButton and inside and not self.double_click:
            self.activated.emit(self.payload)
        self._press = None

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self.double_click:
            self.activated.emit(self.payload)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = 14 if self.width() > 100 else 11
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        glow = self._glow
        painter.fillPath(path, QColor(255, 255, 255, int(10 + 26 * glow)))
        if glow > 0.01:
            halo = QRadialGradient(rect.center(), rect.width() * 0.75)
            halo.setColorAt(0.0, theme.accent_qcolor(int(58 * glow)))
            halo.setColorAt(1.0, theme.accent_qcolor(0))
            painter.fillPath(path, halo)
        painter.setPen(QPen(QColor(255, 255, 255, int(26 + 90 * glow)), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, radius, radius)

        size = int(self.icon_size + 4 * glow)
        ratio = self.devicePixelRatioF()
        pixmap = self._icon.pixmap(QSize(int(size * ratio), int(size * ratio)))
        pixmap.setDevicePixelRatio(ratio)
        target = QRectF(0, 0, size, size)
        target.moveCenter(QPointF(rect.center().x(),
                                  rect.top() + 10 + self.icon_size / 2))
        painter.drawPixmap(target.toRect(), pixmap)

        painter.setPen(QColor(theme.INK) if glow > 0.5 else QColor(theme.DIM))
        font = QFont(self.font())
        font.setPointSizeF(8.5 if self.width() > 100 else 7.8)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        usable = int(rect.width()) - 12
        lines = fit_lines(metrics, self.name, usable)
        line_height = metrics.height()
        top = rect.bottom() - 6 - line_height * len(lines)
        for index, line in enumerate(lines):
            painter.drawText(
                QRectF(rect.left() + 6, top + index * line_height, usable, line_height),
                Qt.AlignHCenter | Qt.AlignVCenter, line)


class GroupRow(QWidget):
    """Sidebar entry for one group."""

    clicked = Signal(str)
    menu_requested = Signal(str, QPoint)

    def __init__(self, group: dict, parent=None):
        super().__init__(parent)
        self.group = group
        self.selected = False
        self._hover = False
        self.setFixedHeight(38)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(
            lambda pos: self.menu_requested.emit(self.group["id"], self.mapToGlobal(pos)))
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_selected(self, value: bool):
        self.selected = value
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.group["id"])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0, 2, -4, -2)

        if self.selected:
            fill = QLinearGradient(rect.topLeft(), rect.topRight())
            fill.setColorAt(0.0, theme.accent_qcolor(78))
            fill.setColorAt(1.0, theme.accent_qcolor(16))
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            painter.fillPath(path, fill)
            painter.fillRect(QRectF(rect.left(), rect.top() + 7, 3, rect.height() - 14),
                             QColor(theme.ACCENT))
        elif self._hover:
            path = QPainterPath()
            path.addRoundedRect(rect, 10, 10)
            painter.fillPath(path, QColor(255, 255, 255, 20))

        painter.setPen(QColor(theme.ACCENT) if self.selected else QColor(theme.FAINT))
        painter.drawText(QRectF(rect.left() + 12, rect.top(), 22, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, self.group.get("glyph", "✦"))

        font = QFont(self.font())
        font.setBold(self.selected)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        name = metrics.elidedText(self.group["name"], Qt.ElideRight, int(rect.width()) - 78)
        painter.drawText(QRectF(rect.left() + 38, rect.top(), rect.width() - 76, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, name)

        painter.setPen(QColor(theme.FAINT))
        painter.drawText(QRectF(rect.right() - 34, rect.top(), 28, rect.height()),
                         Qt.AlignVCenter | Qt.AlignRight, str(len(self.group["apps"])))


class GlyphButton(QWidget):
    """Small round icon button drawn from a text glyph."""

    clicked = Signal()

    def __init__(self, glyph: str, tip: str = "", size: int = 30, danger=False, parent=None):
        super().__init__(parent)
        self.glyph = glyph
        self.danger = danger
        self._hover = False
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        if tip:
            self.setToolTip(tip)

    def enterEvent(self, event):
        self._hover = True
        self.update()

    def leaveEvent(self, event):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._hover:
            accent = QColor(232, 90, 110, 60) if self.danger else theme.accent_qcolor(60)
            painter.setBrush(accent)
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1))
            painter.drawEllipse(rect)
        painter.setPen(QColor(theme.INK) if self._hover else QColor(theme.DIM))
        font = QFont(self.font())
        font.setPointSizeF(11)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignCenter, self.glyph)
