"""Double-click on empty desktop to peek: hides or shows every fence.

Windows only synthesises double-clicks for the window that owns them, and the
desktop is another process, so the pair of clicks is recognised here from the
raw low-level mouse stream instead.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

WH_MOUSE_LL = 14
WM_LBUTTONDOWN = 0x0201
HC_ACTION = 0

# Clicking any of these means the desktop itself was clicked, not an app.
DESKTOP_CLASSES = {"Progman", "WorkerW", "SHELLDLL_DefView", "SysListView32"}

_user32 = ctypes.windll.user32


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int,
                              wintypes.WPARAM, wintypes.LPARAM)

# Without explicit signatures ctypes guesses, and guesses wrong for the 64-bit
# pointer that arrives as lParam.
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC,
                                      wintypes.HINSTANCE, wintypes.DWORD]
_user32.SetWindowsHookExW.restype = wintypes.HANDLE
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
_user32.UnhookWindowsHookEx.restype = wintypes.BOOL
_user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int,
                                   wintypes.WPARAM, wintypes.LPARAM]
_user32.CallNextHookEx.restype = ctypes.c_ssize_t
_user32.WindowFromPoint.argtypes = [POINT]
_user32.WindowFromPoint.restype = wintypes.HWND
_user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_user32.GetClassNameW.restype = ctypes.c_int
_user32.GetDoubleClickTime.restype = wintypes.UINT


class DesktopDoubleClick:
    """Calls back when the user double-clicks empty desktop."""

    def __init__(self, on_double_click):
        self._on_double_click = on_double_click
        self._last_time = 0
        self._last_pos = (0, 0)
        self._hook = None
        # Held as an attribute so the thunk is not garbage collected.
        self._proc = HOOKPROC(self._callback)

    def start(self) -> bool:
        if self._hook:
            return True
        self._hook = _user32.SetWindowsHookExW(WH_MOUSE_LL, self._proc, None, 0)
        return bool(self._hook)

    def stop(self) -> None:
        if self._hook:
            _user32.UnhookWindowsHookEx(self._hook)
            self._hook = None

    def _is_desktop(self, x: int, y: int) -> bool:
        window = _user32.WindowFromPoint(POINT(x, y))
        if not window:
            return False
        buffer = ctypes.create_unicode_buffer(64)
        _user32.GetClassNameW(window, buffer, 64)
        return buffer.value in DESKTOP_CLASSES

    def _callback(self, code, wparam, lparam):
        # Anything but a left press is passed straight through untouched; this
        # runs for every mouse event in the session, so it stays cheap.
        if code == HC_ACTION and wparam == WM_LBUTTONDOWN:
            data = ctypes.cast(lparam, ctypes.POINTER(MSLLHOOKSTRUCT)).contents
            x, y, when = data.pt.x, data.pt.y, data.time
            gap = when - self._last_time
            near = (abs(x - self._last_pos[0]) <= 6
                    and abs(y - self._last_pos[1]) <= 6)
            if 0 < gap <= _user32.GetDoubleClickTime() and near:
                self._last_time = 0
                if self._is_desktop(x, y):
                    try:
                        self._on_double_click()
                    except Exception:
                        pass
            else:
                self._last_time, self._last_pos = when, (x, y)
        return _user32.CallNextHookEx(None, code, wparam, lparam)
