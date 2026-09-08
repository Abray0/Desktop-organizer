"""High-resolution shell icons without third-party packages.

Two pieces, both plain ctypes:
  * resolve_shortcut() reads a .lnk's target straight out of the file, so we can
    take the icon from the real executable and skip the blue overlay arrow.
  * shell_icon() asks IShellItemImageFactory for a jumbo icon, which gives
    crisp 96px art instead of the 32px the classic APIs hand back.
"""
from __future__ import annotations

import ctypes
import os
import struct
from ctypes import POINTER, byref, c_int, c_void_p, wintypes

from PySide6.QtGui import QImage, QPixmap

# ----------------------------------------------------------------- .lnk parse
_HEADER_SIZE = 0x4C
_HAS_LINK_TARGET_IDLIST = 0x01
_HAS_LINK_INFO = 0x02
_VOLUME_ID_AND_LOCAL_BASE_PATH = 0x01
_ENV_BLOCK_SIGNATURE = 0xA0000001


def _cstr(blob: bytes, offset: int, wide: bool) -> str:
    if offset <= 0 or offset >= len(blob):
        return ""
    if wide:
        end = offset
        while end + 1 < len(blob) and blob[end:end + 2] != b"\x00\x00":
            end += 2
        return blob[offset:end].decode("utf-16-le", "ignore")
    end = blob.index(b"\x00", offset) if b"\x00" in blob[offset:] else len(blob)
    return blob[offset:end].decode("mbcs", "ignore")


def resolve_shortcut(path: str) -> str | None:
    """Return the file a .lnk points at, or None if it cannot be read."""
    return _resolve_from_bytes(path) or _resolve_via_com(path)


def _resolve_from_bytes(path: str) -> str | None:
    try:
        with open(path, "rb") as handle:
            blob = handle.read(64 * 1024)
    except OSError:
        return None
    if len(blob) < _HEADER_SIZE or blob[:4] != b"\x4c\x00\x00\x00":
        return None

    flags = struct.unpack_from("<I", blob, 20)[0]
    cursor = _HEADER_SIZE
    if flags & _HAS_LINK_TARGET_IDLIST:
        if cursor + 2 > len(blob):
            return None
        cursor += 2 + struct.unpack_from("<H", blob, cursor)[0]

    target = ""
    if flags & _HAS_LINK_INFO and cursor + 24 <= len(blob):
        base = cursor
        header_size = struct.unpack_from("<I", blob, base + 4)[0]
        info_flags = struct.unpack_from("<I", blob, base + 8)[0]
        if info_flags & _VOLUME_ID_AND_LOCAL_BASE_PATH:
            wide = header_size >= 0x24
            local_off = struct.unpack_from("<I", blob, base + (28 if wide else 16))[0]
            suffix_off = struct.unpack_from("<I", blob, base + (32 if wide else 24))[0]
            target = _cstr(blob, base + local_off, wide) + _cstr(blob, base + suffix_off, wide)

    if not target:
        # Shortcuts written with %ProgramFiles% style paths keep the target in
        # an EnvironmentVariableDataBlock instead of LinkInfo.
        marker = struct.pack("<I", _ENV_BLOCK_SIGNATURE)
        at = blob.find(marker)
        if at > 0:
            target = _cstr(blob, at + 4 + 260, True) or _cstr(blob, at + 4, False)

    target = os.path.expandvars(target.strip("\x00").strip())
    return target if target and os.path.exists(target) else None


# --------------------------------------------------------- IShellItemImageFactory
class GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class _BITMAP(ctypes.Structure):
    _fields_ = [("bmType", ctypes.c_long), ("bmWidth", ctypes.c_long),
                ("bmHeight", ctypes.c_long), ("bmWidthBytes", ctypes.c_long),
                ("bmPlanes", ctypes.c_ushort), ("bmBitsPixel", ctypes.c_ushort),
                ("bmBits", c_void_p)]


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32)]


SIIGBF_ICONONLY = 0x04
SIIGBF_THUMBNAILONLY = 0x08
DIB_RGB_COLORS = 0
CLSCTX_INPROC_SERVER = 1
SLGP_RAWPATH = 4
MAX_PATH = 260

_ole32 = ctypes.windll.ole32
_shell32 = ctypes.windll.shell32
_gdi32 = ctypes.windll.gdi32
_user32 = ctypes.windll.user32


def make_guid(text: str) -> GUID:
    value = GUID()
    _ole32.CLSIDFromString(text, byref(value))
    return value


