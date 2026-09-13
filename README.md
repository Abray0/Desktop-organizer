# Arcane Dock

[![CI](https://github.com/Abray0/Desktop-organizer/actions/workflows/ci.yml/badge.svg)](https://github.com/Abray0/Desktop-organizer/actions/workflows/ci.yml)
[![Release](https://github.com/Abray0/Desktop-organizer/actions/workflows/release.yml/badge.svg)](https://github.com/Abray0/Desktop-organizer/actions/workflows/release.yml)

Tidies a messy Windows desktop into glass **fences** — panels that sit on the
desktop itself, each holding a group of your actual files, folders and
shortcuts. Glassmorphic, with a bit of fantasy in it, and light enough to leave
running.

On first run it hides Windows' own desktop icons so the fences *replace* the
clutter rather than sit on top of it. That is a display toggle — **nothing on
your disk is moved, renamed or deleted**, the icons come back from the tray at
any time, and they are restored automatically when you quit.

## Install

**Download** the latest `ArcaneDock-windows-x64.zip` from
[Releases](../../releases), unzip it anywhere, and run `ArcaneDock.exe`.

**Or run from source** (Windows 10/11, Python 3.10+):

```powershell
git clone https://github.com/Abray0/Desktop-organizer.git
cd Desktop-organizer
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw.exe -m arcanedock     # no console window
```

or double-click **`Start Arcane Dock.bat`**, which does the last step for you.
To stop it from a terminal: `.venv\Scripts\python.exe -m arcanedock --quit`.

On first launch it reads your desktop and builds one fence per kind of thing it
finds, in alphabetical order — Apps, Archives, Code, Documents, Folders, Games,
Images, Media, System and an *Other* fence that catches anything else. Items
inside a fence are sorted alphabetically too.

**Games** are told apart from apps by where they lead, not by their name: a
shortcut is a game if it launches through a store (`steam://`,
`com.epicgames.launcher://`, and friends) or if its target lives in a game
install tree. Engines and editors are excluded, so Unreal Engine stays under
Apps. **System** holds the Recycle Bin and any other special desktop icons you
have switched on (This PC, Network, and so on).

The glass takes its colour from your **Windows accent colour** and follows it
live — change the accent in Windows Settings and the fences recolour within a
second, no restart. Untick *Use Windows accent colour* in the tray for the
original violet.

## Using it

| | |
|---|---|
| **Open something** | Double-click its tile |
| **Move a fence** | Drag its title bar (snaps to an 8px grid) |
| **Resize** | Drag the grip in the bottom-right corner |
| **Roll up / down** | Double-click the title bar — collapses to just the title |
| **Regroup an item** | Drag a tile from one fence to another, or right-click → *Move to fence* |
| **Undo that** | Right-click the tile → *Sort automatically* |
| **Fence menu** | Right-click the title bar: rename, sigil, which kinds it holds, sort order, extra rules, fit to contents, new, delete |
| **Peek at the wallpaper** | Double-click empty desktop to hide every fence; again to bring them back |
| **Item menu** | Right-click a tile: open, file location, copy path, rename, delete to Recycle Bin |
| **Show / hide all fences** | Click the tray sigil |

New files land in the right fence on their own — the desktop folders are
watched, so saving a screenshot or unzipping something updates the fences
without a rescan.

### How an item picks its fence

1. If you dragged it somewhere by hand, it stays there.
2. Otherwise, the first fence whose **extra rules** match it.
3. Otherwise, the first fence that holds its kind.
4. Anything left over goes to the catch-all fence.

A fence's kinds are editable: right-click its title → **Holds which kinds**. A
fence with no kinds ticked only ever holds what you drag into it.

### Extra rules

Right-click a fence → **Extra rules…** to catch items by more than their type:

* **Name matches** — comma-separated patterns, e.g. `Screenshot*, *.log, invoice*`
* **Not touched for N days** — an "Old stuff" fence that fills itself
* **Touched within N days** — a "Working on" fence for what is actually live

Rules outrank kinds, so a Screenshots fence beats the Images fence. Both a
pattern and an age can be set, and then both must match.

### Sort order

Right-click a fence → **Sort by**: Name, Recently added, Recently changed, Kind,
or Largest first. Each fence remembers its own choice — alphabetical for a
reference pile, *Recently added* for the fence where new downloads land.

## Tray menu

* **Show desktop fences** — hide them all without quitting
* **New fence…**, **Rescan desktop**
* **App launcher…** — the separate full-screen app grid (see below)
* **Options**
  * **Start with Windows** — one `HKCU\...\CurrentVersion\Run` entry
  * **Hide Windows desktop icons** — on by default; untick to get the ordinary
    icons back alongside the fences
  * **Lock fences in place** — stops accidental dragging
  * **Double-click desktop to peek** — on by default; see the cost below
  * **Glass blur** — Windows acrylic behind each fence
  * **Use Windows accent colour** — on by default; off gives the arcane violet
  * **Reset fence layout…** — rebuild from scratch, alphabetically

## The app launcher

The first thing I built here, kept as a side feature: a full-screen-ish window
that groups everything in your **Start Menu** (not the desktop) into Games,
Development, Internet and so on, with search. Open it from the tray. It scans
on first open, not at startup.

## Notes on weight

Measured on this machine (72 desktop items, 7 fences, 125% display scaling):

| | CPU | Memory |
|---|---|---|
| Sitting on the desktop | 0% | 77 MB private / 153 MB working set |

* **Nothing animates.** The fences are completely static, so they repaint only
  when something actually changes. An earlier build drifted glowing motes
  across each panel and that alone cost ~20% of a core with seven fences open,
  which is not what "lightweight" means.
* No polling either. The desktop folders are watched by the OS, and a burst of
  file events is collapsed into a single rescan 400 ms later.
* Each fence's gradient wash is rendered once per size and blitted after that.
* **Peek** is the one thing that costs anything at rest: watching for a
  double-click on the desktop needs a system-wide mouse hook, measured at
  **7.8 microseconds of CPU per mouse event** — roughly 0.1% of one core while
  you are actively moving the mouse, and nothing at all when you are not.
  Turning the tray option off removes the hook entirely rather than ignoring it.
* No shell extension, no service, no admin rights.
* Icons are fetched once per item and cached. Shortcut targets are read out of
  the `.lnk`, so tiles show the real app icon instead of a 32px thumbnail with
  an overlay arrow. Images and videos get real thumbnails.

## Where things live

```
arcanedock/
  app.py         entry point, single instance, tray wiring
  fences.py      fence manager: layout, assignment, item and fence actions
  desktop.py     what is on the desktop, categorised, watched for changes
  shellops.py    open/recycle/rename, desktop known-folders, icon layer, z-order
  config.py      JSON store in %APPDATA%\ArcaneDock
  winicon.py     .lnk target resolution + jumbo icons and thumbnails (ctypes)
  winblur.py     acrylic backdrop + rounded corners (ctypes)
  scanner.py     Start Menu walk, for the app launcher
  startup.py     run-at-login registry entry
  tray.py        tray icon and options
  ui/
    fence.py     the fence window and its title bar
    widgets.py   glass backdrop, flow layout, tiles
    window.py    the app launcher window
    theme.py     palette and stylesheet
```

Settings, fences and positions: `%APPDATA%\ArcaneDock\config.json`. Delete it to
start over.

## Development

```powershell
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python.exe tests\smoke.py          # pure-logic tests, no windows
.venv\Scripts\python.exe -m compileall -q arcanedock
```

`tests/smoke.py` covers the parts worth protecting: file categorisation, game
detection, the sort keys, rule matching and palette generation. It runs headless
(`QT_QPA_PLATFORM=offscreen`) and is what CI runs on every push.

To build the standalone app the way the release workflow does:

```powershell
.venv\Scripts\pyinstaller --noconfirm --clean --windowed --name ArcaneDock ^
    --collect-submodules arcanedock arcane_dock.pyw
```

Tagging `v*` and pushing runs `.github/workflows/release.yml`, which builds on
`windows-latest` and attaches the zip to a GitHub release.

Note the `.exe` is packaging convenience only — it bundles the same CPython and
Qt DLLs, so it uses the same memory as running from source.

## Requirements

Windows 10/11, Python 3.10+, PySide6-Essentials. No pywin32: every Windows call
(shell icons, `.lnk` parsing, acrylic, the desktop icon layer, the mouse hook)
goes through `ctypes`.

## Known edges

* Fences sit below normal windows and above the wallpaper. Pressing **Win+D**
  ("show desktop") may hide them along with everything else; clicking the tray
  sigil twice brings them back.
* If the app is killed rather than quit, the desktop icons stay hidden. Launch
  it again and untick *Hide Windows desktop icons*, or right-click the desktop →
  View → Show desktop icons.
* The default layout is built for the primary monitor.
* Dragging a file from Explorer onto a fence pins it there only if it already
  lives on the desktop; files elsewhere are ignored rather than moved.
* Shell locations such as the Recycle Bin can be opened and moved between
  fences, but not renamed, revealed or deleted — there is no file behind them.
* A kind of item seen for the first time gets its own fence once. Delete that
  fence and it stays deleted — it is not recreated on the next launch.
