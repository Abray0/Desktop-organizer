"""Shell icon extraction with a small in-process cache."""
from __future__ import annotations

from PySide6.QtCore import QFileInfo, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPixmap)

from .winicon import resolve_shortcut, shell_icon

try:  # Qt 6 moved this out of QtWidgets partway through the 6.x line.
    from PySide6.QtGui import QFileIconProvider
except ImportError:  # pragma: no cover - depends on PySide6 build
    from PySide6.QtWidgets import QFileIconProvider

_provider = QFileIconProvider()
_cache: dict[tuple[str, bool], QIcon] = {}


def _rune(letter: str, size: int = 96) -> QIcon:
    """Fallback tile art: a lettered sigil, so nothing renders as a blank box."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(6, 6, size - 12, size - 12), size * 0.26, size * 0.26)
    gradient = QLinearGradient(0, 0, size, size)
    gradient.setColorAt(0.0, QColor(139, 108, 232, 215))
    gradient.setColorAt(1.0, QColor(74, 158, 196, 215))
    painter.fillPath(path, gradient)
    painter.setPen(QColor(255, 255, 255, 235))
    painter.setFont(QFont("Georgia", int(size * 0.4), QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, letter.upper()[:1] or "?")
    painter.end()
    return QIcon(pixmap)


def icon_for(path: str, name: str = "", thumbnail: bool = False) -> QIcon:
    key = (path.lower(), thumbnail)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    # For a shortcut, take the target's icon: same art, minus the overlay arrow.
    source = path
    if path.lower().endswith(".lnk"):
        source = resolve_shortcut(path) or path

    icon = QIcon()
    pixmap = None
    if thumbnail:
        # Photos and videos read far better as their own thumbnail; anything
        # without one falls back to the ordinary icon below.
        pixmap = shell_icon(source, 128, icon_only=False)
    if pixmap is None or pixmap.isNull():
        pixmap = shell_icon(source, 96)
    if pixmap is not None and not pixmap.isNull():
        icon = QIcon(pixmap)
    else:
        try:
            icon = _provider.icon(QFileInfo(path))
        except Exception:
            pass
    if icon.isNull() or not icon.availableSizes():
        icon = _rune(name or QFileInfo(path).baseName())

    # The Recycle Bin swaps between full and empty art, so never cache it.
    if not path.startswith("::"):
        _cache[key] = icon
    return icon
