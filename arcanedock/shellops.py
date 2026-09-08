"""Shell operations: opening items, recycling them, and the desktop icon layer."""
from __future__ import annotations

import ctypes
import os
import subprocess
from ctypes import byref, wintypes

from .winicon import GUID, make_guid

_user32 = ctypes.windll.user32
_shell32 = ctypes.windll.shell32
_ole32 = ctypes.windll.ole32

_user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowW.restype = wintypes.HWND
_user32.FindWindowExW.argtypes = [wintypes.HWND, wintypes.HWND,
                                  wintypes.LPCWSTR, wintypes.LPCWSTR]
_user32.FindWindowExW.restype = wintypes.HWND
_user32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
_user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t

FOLDERID_DESKTOP = "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}"
FOLDERID_PUBLIC_DESKTOP = "{C4AA340D-F20F-4863-AFEF-F87EF2E6BA25}"

GWLP_HWNDPARENT = -8
HWND_BOTTOM = 1
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SW_HIDE = 0
SW_SHOW = 5

FO_DELETE = 3
FOF_SILENT = 0x0004
FOF_NOCONFIRMATION = 0x0010
FOF_ALLOWUNDO = 0x0040
FOF_NOERRORUI = 0x0400


class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", ctypes.c_uint),
        ("pFrom", ctypes.c_wchar_p),
        ("pTo", ctypes.c_wchar_p),
        ("fFlags", ctypes.c_uint16),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", ctypes.c_wchar_p),
    ]


# ------------------------------------------------------------------ locations
def _known_folder(folder_id: str) -> str | None:
    guid = make_guid(folder_id)
    out = ctypes.c_wchar_p()
    if _shell32.SHGetKnownFolderPath(byref(guid), 0, None, byref(out)) != 0:
        return None
    path = out.value
    _ole32.CoTaskMemFree(out)
    return path


def desktop_dirs() -> list[str]:
    """The folders Explorer actually draws on the desktop, in display order.

    Asked of the shell rather than assumed, so a OneDrive-redirected Desktop
    resolves to wherever it really lives.
    """
    dirs = []
    for folder_id in (FOLDERID_DESKTOP, FOLDERID_PUBLIC_DESKTOP):
        path = _known_folder(folder_id)
        if path and os.path.isdir(path) and path not in dirs:
            dirs.append(path)
    return dirs


# ------------------------------------------------------------- system colour
def accent_color() -> tuple[int, int, int] | None:
    """The Windows accent colour, or None if it cannot be read."""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\DWM") as key:
            value, _ = winreg.QueryValueEx(key, "AccentColor")  # 0xAABBGGRR
        return (value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\DWM") as key:
            value, _ = winreg.QueryValueEx(key, "ColorizationColor")  # 0x00RRGGBB
        return ((value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF)
    except OSError:
        return None


# --------------------------------------------------------------- file actions
def is_shell_item(path: str) -> bool:
    """True for shell namespace entries such as the Recycle Bin."""
    return path.startswith("::")


def open_item(path: str) -> bool:
    if is_shell_item(path):
        try:
            subprocess.Popen(["explorer.exe", "shell:" + path])
            return True
        except OSError:
            return False
    try:
        os.startfile(path)  # noqa: S606 - launching by shell association is the point
        return True
    except OSError:
        return False


def reveal(path: str) -> None:
    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def recycle(paths: list[str]) -> bool:
    """Send files to the Recycle Bin (undoable), never a hard delete."""
    if not paths:
        return True
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = "\0".join(os.path.normpath(p) for p in paths) + "\0\0"
    op.pTo = None
    op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI
    return _shell32.SHFileOperationW(byref(op)) == 0 and not op.fAnyOperationsAborted


def rename(path: str, new_name: str) -> str | None:
    target = os.path.join(os.path.dirname(path), new_name)
    if os.path.exists(target):
        return None
    try:
        os.rename(path, target)
        return target
    except OSError:
        return None


# -------------------------------------------------------------- desktop layer
def progman() -> int:
    return _user32.FindWindowW("Progman", None) or 0


def _desktop_listview() -> int:
    """The SysListView32 that draws the desktop icons, wherever it is parented."""
    defview = _user32.FindWindowExW(progman(), None, "SHELLDLL_DefView", None)
    if not defview:
        # With a wallpaper slideshow or a live wallpaper the icon host is
        # re-parented under one of the WorkerW windows instead of Progman.
        found = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def each(hwnd, _lparam):
            child = _user32.FindWindowExW(hwnd, None, "SHELLDLL_DefView", None)
            if child:
                found.append(child)
                return False
            return True

        _user32.EnumWindows(each, 0)
        defview = found[0] if found else None
    if not defview:
        return 0
    return _user32.FindWindowExW(defview, None, "SysListView32", None) or 0


def native_icons_visible() -> bool:
    listview = _desktop_listview()
    return bool(listview and _user32.IsWindowVisible(listview))


def set_native_icons(show: bool) -> bool:
    """Show or hide Windows' own desktop icons. Reversible, nothing is deleted."""
    listview = _desktop_listview()
    if not listview:
        return False
    _user32.ShowWindow(listview, SW_SHOW if show else SW_HIDE)
    return True


def pin_to_desktop(widget) -> None:
    """Keep a window glued to the desktop: above the wallpaper, below real windows."""
    hwnd = int(widget.winId())
    owner = progman()
    if owner:
        try:
            _user32.SetWindowLongPtrW(hwnd, GWLP_HWNDPARENT, owner)
        except Exception:
            pass
    send_to_bottom(widget)


def send_to_bottom(widget) -> None:
    hwnd = int(widget.winId())
    _user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_BOTTOM), 0, 0, 0, 0,
                         SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
