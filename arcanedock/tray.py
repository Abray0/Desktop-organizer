"""System tray icon and its options menu."""
from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import (QAction, QColor, QIcon, QLinearGradient, QPainter,
                           QPainterPath, QPixmap)
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import shellops, startup
from .config import APP_TITLE, Store
from .ui import theme


def make_icon() -> QIcon:
    """A violet sigil, drawn at runtime so the app ships without image assets."""
    icon = QIcon()
    for edge in (16, 24, 32, 48, 64):
        pixmap = QPixmap(edge, edge)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        gradient = QLinearGradient(0, 0, edge, edge)
        gradient.setColorAt(0.0, QColor(186, 152, 255))
        gradient.setColorAt(1.0, QColor(97, 214, 214))

        path = QPainterPath()
        cx = cy = edge / 2
        span = edge * 0.46
        waist = edge * 0.13
        path.moveTo(QPointF(cx, cy - span))
        path.quadTo(QPointF(cx + waist, cy - waist), QPointF(cx + span, cy))
        path.quadTo(QPointF(cx + waist, cy + waist), QPointF(cx, cy + span))
        path.quadTo(QPointF(cx - waist, cy + waist), QPointF(cx - span, cy))
        path.quadTo(QPointF(cx - waist, cy - waist), QPointF(cx, cy - span))
        painter.fillPath(path, gradient)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


class Tray(QSystemTrayIcon):
    def __init__(self, store: Store, manager, open_launcher, on_quit):
        super().__init__(make_icon())
        self.store = store
        self.manager = manager
        self.open_launcher = open_launcher
        self.on_quit = on_quit

        self.setToolTip(APP_TITLE)
        self.activated.connect(self._activated)

        self.menu = QMenu()
        self.menu.setStyleSheet(theme.qss())

        self.show_fences = self._check(self.menu, "Show desktop fences",
                                       self.manager.set_visible)
        self.menu.addSeparator()

        for label, handler in (("New fence…", self.manager.new_fence_here),
                               ("Rescan desktop", self.manager.rescan)):
            action = QAction(label, self.menu)
            action.triggered.connect(handler)
            self.menu.addAction(action)
        self.menu.addSeparator()

        launcher = QAction("App launcher…", self.menu)
        launcher.triggered.connect(self.open_launcher)
        self.menu.addAction(launcher)
        self.menu.addSeparator()

        options = self.menu.addMenu("Options")
        self.opt_startup = self._check(options, "Start with Windows", self._set_startup)
        self.opt_native = self._check(options, "Hide Windows desktop icons",
                                      self._set_native_icons)
        options.addSeparator()
        self.opt_lock = self._check(options, "Lock fences in place",
                                    self.manager.set_locked)
        self.opt_peek = self._check(options, "Double-click desktop to peek",
                                    self.manager.set_peek)
        self.opt_blur = self._check(options, "Glass blur", self._set_blur)
        self.opt_accent = self._check(options, "Use Windows accent colour",
                                      self._set_system_accent)
        options.addSeparator()
        reset = QAction("Reset fence layout…", options)
        reset.triggered.connect(self.manager.reset_layout)
        options.addAction(reset)

        self.menu.addSeparator()
        quit_action = QAction("Quit", self.menu)
        quit_action.triggered.connect(self.on_quit)
        self.menu.addAction(quit_action)

        self.menu.aboutToShow.connect(self._sync)
        self.setContextMenu(self.menu)

    def _check(self, menu: QMenu, text: str, handler) -> QAction:
        action = QAction(text, menu)
        action.setCheckable(True)
        action.toggled.connect(handler)
        menu.addAction(action)
        return action

    def _sync(self) -> None:
        settings = self.store.settings
        for action, value in (
            (self.show_fences, settings["fences_visible"]),
            (self.opt_startup, startup.is_enabled()),
            (self.opt_native, not shellops.native_icons_visible()),
            (self.opt_lock, settings["lock_fences"]),
            (self.opt_peek, settings["peek_on_double_click"]),
            (self.opt_blur, settings["glass_blur"]),
            (self.opt_accent, settings["system_accent"]),
        ):
            action.blockSignals(True)
            action.setChecked(bool(value))
            action.blockSignals(False)

    def _set(self, key: str, value: bool) -> None:
        self.store.settings[key] = bool(value)
        self.store.save()

    def _set_startup(self, on: bool) -> None:
        if startup.set_enabled(on):
            self._set("start_with_windows", on)
        else:
            self.message("Could not update the Windows startup entry.")

    def _set_native_icons(self, hide: bool) -> None:
        if shellops.set_native_icons(not hide):
            self._set("hide_native_icons", hide)
            if hide:
                self.message("Windows desktop icons hidden — your files are untouched.")
        else:
            self.message("Could not reach the desktop icon layer.")

    def _set_system_accent(self, on: bool) -> None:
        self._set("system_accent", on)
        theme.set_accent(shellops.accent_color() if on else None)
        self.menu.setStyleSheet(theme.qss())
        self.manager.restyle()

    def _set_blur(self, on: bool) -> None:
        self._set("glass_blur", on)
        self.manager.apply_glass()

    def message(self, text: str) -> None:
        self.showMessage(APP_TITLE, text, make_icon(), 3000)

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.manager.set_visible(not self.store.settings["fences_visible"])
