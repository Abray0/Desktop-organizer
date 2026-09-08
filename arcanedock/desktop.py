"""What is actually sitting on the desktop, sorted into kinds and kept in sync."""
from __future__ import annotations

import os
from dataclasses import dataclass

from PySide6.QtCore import QFileSystemWatcher, QObject, QTimer, Signal

from . import shellops

# Display name and sigil for each kind, in the order fences get laid out.
CATEGORY_META: dict[str, tuple[str, str]] = {
    "folder": ("Folders", "▤"),
    "app": ("Apps", "⚙︎"),
    "game": ("Games", "⚔︎"),
    "document": ("Documents", "✎︎"),
    "code": ("Code", "⌥"),
    "image": ("Images", "◍"),
    "media": ("Media", "▶︎"),
    "archive": ("Archives", "❖"),
    "system": ("System", "◈"),
    "other": ("Other", "✦"),
}
CATEGORY_ORDER = list(CATEGORY_META)

EXTENSIONS: dict[str, str] = {}
for _category, _exts in {
    "app": ".lnk .exe .url .bat .cmd .msi .appref-ms .ps1",
    "document": ".pdf .doc .docx .txt .md .rtf .odt .xls .xlsx .csv .ppt .pptx "
                ".epub .one .pub .vsd .tex",
    "code": ".py .js .ts .tsx .jsx .json .html .htm .css .java .c .h .cpp .cs .go "
            ".rs .rb .php .sh .yml .yaml .xml .sql .ipynb .toml .pem .key .env",
    "image": ".png .jpg .jpeg .gif .bmp .webp .svg .psd .ai .tif .tiff .ico .heic .raw",
    "media": ".mp4 .mkv .avi .mov .webm .wmv .flv .mp3 .wav .flac .m4a .ogg .aac .m4v",
    "archive": ".zip .rar .7z .tar .gz .bz2 .iso .cab .xz",
}.items():
    for _ext in _exts.split():
        EXTENSIONS[_ext] = _category

# Never worth showing.
IGNORED_NAMES = {"desktop.ini", "thumbs.db", ".ds_store"}

# Categories whose tiles look better as a real thumbnail than as a generic icon.
THUMBNAIL_CATEGORIES = {"image", "media"}


# Desktop icons that are shell locations rather than files. Windows draws these
# in the same icon layer we hide, so they have to be re-offered here.
SHELL_ICONS: list[tuple[str, str, bool]] = [
    ("Recycle Bin", "{645FF040-5081-101B-9F08-00AA002F954E}", True),
    ("This PC", "{20D04FE0-3AEA-1069-A2D8-08002B30309D}", False),
    ("Home", "{59031a47-3f72-44a7-89c5-5595fe6b30ee}", False),
    ("Network", "{F02C1A0D-BE21-4350-88B0-7367FC96EF3C}", False),
    ("Control Panel", "{5399E694-6CE5-4D6C-8FCE-1D8870FDCBA0}", False),
]
HIDE_ICONS_KEY = (r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                  r"\HideDesktopIcons\NewStartPanel")


@dataclass(frozen=True)
class Item:
    path: str
    name: str
    category: str
    is_dir: bool
    mtime: float = 0.0
    ctime: float = 0.0
    size: int = 0

    @property
    def key(self) -> str:
        return self.path.lower()

    @property
    def is_shell(self) -> bool:
        """Shell locations cannot be renamed, revealed or recycled."""
        return self.path.startswith("::")

    @property
    def wants_thumbnail(self) -> bool:
        return self.category in THUMBNAIL_CATEGORIES


# A shortcut is a game if it launches through a store, or if it lives in one
# of the usual game install trees.
GAME_URL_SCHEMES = ("steam:", "com.epicgames.launcher:", "uplay:", "origin:",
                    "gog:", "battlenet:", "roblox-player:", "minecraft:", "egs:")
# Matched against the target path with separators normalised to "/".
GAME_PATH_MARKERS = ("steamapps", "/steam/", "/epic games/", "/riot games/",
                     "/gog galaxy/", "/battle.net/", "/ubisoft/", "/ea games/",
                     "/origin games/", "/rockstar games/", "/games/",
                     "minecraft", "roblox")
# Game engines and editors live under the same trees but are not games.
NOT_GAME_MARKERS = ("engine/binaries", "unrealeditor", "ue4editor", "unityhub",
                    "/unity/", "/sdk/", "devkit")
