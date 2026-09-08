"""Windows 11 acrylic backdrop + rounded corners via ctypes (no extra deps)."""
from __future__ import annotations

import ctypes
from ctypes import wintypes

ACCENT_ENABLE_ACRYLICBLURBEHIND = 4
ACCENT_ENABLE_BLURBEHIND = 3
WCA_ACCENT_POLICY = 19
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_SYSTEMBACKDROP_TYPE = 38
DWMWCP_ROUND = 2
DWMSBT_TRANSIENTWINDOW = 3  # acrylic


class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class WINDOWCOMPOSITIONATTRIBDATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(ctypes.c_int)),
        ("SizeOfData", ctypes.c_size_t),
    ]


def _hwnd(widget) -> int:
    return int(widget.winId())


def round_corners(widget) -> None:
    """Ask DWM for Windows 11 rounded corners so the blur follows the shape."""
    try:
        pref = ctypes.c_int(DWMWCP_ROUND)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(_hwnd(widget)), DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(pref), ctypes.sizeof(pref))
    except Exception:
        pass


def apply_acrylic(widget, tint: int = 0x2A140A20, enabled: bool = True) -> bool:
    """Blur whatever is behind the window. tint is 0xAABBGGRR."""
    try:
        accent = ACCENT_POLICY()
        accent.AccentState = ACCENT_ENABLE_ACRYLICBLURBEHIND if enabled else 0
        accent.AccentFlags = 0x20 | 0x40 | 0x80 | 0x100  # blur all four edges
        accent.GradientColor = tint
        accent.AnimationId = 0

        data = WINDOWCOMPOSITIONATTRIBDATA()
        data.Attribute = WCA_ACCENT_POLICY
        data.Data = ctypes.cast(ctypes.pointer(accent), ctypes.POINTER(ctypes.c_int))
        data.SizeOfData = ctypes.sizeof(accent)

        set_attr = ctypes.windll.user32.SetWindowCompositionAttribute
        set_attr.argtypes = [wintypes.HWND, ctypes.POINTER(WINDOWCOMPOSITIONATTRIBDATA)]
        ok = bool(set_attr(wintypes.HWND(_hwnd(widget)), ctypes.byref(data)))
        round_corners(widget)
        return ok
    except Exception:
        return False
