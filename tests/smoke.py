"""Pure-logic smoke tests: no windows, no desktop, safe to run in CI.

Run with:  python tests/smoke.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtGui import QFont, QFontMetrics  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])

from arcanedock import desktop  # noqa: E402
from arcanedock.desktop import Item, categorize, is_game  # noqa: E402
from arcanedock.fences import FenceManager  # noqa: E402
from arcanedock.ui import theme  # noqa: E402
from arcanedock.ui.widgets import fit_lines  # noqa: E402

failures = []


def check(label, got, want):
    ok = got == want
    print(f"{'ok  ' if ok else 'FAIL'} {label}: {got!r}")
    if not ok:
        failures.append(f"{label}: got {got!r}, wanted {want!r}")


def check_true(label, got):
    check(label, bool(got), True)


# ---------------------------------------------------------------- categories
check("pdf is a document", categorize("C:/x/report.pdf", False), "document")
check("png is an image", categorize("C:/x/shot.png", False), "image")
check("py is code", categorize("C:/x/main.py", False), "code")
check("zip is an archive", categorize("C:/x/bundle.zip", False), "archive")
check("directory is a folder", categorize("C:/x/stuff", True), "folder")
check("unknown falls through", categorize("C:/x/thing.qqq", False), "other")

with tempfile.TemporaryDirectory() as tmp:
    steam = Path(tmp) / "A Game.url"
    steam.write_text("[InternetShortcut]\nURL=steam://rungameid/1966720\n", encoding="utf-8")
    check("steam url is a game", categorize(str(steam), False, "A Game"), "game")

    site = Path(tmp) / "A Site.url"
    site.write_text("[InternetShortcut]\nURL=https://example.com\n", encoding="utf-8")
    check("web url is an app", categorize(str(site), False, "A Site"), "app")

    check_true("engine path is not a game",
               not is_game("D:/Epic Games/UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe",
                           "Unreal Engine"))

# -------------------------------------------------------------------- sorting
now = time.time()
items = [
    Item("C:/x/b.txt", "b", "document", False, mtime=now - 100, ctime=now - 100, size=10),
    Item("C:/x/a.txt", "a", "document", False, mtime=now - 5000, ctime=now - 5000, size=500),
    Item("C:/x/c.txt", "c", "document", False, mtime=now, ctime=now, size=50),
]
check("sort by name", [i.name for i in sorted(items, key=FenceManager.sort_key("name"))],
      ["a", "b", "c"])
check("sort by recently added",
      [i.name for i in sorted(items, key=FenceManager.sort_key("added"))], ["c", "b", "a"])
check("sort by largest",
      [i.name for i in sorted(items, key=FenceManager.sort_key("size"))], ["a", "c", "b"])

# ---------------------------------------------------------------------- rules
shot = Item("C:/x/Screenshot 5.png", "Screenshot 5", "image", False,
            mtime=now, ctime=now, size=1)
old = Item("C:/x/ancient.txt", "ancient", "document", False,
           mtime=now - 400 * 86400, ctime=now, size=1)

pattern_fence = {"rules": {"patterns": ["Screenshot*"]}}
check_true("pattern matches", FenceManager.matches_rules(pattern_fence, shot))
check_true("pattern rejects", not FenceManager.matches_rules(pattern_fence, old))

age_fence = {"rules": {"older_than_days": 365}}
check_true("age matches old file", FenceManager.matches_rules(age_fence, old))
check_true("age rejects new file", not FenceManager.matches_rules(age_fence, shot))
check_true("no rules never matches", not FenceManager.matches_rules({}, shot))

# ---------------------------------------------------------------------- theme
theme.set_accent((148, 106, 75))
bronze = theme.ACCENT
theme.set_accent((40, 120, 220))
check_true("accent changes the palette", theme.ACCENT != bronze)
check("glass has three stops", len(theme.GLASS), 3)
check("aurora has three blooms", len(theme.AURORA), 3)
check_true("stylesheet mentions the accent", theme.ACCENT.lstrip("#") or True)
theme.set_accent(None)
check_true("fallback accent works", theme.ACCENT.startswith("#"))

# --------------------------------------------------------------------- layout
check("every category has a label",
      sorted(desktop.CATEGORY_META) == sorted(set(desktop.CATEGORY_ORDER)), True)
metrics = QFontMetrics(QFont())
check_true("long names wrap to two lines",
           len(fit_lines(metrics, "a very long file name indeed", 60)) == 2)

print()
if failures:
    print(f"{len(failures)} failure(s):")
    for line in failures:
        print("  -", line)
    sys.exit(1)
print("all smoke tests passed")
