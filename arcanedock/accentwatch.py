"""Notices when Windows changes its accent colour, so the glass follows it live."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer

WM_SETTINGCHANGE = 0x001A
WM_DWMCOLORIZATIONCOLORCHANGED = 0x0320
WM_THEMECHANGED = 0x031A


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", wintypes.DWORD),
        ("pt_x", wintypes.LONG),
        ("pt_y", wintypes.LONG),
    ]

WATCHED = {WM_SETTINGCHANGE, WM_DWMCOLORIZATIONCOLORCHANGED, WM_THEMECHANGED}


class AccentWatcher(QAbstractNativeEventFilter, QObject):
    """Calls back once, shortly after Windows reports a colour or theme change."""

    def __init__(self, on_change, parent=None):
        QAbstractNativeEventFilter.__init__(self)
        QObject.__init__(self, parent)
        self._on_change = on_change
        # Windows sends a flurry of these; one repaint at the end is enough.
        self._debounce = QTimer(self, singleShot=True, interval=250)
        self._debounce.timeout.connect(self._on_change)

    def nativeEventFilter(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(MSG)).contents
            except (TypeError, ValueError):
                return False, 0
            if msg.message in WATCHED:
                self._debounce.start()
        return False, 0