GAME_NAME_HINTS = ("valorant", "albion", "plutonium", "league of legends", "minecraft",
                   "roblox", "steam", "epic games", "riot", "battle.net", "gog galaxy",
                   "ubisoft", "xbox", "among us", "fortnite", "call of duty",
                   "counter-strike", "dota", "genshin", "wuthering waves",
                   "lethal company", "the finals", "playnite")

# Resolving a shortcut costs a file read, so remember the verdict per file.
_game_cache: dict[str, tuple[float, bool]] = {}


def _looks_like_game(path: str, name: str) -> bool:
    lower = path.lower()
    if lower.endswith(".url"):
        try:
            with open(path, encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    if line.lower().startswith("url="):
                        target = line.split("=", 1)[1].strip().lower()
                        return target.startswith(GAME_URL_SCHEMES)
        except OSError:
            return False
        return False

    target = ""
    if lower.endswith(".lnk"):
        from .winicon import resolve_shortcut
        target = (resolve_shortcut(path) or "").lower()
    elif lower.endswith(".exe"):
        target = lower
    target = target.replace("\\", "/")

    if target:
        if any(marker in target for marker in NOT_GAME_MARKERS):
            return False
        if any(marker in target for marker in GAME_PATH_MARKERS):
            return True

    hay = name.lower()
    return any(hint in hay for hint in GAME_NAME_HINTS)


def is_game(path: str, name: str) -> bool:
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        stamp = 0.0
    cached = _game_cache.get(path)
    if cached is not None and cached[0] == stamp:
        return cached[1]
    verdict = _looks_like_game(path, name)
    _game_cache[path] = (stamp, verdict)
    return verdict


def categorize(path: str, is_dir: bool, name: str = "") -> str:
    if is_dir:
        return "folder"
    category = EXTENSIONS.get(os.path.splitext(path)[1].lower(), "other")
    if category == "app" and is_game(path, name):
        return "game"
    return category


def category_label(category: str) -> tuple[str, str]:
    return CATEGORY_META.get(category, CATEGORY_META["other"])


def shell_items() -> list[Item]:
    """The special desktop icons Windows is currently set to show."""
    import winreg

    hidden: dict[str, int] = {}
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, HIDE_ICONS_KEY) as key:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError:
                    break
                hidden[name.upper()] = value
                index += 1
    except OSError:
        pass

    found = []
    for label, clsid, shown_by_default in SHELL_ICONS:
        state = hidden.get(clsid.upper())
        if shown_by_default if state is None else state == 0:
            found.append(Item("::" + clsid, label, "system", True))
    return found


def scan() -> list[Item]:
    """Every visible thing on the desktop, folders first then alphabetical."""
    items: dict[str, Item] = {item.key: item for item in shell_items()}
    for root in shellops.desktop_dirs():
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for entry in entries:
            if entry.name.lower() in IGNORED_NAMES or entry.name.startswith("~$"):
                continue
            try:
                stat = entry.stat(follow_symlinks=False)
            except OSError:
                stat = None
            if stat is not None and getattr(stat, "st_file_attributes", 0) & 0x2:
                continue  # hidden
            is_dir = entry.is_dir()
            name = entry.name if is_dir else os.path.splitext(entry.name)[0]
            item = Item(entry.path, name,
                        categorize(entry.path, is_dir, name), is_dir,
                        mtime=stat.st_mtime if stat else 0.0,
                        ctime=stat.st_ctime if stat else 0.0,
                        size=0 if is_dir or not stat else stat.st_size)
            items.setdefault(item.key, item)
    return sorted(items.values(), key=lambda i: i.name.lower())


class DesktopIndex(QObject):
    """Keeps the item list current as files appear and disappear."""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items: list[Item] = scan()
        self._watcher = QFileSystemWatcher(shellops.desktop_dirs(), self)
        self._watcher.directoryChanged.connect(self._queue_refresh)
        # Explorer touches the desktop folder several times per file operation,
        # so collapse a burst of notifications into one rescan.
        self._debounce = QTimer(self, singleShot=True, interval=400)
        self._debounce.timeout.connect(self.refresh)

    def _queue_refresh(self, _path: str) -> None:
        self._debounce.start()

    def refresh(self) -> None:
        fresh = scan()
        if fresh != self._items:
            self._items = fresh
            self.changed.emit()

    def items(self) -> list[Item]:
        return list(self._items)

    def categories_present(self) -> list[str]:
        present = {item.category for item in self._items}
        return [c for c in CATEGORY_ORDER if c in present]
