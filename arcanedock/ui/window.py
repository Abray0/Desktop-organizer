"""The dock window: groups on the left, launchable tiles on the right."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QGuiApplication
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QMenu,
                               QMessageBox, QScrollArea, QSizeGrip, QVBoxLayout,
                               QWidget)

from .. import scanner
from ..config import APP_TITLE, Store
from ..winblur import apply_acrylic
from . import theme
from ..icons import icon_for
from .widgets import FlowLayout, GlassRoot, GlyphButton, GroupRow, Tile

GLYPHS = ["✦", "✧", "★", "☾", "❖", "⚔︎",
          "⚙︎", "✎︎", "◍", "▶︎", "▤",
          "⚜", "⚗︎", "♜", "⚑", "⚡︎"]


class DockWindow(QWidget):
    def __init__(self, store: Store):
        super().__init__()
        self.store = store
        self.current_group_id: str | None = None
        self._suppress_hide = False
        self._drag_offset: QPoint | None = None

        self.setWindowTitle(APP_TITLE)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(780, 470)
        self.setStyleSheet(theme.qss())

        self._build()
        self._restore_geometry()
        self.refresh_groups()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.root = GlassRoot(self)
        self.root.setObjectName("Root")
        outer.addWidget(self.root)

        column = QVBoxLayout(self.root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(self._build_header())

        body = QHBoxLayout()
        body.setContentsMargins(14, 6, 14, 14)
        body.setSpacing(14)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_content(), 1)
        column.addLayout(body, 1)

        self.grip = QSizeGrip(self.root)
        self.grip.setFixedSize(16, 16)

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setFixedHeight(58)
        header.installEventFilter(self)
        row = QHBoxLayout(header)
        row.setContentsMargins(20, 12, 14, 8)
        row.setSpacing(10)

        title = QLabel("✦  ARCANE DOCK")
        title.setObjectName("Title")
        row.addWidget(title)
        row.addSpacing(18)

        self.search = QLineEdit()
        self.search.setObjectName("Search")
        self.search.setPlaceholderText("Search the grimoire…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.refresh_tiles)
        row.addWidget(self.search)
        row.addStretch(1)

        rescan = GlyphButton("⟳", "Rescan installed apps")
        rescan.clicked.connect(lambda: self.rescan(announce=True))
        row.addWidget(rescan)

        close = GlyphButton("✕", "Hide to tray  (stays running)", danger=True)
        close.clicked.connect(self.hide)
        row.addWidget(close)
        return header

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(212)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(2)

        caption = QLabel("GROUPS")
        caption.setObjectName("Subtle")
        caption.setContentsMargins(12, 0, 0, 6)
        layout.addWidget(caption)

        self.group_box = QVBoxLayout()
        self.group_box.setSpacing(1)
        layout.addLayout(self.group_box)
        layout.addStretch(1)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(8, 6, 0, 4)
        new_group = GlyphButton("＋", "New group")
        new_group.clicked.connect(self.new_group)
        add_row.addWidget(new_group)
        label = QLabel("New group")
        label.setObjectName("Subtle")
        add_row.addWidget(label)
        add_row.addStretch(1)
        layout.addLayout(add_row)
        return panel

    def _build_content(self) -> QWidget:
        panel = QFrame()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        head = QHBoxLayout()
        head.setContentsMargins(4, 2, 4, 0)
        self.group_title = QLabel("")
        self.group_title.setObjectName("GroupTitle")
        head.addWidget(self.group_title)
        head.addStretch(1)
        add_app = GlyphButton("＋", "Add an app to this group")
        add_app.clicked.connect(self.add_app_dialog)
        head.addWidget(add_app)
        layout.addLayout(head)

        hint = QLabel("Drop shortcuts or .exe files anywhere on this window to add them")
        hint.setObjectName("Subtle")
        hint.setContentsMargins(4, 0, 0, 2)
        layout.addWidget(hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.grid = FlowLayout(holder, margin=4, spacing=10)
        self.scroll.setWidget(holder)
        layout.addWidget(self.scroll, 1)

        self.empty = QLabel("Nothing here yet — drop an app in, or press ＋")
        self.empty.setObjectName("Empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        layout.addWidget(self.empty)
        return panel

    # ------------------------------------------------------------- rendering
    def refresh_groups(self) -> None:
        while self.group_box.count():
            item = self.group_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        ids = [g["id"] for g in self.store.groups]
        if self.current_group_id not in ids:
            self.current_group_id = ids[0] if ids else None

        for group in self.store.groups:
            row = GroupRow(group)
            row.set_selected(group["id"] == self.current_group_id)
            row.clicked.connect(self.select_group)
            row.menu_requested.connect(self.group_menu)
            self.group_box.addWidget(row)
        self.refresh_tiles()

    def select_group(self, group_id: str) -> None:
        self.current_group_id = group_id
        self.search.clear()
        for i in range(self.group_box.count()):
            row = self.group_box.itemAt(i).widget()
            if isinstance(row, GroupRow):
                row.set_selected(row.group["id"] == group_id)
        self.refresh_tiles()

    def refresh_tiles(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        query = self.search.text().strip().lower()
        if query:
            apps = [a for _, a in self.store.all_apps() if query in a["name"].lower()]
            self.group_title.setText(f"Search · {len(apps)} found")
        else:
            group = self.store.group(self.current_group_id) if self.current_group_id else None
            apps = list(group["apps"]) if group else []
            if group:
                self.group_title.setText(f"{group.get('glyph', '✦')}  {group['name']}")
            else:
                self.group_title.setText("No groups yet")

        for app in apps:
            tile = Tile(app, app["name"], icon_for(app["path"], app["name"]))
            tile.activated.connect(self.launch)
            tile.menu_requested.connect(self.app_menu)
            self.grid.addWidget(tile)

        self.empty.setVisible(not apps)
        self.scroll.setVisible(bool(apps))

    # ---------------------------------------------------------------- actions
    def launch(self, app: dict) -> None:
        path = app["path"]
        try:
            os.startfile(path)  # noqa: S606 - shell launch is the point here
        except OSError:
            try:
                subprocess.Popen([path], shell=True)
            except OSError:
                QMessageBox.warning(self, APP_TITLE,
                                    f"Could not launch:\n{path}")
                return
        app["runs"] = app.get("runs", 0) + 1
        self.store.save()
        if self.store.settings["hide_after_launch"]:
            self.hide()

    def add_app_dialog(self) -> None:
        if not self.current_group_id:
            self.new_group()
        if not self.current_group_id:
            return
        self._suppress_hide = True
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Add apps", os.environ.get("PROGRAMFILES", ""),
            "Apps and shortcuts (*.lnk *.exe *.url *.bat *.cmd);;All files (*.*)")
        self._suppress_hide = False
        self.add_paths(paths)

    def add_paths(self, paths) -> int:
        added = 0
        for path in paths:
            name = os.path.splitext(os.path.basename(path))[0]
            if self.store.add_app(self.current_group_id, name, path):
                added += 1
        if added:
            self.store.save()
            self.refresh_groups()
        return added

    def new_group(self) -> None:
        self._suppress_hide = True
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        self._suppress_hide = False
        if ok and name.strip():
            group = self.store.add_group(name.strip())
            self.store.save()
            self.current_group_id = group["id"]
            self.refresh_groups()

    def group_menu(self, group_id: str, pos: QPoint) -> None:
        group = self.store.group(group_id)
        if group is None:
            return
        menu = QMenu(self)
        rename = QAction("Rename…", menu)
        rename.triggered.connect(lambda: self._rename_group(group))
        glyph = QAction("Change glyph…", menu)
        glyph.triggered.connect(lambda: self._change_glyph(group))
        delete = QAction("Delete group", menu)
        delete.triggered.connect(lambda: self._delete_group(group))
        menu.addAction(rename)
        menu.addAction(glyph)
        menu.addSeparator()
        menu.addAction(delete)
        menu.exec(pos)

    def _rename_group(self, group: dict) -> None:
        self._suppress_hide = True
        name, ok = QInputDialog.getText(self, "Rename group", "Group name:",
                                        text=group["name"])
        self._suppress_hide = False
        if ok and name.strip():
            group["name"] = name.strip()
            self.store.save()
            self.refresh_groups()

    def _change_glyph(self, group: dict) -> None:
        self._suppress_hide = True
        glyph, ok = QInputDialog.getItem(self, "Group glyph", "Pick a sigil:",
                                         GLYPHS, 0, False)
        self._suppress_hide = False
        if ok and glyph:
            group["glyph"] = glyph
            self.store.save()
            self.refresh_groups()

    def _delete_group(self, group: dict) -> None:
        self._suppress_hide = True
        count = len(group["apps"])
        question = f"Delete “{group['name']}”?"
        if count:
            question += f"\n\n{count} shortcut(s) in it will be removed from the dock."
        confirm = QMessageBox.question(self, APP_TITLE, question)
        self._suppress_hide = False
        if confirm == QMessageBox.Yes:
            self.store.remove_group(group["id"])
            self.store.save()
            self.refresh_groups()

    def app_menu(self, app: dict, pos: QPoint) -> None:
        menu = QMenu(self)
        launch = QAction("Launch", menu)
        launch.triggered.connect(lambda: self.launch(app))
        menu.addAction(launch)

        where = QAction("Open file location", menu)
        where.triggered.connect(
            lambda: subprocess.Popen(["explorer", "/select,", os.path.normpath(app["path"])]))
        menu.addAction(where)
        menu.addSeparator()

        move = menu.addMenu("Move to group")
        for group in self.store.groups:
            if any(a["id"] == app["id"] for a in group["apps"]):
                continue
            action = QAction(f"{group.get('glyph', '✦')}  {group['name']}", move)
            action.triggered.connect(
                lambda _=False, gid=group["id"]: self._move_app(app["id"], gid))
            move.addAction(action)
        move.setEnabled(bool(move.actions()))

        rename = QAction("Rename…", menu)
        rename.triggered.connect(lambda: self._rename_app(app))
        menu.addAction(rename)
        menu.addSeparator()

        remove = QAction("Remove from dock", menu)
        remove.triggered.connect(lambda: self._remove_app(app))
        menu.addAction(remove)
        menu.exec(pos)

    def _move_app(self, app_id: str, group_id: str) -> None:
        self.store.move_app(app_id, group_id)
        self.store.save()
        self.refresh_groups()

    def _rename_app(self, app: dict) -> None:
        self._suppress_hide = True
        name, ok = QInputDialog.getText(self, "Rename", "Display name:", text=app["name"])
        self._suppress_hide = False
        if ok and name.strip():
            app["name"] = name.strip()
            self.store.save()
            self.refresh_tiles()

    def _remove_app(self, app: dict) -> None:
        self.store.remove_app(app["id"])
        self.store.save()
        self.refresh_groups()

    def rescan(self, announce: bool = False) -> int:
        """Merge newly installed apps in, leaving anything removed by hand alone."""
        added = 0
        for item in scanner.scan():
            key = item["path"].lower()
            if key in self.store.seen or self.store.has_path(item["path"]):
                continue
            group = self.store.ensure_group(item["group"], item["glyph"])
            if self.store.add_app(group["id"], item["name"], item["path"]):
                added += 1
        if added:
            self.store.save()
            self.refresh_groups()
        if announce:
            QMessageBox.information(
                self, APP_TITLE,
                f"Summoned {added} new app(s)." if added else "No new apps found.")
        return added

    # ----------------------------------------------------------------- window
    def apply_glass(self) -> None:
        enabled = bool(self.store.settings["glass_blur"])
        apply_acrylic(self, tint=theme.ACRYLIC_TINT, enabled=enabled)

    def toggle(self) -> None:
        if self.isVisible() and self.isActiveWindow():
            self.hide()
        else:
            self.show_dock()

    def show_dock(self) -> None:
        if not self.isVisible():
            self._center_on_active_screen()
        self.show()
        self.apply_glass()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def _center_on_active_screen(self) -> None:
        saved = self.store.settings["window"]
        if saved.get("x") is not None:
            self.move(saved["x"], saved["y"])
            return
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        self.move(area.center().x() - self.width() // 2,
                  area.center().y() - self.height() // 2)

    def _restore_geometry(self) -> None:
        saved = self.store.settings["window"]
        self.resize(saved.get("w", 1000), saved.get("h", 620))

    def _store_geometry(self) -> None:
        self.store.settings["window"] = {
            "w": self.width(), "h": self.height(),
            "x": self.x(), "y": self.y(),
        }

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.grip.move(self.width() - 22, self.height() - 22)

    def hideEvent(self, event):
        self._store_geometry()
        self.store.save()
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.ActivationChange and not self.isActiveWindow():
            if self.store.settings["hide_on_focus_loss"] and not self._suppress_hide:
                QTimer.singleShot(80, self._hide_if_really_inactive)
        super().changeEvent(event)

    def _hide_if_really_inactive(self):
        if self._suppress_hide or QApplication.activePopupWidget():
            return
        if not self.isActiveWindow() and self.isVisible():
            self.hide()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)

    def eventFilter(self, obj, event):
        # Drag the frameless window by its header.
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
        elif event.type() == QEvent.MouseMove and self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
        elif event.type() == QEvent.MouseButtonRelease:
            self._drag_offset = None
        return super().eventFilter(obj, event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if not self.current_group_id and paths:
            self.store.ensure_group("Other")
            self.store.save()
            self.refresh_groups()
        self.add_paths(paths)
        event.acceptProposedAction()
