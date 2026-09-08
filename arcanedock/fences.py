"""Owns the fence windows: what goes in them, where they sit, what they do."""
from __future__ import annotations

import fnmatch
import math
import os
import time

from PySide6.QtCore import QObject, QRect
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QApplication, QInputDialog, QMessageBox,
                               QWidget)

from . import shellops
from .config import APP_TITLE, Store
from .desktop import CATEGORY_ORDER, DesktopIndex, Item, category_label
from .ui import theme
from .ui.fence import TILE_H, TILE_W, TITLE_HEIGHT, FenceWindow

GLYPHS = ["✦", "✧", "★", "☾", "❖", "⚔︎", "⚙︎", "✎︎", "◍", "▶︎", "▤", "⚜",
          "⚗︎", "♜", "⚑", "⌥"]

SORT_MODES = [
    ("name", "Name"),
    ("added", "Recently added"),
    ("modified", "Recently changed"),
    ("kind", "Kind"),
    ("size", "Largest first"),
]

COLUMN_W = 296
GAP = 16
MARGIN = 40


class FenceManager(QObject):
    def __init__(self, store: Store, parent=None):
        super().__init__(parent)
        self.store = store
        self.index = DesktopIndex(self)
        self.index.changed.connect(self.refresh)
        self.windows: dict[str, FenceWindow] = {}
        self.notifier = None
        self.peeker = None

    # ------------------------------------------------------------------ setup
    def start(self) -> None:
        if not self.store.fences:
            self.default_layout()
            self.store.save()
        self.ensure_category_fences()
        self.rebuild()

    def default_layout(self) -> None:
        """First run: one fence per kind of thing actually on the desktop."""
        counts: dict[str, int] = {}
        for item in self.index.items():
            counts[item.category] = counts.get(item.category, 0) + 1

        categories = [c for c in CATEGORY_ORDER if counts.get(c)]
        if "other" not in categories:
            categories.append("other")  # always keep a catch-all around
        categories.sort(key=lambda c: category_label(c)[0].lower())

        area = (QGuiApplication.primaryScreen()).availableGeometry()
        x, y = area.x() + MARGIN, area.y() + MARGIN
        for category in categories:
            name, glyph = category_label(category)
            height = self._height_for(counts.get(category, 0))
            if y + height > area.bottom() - MARGIN:
                x += COLUMN_W + GAP
                y = area.y() + MARGIN
            self.store.add_fence(name, glyph, [x, y, COLUMN_W, height],
                                 categories=[category],
                                 catch_all=(category == "other"))
            y += height + GAP

    @staticmethod
    def _height_for(count: int, width: int = COLUMN_W) -> int:
        # Mirrors what the flow layout will actually fit: fence width less the
        # body margins, the grid margin and room for a scrollbar, so the column
        # count does not change the moment a fence overflows.
        usable = width - 28
        columns = max(1, (usable + 6) // (TILE_W + 6))
        rows = max(1, math.ceil(count / columns))
        return int(min(max(TITLE_HEIGHT + rows * (TILE_H + 6) + 20, 150), 500))

    def _free_slot(self, height: int) -> list[int]:
        """First spot on the primary screen that does not overlap a fence."""
        area = QGuiApplication.primaryScreen().availableGeometry()
        taken = [QRect(*f["rect"]) for f in self.store.fences]
        x = area.x() + MARGIN
        while x + COLUMN_W < area.right():
            y = area.y() + MARGIN
            while y + height < area.bottom():
                candidate = QRect(x, y, COLUMN_W, height)
                if not any(candidate.intersects(other) for other in taken):
                    return [x, y, COLUMN_W, height]
                y += 40
            x += COLUMN_W + GAP
        return [area.x() + MARGIN, area.y() + MARGIN, COLUMN_W, height]

    def ensure_category_fences(self) -> bool:
        """Give a newly-seen kind of item its own fence, once.

        Without this, a kind added in a later version (Games, System) would
        silently fall into the catch-all fence for anyone who already has a
        layout. Recorded in known_categories so deleting the fence sticks.
        """
        known = set(self.store.settings.get("known_categories") or [])
        items = self.index.items()
        present = {item.category for item in items}
        claimed = {c for f in self.store.fences for c in f.get("categories", [])}

        created = False
        for category in CATEGORY_ORDER:
            if category not in present or category in known or category in claimed:
                continue
            name, glyph = category_label(category)
            count = sum(1 for item in items if item.category == category)
            height = self._height_for(count)
            self.store.add_fence(name, glyph, self._free_slot(height),
                                 categories=[category])
            created = True

        self.store.settings["known_categories"] = sorted(known | present)
        self.store.save()
        return created

    # --------------------------------------------------------------- lifecycle
    def rebuild(self) -> None:
        wanted = {f["id"] for f in self.store.fences}
        for fence_id in list(self.windows):
            if fence_id not in wanted:
                self.windows.pop(fence_id).close()
        for fence in self.store.fences:
            if fence["id"] not in self.windows:
                window = FenceWindow(fence, self)
                window.set_locked(bool(self.store.settings["lock_fences"]))
                self.windows[fence["id"]] = window
                if self.store.settings["fences_visible"]:
                    window.show()
        self.refresh()

    def refresh(self) -> None:
        placement = self.assignment()
        for fence_id, window in self.windows.items():
            window.set_items(placement.get(fence_id, []))

    @staticmethod
    def matches_rules(fence: dict, item: Item) -> bool:
        """Name-pattern and age rules, which outrank plain kind matching."""
        rules = fence.get("rules") or {}
        patterns = rules.get("patterns") or []
        older = rules.get("older_than_days") or 0
        newer = rules.get("newer_than_days") or 0
        if not patterns and not older and not newer:
            return False

        name = (item.name if item.is_shell else os.path.basename(item.path)).lower()
        if patterns and not any(fnmatch.fnmatch(name, p.lower()) for p in patterns):
            return False
        if older or newer:
            if not item.mtime:
                return False
            age_days = (time.time() - item.mtime) / 86400.0
            if older and age_days < older:
                return False
            if newer and age_days > newer:
                return False
        return True

    @staticmethod
    def sort_key(mode: str):
        if mode == "added":
            return lambda i: (-i.ctime, i.name.lower())
        if mode == "modified":
            return lambda i: (-i.mtime, i.name.lower())
        if mode == "kind":
            return lambda i: (i.category, i.name.lower())
        if mode == "size":
            return lambda i: (-i.size, i.name.lower())
        return lambda i: i.name.lower()

    def assignment(self) -> dict[str, list[Item]]:
        """Decide which fence shows each desktop item."""
        result: dict[str, list[Item]] = {f["id"]: [] for f in self.store.fences}
        pinned: dict[str, str] = {}
        for fence in self.store.fences:
            for path in fence.get("pinned", []):
                pinned[path.lower()] = fence["id"]
        catch_all = next((f["id"] for f in self.store.fences if f.get("catch_all")), None)

        for item in self.index.items():
            fence_id = pinned.get(item.key)
            if fence_id not in result:
                fence_id = None
            if fence_id is None:
                fence_id = next((f["id"] for f in self.store.fences
                                 if self.matches_rules(f, item)), None)
            if fence_id is None:
                fence_id = next((f["id"] for f in self.store.fences
                                 if item.category in f.get("categories", [])), catch_all)
            if fence_id in result:
                result[fence_id].append(item)

        for fence in self.store.fences:
            items = result.get(fence["id"])
            if items:
                items.sort(key=self.sort_key(fence.get("sort", "name")))
        return result

    def set_sort(self, fence: dict, mode: str) -> None:
        fence["sort"] = mode
        self.store.save()
        self.refresh()

    def edit_rules(self, fence: dict) -> None:
        from .ui.rules import RulesDialog

        dialog = RulesDialog(fence)
        if dialog.exec():
            fence["rules"] = dialog.rules()
            self.store.save()
            self.refresh()

    def height_for_items(self, count: int, width: int) -> int:
        return self._height_for(count, width)

    def save(self) -> None:
        self.store.save()

    def notify(self, message: str) -> None:
        if self.notifier:
            self.notifier(message)

    # ------------------------------------------------------------ item actions
    def move_item(self, path: str, fence_id: str) -> None:
        target = self.store.fence(fence_id)
        if target is None or not os.path.exists(path):
            return
        low = path.lower()
        for fence in self.store.fences:
            fence["pinned"] = [p for p in fence.get("pinned", []) if p.lower() != low]
        target.setdefault("pinned", []).append(path)
        self.store.save()
        self.refresh()

    def unpin(self, path: str) -> None:
        low = path.lower()
        for fence in self.store.fences:
            fence["pinned"] = [p for p in fence.get("pinned", []) if p.lower() != low]
        self.store.save()
        self.refresh()

    def copy_path(self, path: str) -> None:
        QApplication.clipboard().setText(path)
        self.notify("Path copied")

    def rename_item(self, item: Item) -> None:
        current = os.path.basename(item.path)
        name, ok = QInputDialog.getText(None, "Rename", "New name:", text=current)
        if not ok or not name.strip() or name.strip() == current:
            return
        renamed = shellops.rename(item.path, name.strip())
        if renamed is None:
            self.notify(f"Could not rename {current}")
            return
        for fence in self.store.fences:
            fence["pinned"] = [renamed if p.lower() == item.key else p
                               for p in fence.get("pinned", [])]
        self.store.save()
        self.index.refresh()

    def recycle_item(self, item: Item) -> None:
        confirm = QMessageBox.question(
            None, APP_TITLE,
            f"Send “{os.path.basename(item.path)}” to the Recycle Bin?")
        if confirm != QMessageBox.Yes:
            return
        if shellops.recycle([item.path]):
            self.unpin(item.path)
            self.index.refresh()
        else:
            self.notify("Delete failed")

    # ----------------------------------------------------------- fence actions
    def rename_fence(self, fence: dict) -> None:
        name, ok = QInputDialog.getText(None, "Rename fence", "Fence name:",
                                        text=fence["name"])
        if ok and name.strip():
            fence["name"] = name.strip()
            self.store.save()
            self._touch(fence)

    def change_glyph(self, fence: dict) -> None:
        glyph, ok = QInputDialog.getItem(None, "Fence sigil", "Pick a sigil:",
                                         GLYPHS, 0, False)
        if ok and glyph:
            fence["glyph"] = glyph
            self.store.save()
            self._touch(fence)

    def _touch(self, fence: dict) -> None:
        window = self.windows.get(fence["id"])
        if window:
            window.title.update()

    def category_options(self, fence: dict) -> list[tuple[str, bool]]:
        held = fence.get("categories", [])
        return [(c, c in held) for c in CATEGORY_ORDER]

    def set_category(self, fence: dict, category: str, on: bool) -> None:
        held = fence.setdefault("categories", [])
        if on and category not in held:
            held.append(category)
        elif not on and category in held:
            held.remove(category)
        self.store.save()
        self.refresh()

    def fit_to_contents(self, window: FenceWindow) -> None:
        window.resize(window.width(),
                      self._height_for(len(window.items), window.width()))
        window.persist()

    def new_fence_here(self) -> None:
        name, ok = QInputDialog.getText(None, "New fence", "Fence name:")
        if not ok or not name.strip():
            return
        fence = self.store.add_fence(name.strip(), "✦", self._free_slot(220))
        self.store.save()
        self.rebuild()
        window = self.windows.get(fence["id"])
        if window:
            window.raise_()

    def delete_fence(self, fence: dict) -> None:
        confirm = QMessageBox.question(
            None, APP_TITLE,
            f"Delete the “{fence['name']}” fence?\n\n"
            "Nothing on disk is touched - its items go back to being sorted "
            "into the other fences.")
        if confirm != QMessageBox.Yes:
            return
        self.store.remove_fence(fence["id"])
        self.store.save()
        self.rebuild()

    def rescan(self) -> None:
        self.index.refresh()
        self.refresh()

    def reset_layout(self) -> None:
        confirm = QMessageBox.question(
            None, APP_TITLE,
            "Rebuild the fences from scratch?\n\n"
            "Your fences and any items you moved by hand are forgotten. "
            "Nothing on disk changes.")
        if confirm != QMessageBox.Yes:
            return
        self.store.fences = []
        self.store.settings["known_categories"] = []
        self.default_layout()
        self.store.save()
        self.ensure_category_fences()
        self.rebuild()

    # ---------------------------------------------------------------- display
    def set_visible(self, on: bool) -> None:
        self.store.settings["fences_visible"] = bool(on)
        self.store.save()
        for window in self.windows.values():
            window.setVisible(on)

    def set_peek(self, on: bool) -> None:
        """Turning peek off removes the mouse hook, it does not just ignore it."""
        self.store.settings["peek_on_double_click"] = bool(on)
        self.store.save()
        if self.peeker is not None:
            if on:
                self.peeker.start()
            else:
                self.peeker.stop()

    def set_locked(self, on: bool) -> None:
        self.store.settings["lock_fences"] = bool(on)
        self.store.save()
        for window in self.windows.values():
            window.set_locked(on)

    def apply_glass(self) -> None:
        for window in self.windows.values():
            window.apply_glass()

    def restyle(self) -> None:
        """Re-apply the palette after the accent source changes."""
        for window in self.windows.values():
            window.setStyleSheet(theme.qss())
            window.root.discard_backdrop()
            window.apply_glass()
            for child in window.findChildren(QWidget):
                child.update()
            window.update()

    def close_all(self) -> None:
        for window in self.windows.values():
            window.close()
        self.windows.clear()