_IID_IMAGE_FACTORY = make_guid("{bcc18b79-ba16-442f-80c4-8a59c30c463b}")
_CLSID_SHELL_LINK = make_guid("{00021401-0000-0000-C000-000000000046}")
_IID_SHELL_LINK_W = make_guid("{000214F9-0000-0000-C000-000000000046}")
_IID_PERSIST_FILE = make_guid("{0000010b-0000-0000-C000-000000000046}")

_GetImage = ctypes.WINFUNCTYPE(
    ctypes.HRESULT, c_void_p, _SIZE, c_int, POINTER(wintypes.HBITMAP))
_Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, c_void_p)
_QueryInterface = ctypes.WINFUNCTYPE(
    ctypes.HRESULT, c_void_p, POINTER(GUID), POINTER(c_void_p))
_Load = ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, ctypes.c_wchar_p, ctypes.c_uint32)
_GetPath = ctypes.WINFUNCTYPE(
    ctypes.HRESULT, c_void_p, ctypes.c_wchar_p, c_int, c_void_p, ctypes.c_uint32)


def _vtable(pointer):
    return ctypes.cast(pointer, POINTER(POINTER(c_void_p)))[0]


def _release(pointer) -> None:
    try:
        _Release(_vtable(pointer)[2])(pointer)
    except Exception:
        pass


def _resolve_via_com(path: str) -> str | None:
    """Shortcuts that store their target as an item-ID list need the shell to read them."""
    _ole32.CoInitializeEx(None, 0x2)  # apartment threaded; harmless if already done
    link = c_void_p()
    if _ole32.CoCreateInstance(byref(_CLSID_SHELL_LINK), None, CLSCTX_INPROC_SERVER,
                               byref(_IID_SHELL_LINK_W), byref(link)) != 0 or not link:
        return None
    persist = c_void_p()
    try:
        if _QueryInterface(_vtable(link)[0])(link, byref(_IID_PERSIST_FILE),
                                             byref(persist)) != 0 or not persist:
            return None
        if _Load(_vtable(persist)[5])(persist, path, 0) != 0:
            return None
        buffer = ctypes.create_unicode_buffer(MAX_PATH)
        if _GetPath(_vtable(link)[3])(link, buffer, MAX_PATH, None, SLGP_RAWPATH) != 0:
            return None
        target = os.path.expandvars(buffer.value.strip())
        return target if target and os.path.exists(target) else None
    except Exception:
        return None
    finally:
        if persist:
            _release(persist)
        _release(link)


def _bitmap_to_qimage(hbitmap) -> QImage | None:
    info = _BITMAP()
    if not _gdi32.GetObjectW(hbitmap, ctypes.sizeof(info), byref(info)):
        return None
    width, height = info.bmWidth, info.bmHeight
    if width <= 0 or height <= 0:
        return None

    header = _BITMAPINFOHEADER()
    header.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    header.biWidth = width
    header.biHeight = -height  # top-down
    header.biPlanes = 1
    header.biBitCount = 32
    header.biCompression = 0

    buffer = ctypes.create_string_buffer(width * height * 4)
    screen_dc = _user32.GetDC(None)
    try:
        copied = _gdi32.GetDIBits(screen_dc, hbitmap, 0, height, buffer,
                                  byref(header), DIB_RGB_COLORS)
    finally:
        _user32.ReleaseDC(None, screen_dc)
    if not copied:
        return None

    image = QImage(buffer.raw, width, height, width * 4,
                   QImage.Format_ARGB32_Premultiplied)
    return image.copy()  # detach from the temporary buffer


def shell_icon(path: str, size: int = 96, icon_only: bool = True) -> QPixmap | None:
    """Ask the shell for the best art for a file: its icon, or a real thumbnail."""
    factory = c_void_p()
    hresult = _shell32.SHCreateItemFromParsingName(
        ctypes.c_wchar_p(path), None, byref(_IID_IMAGE_FACTORY), byref(factory))
    if hresult != 0 or not factory:
        return None
    try:
        vtable = ctypes.cast(factory, POINTER(POINTER(c_void_p)))[0]
        hbitmap = wintypes.HBITMAP()
        flags = SIIGBF_ICONONLY if icon_only else SIIGBF_THUMBNAILONLY
        if _GetImage(vtable[3])(factory, _SIZE(size, size), flags,
                                byref(hbitmap)) != 0:
            return None
        try:
            image = _bitmap_to_qimage(hbitmap)
        finally:
            _gdi32.DeleteObject(hbitmap)
        if image is None or image.isNull():
            return None
        return QPixmap.fromImage(image)
    except Exception:
        return None
    finally:
        try:
            _Release(ctypes.cast(factory, POINTER(POINTER(c_void_p)))[0][2])(factory)
        except Exception:
            pass
