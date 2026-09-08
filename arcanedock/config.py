"""Persistent configuration for Arcane Dock (JSON under %APPDATA%)."""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

APP_NAME = "ArcaneDock"
APP_TITLE = "Arcane Dock"

CONFIG_DIR = Path(os.environ.get("APPDATA") or Path.home()) / APP_NAME
CONFIG_FILE = CONFIG_DIR / "config.json"
BACKUP_FILE = CONFIG_DIR / "config.bak"

DEFAULT_SETTINGS = {
    "start_with_windows": False,
    # The point is to replace the clutter, not sit on top of it.
    "hide_native_icons": True,
    "fences_visible": True,
    "system_accent": True,
    "known_categories": [],
    "peek_on_double_click": True,
    "lock_fences": False,
    "hide_after_launch": True,
    "hide_on_focus_loss": True,
    "glass_blur": True,
    "window": {"w": 1000, "h": 620, "x": None, "y": None},
}


def new_id() -> str:
    return uuid.uuid4().hex[:12]


class Store:
    """Groups + settings, saved lazily to a single JSON file."""

    def __init__(self) -> None:
        self.fences: list[dict] = []
        self.groups: list[dict] = []
        self.settings: dict = json.loads(json.dumps(DEFAULT_SETTINGS))
        # Every path the scanner has ever offered. Keeps removed apps from
        # reappearing on the next rescan.
        self.seen: set[str] = set()
        self.load()

    # ---------- persistence ----------
    def load(self) -> None:
        try:
            data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.fences = data.get("fences") or []
        self.groups = data.get("groups") or []
        self.seen = {p.lower() for p in data.get("seen") or []}
        saved = data.get("settings") or {}
        for key, value in saved.items():
            if key in self.settings:
                self.settings[key] = value

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "settings": self.settings,
            "fences": self.fences,
            "groups": self.groups,
            "seen": sorted(self.seen),
        }
        tmp = CONFIG_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        # Keep the previous file. A layout represents real arranging work, and
        # this is the only copy of it.
        if CONFIG_FILE.exists():
            try:
                BACKUP_FILE.write_bytes(CONFIG_FILE.read_bytes())
            except OSError:
                pass
        os.replace(tmp, CONFIG_FILE)

    # ---------- groups ----------
    def group(self, group_id: str) -> dict | None:
        return next((g for g in self.groups if g["id"] == group_id), None)

    def group_by_name(self, name: str) -> dict | None:
        low = name.strip().lower()
        return next((g for g in self.groups if g["name"].lower() == low), None)

    def add_group(self, name: str, glyph: str = "\u2726") -> dict:
        group = {"id": new_id(), "name": name, "glyph": glyph, "apps": []}
        self.groups.append(group)
        return group

    def ensure_group(self, name: str, glyph: str = "\u2726") -> dict:
        return self.group_by_name(name) or self.add_group(name, glyph)

    def remove_group(self, group_id: str) -> None:
        self.groups = [g for g in self.groups if g["id"] != group_id]

    # ---------- apps ----------
    def all_apps(self):
        for group in self.groups:
            for app in group["apps"]:
                yield group, app

    def has_path(self, path: str) -> bool:
        low = path.lower()
        return any(a["path"].lower() == low for _, a in self.all_apps())

    def add_app(self, group_id: str, name: str, path: str) -> dict | None:
        group = self.group(group_id)
        if group is None or self.has_path(path):
            return None
        app = {"id": new_id(), "name": name, "path": path, "runs": 0}
        group["apps"].append(app)
        self.seen.add(path.lower())
        return app

    def remove_app(self, app_id: str) -> None:
        for group in self.groups:
            group["apps"] = [a for a in group["apps"] if a["id"] != app_id]

    def move_app(self, app_id: str, target_group_id: str) -> None:
        moved = None
        for group in self.groups:
            for app in group["apps"]:
                if app["id"] == app_id:
                    moved = app
                    break
            if moved:
                group["apps"] = [a for a in group["apps"] if a["id"] != app_id]
                break
        target = self.group(target_group_id)
        if moved and target is not None:
            target["apps"].append(moved)


    # ---------- fences ----------
    def fence(self, fence_id: str) -> dict | None:
        return next((f for f in self.fences if f["id"] == fence_id), None)

    def add_fence(self, name: str, glyph: str = "✦", rect=None,
                  categories=None, catch_all: bool = False) -> dict:
        fence = {
            "id": new_id(),
            "name": name,
            "glyph": glyph,
            "rect": rect or [60, 60, 300, 260],
            "collapsed": False,
            "categories": list(categories or []),
            "pinned": [],
            "catch_all": catch_all,
        }
        self.fences.append(fence)
        return fence

    def remove_fence(self, fence_id: str) -> None:
        self.fences = [f for f in self.fences if f["id"] != fence_id]
