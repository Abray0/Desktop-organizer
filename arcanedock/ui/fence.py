"""A fence: a glass panel that sits on the desktop and holds desktop items."""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (QFrame, QLabel, QMenu, QScrollArea, QSizeGrip,
                               QVBoxLayout, QWidget)

from .. import shellops
from ..desktop import Item, category_label
from ..icons import icon_for
from ..winblur import apply_acrylic
from . import theme
from .widgets import FlowLayout, GlassRoot, Tile

ITEM_MIME = "application/x-arcane-desktop-item"

TITLE_HEIGHT = 32
TILE_W, TILE_H, TILE_ICON = 82, 84, 36
SNAP = 8


class TitleBar(QWidget):
    """Drag handle, name, count, and the fence's own menu."""

    def __init__(self, fence: FenceWindow):
        super().__init__(fence)
        self.fence = fence
        self.setFixedHeight(TITLE_HEIGHT)
        self.setCursor(Qt.SizeAllCursor)
        self._drag: QPoint | None = None
        self.count = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.fence.locked:
            self._drag = event.globalPosition().toPoint() - self.fence.pos()

    def mouseMoveEvent(self, event):
        if self._drag is None:
            return
        target = event.globalPosition().toPoint() - self._drag
        # Snap to a small grid so fences line up without fiddling.
        self.fence.move(round(target.x() / SNAP) * SNAP,
                        round(target.y() / SNAP) * SNAP)

    def mouseReleaseEvent(self, event):
        if self._drag is not None:
            self._drag = None
            self.fence.persist()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.fence.toggle_collapsed()

    def contextMenuEvent(self, event):
        self.fence.show_menu(event.globalPos())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect())

        painter.setPen(QColor(theme.ACCENT))
        painter.drawText(QRectF(rect.left() + 14, rect.top(), 20, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft,
                         self.fence.fence.get("glyph", "✦"))

        font = QFont(self.font())
        font.setPointSizeF(9.5)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(theme.INK))
        metrics = QFontMetrics(font)
        room = int(rect.width()) - 96
        name = metrics.elidedText(self.fence.fence["name"], Qt.ElideRight, max(room, 20))
        painter.drawText(QRectF(rect.left() + 38, rect.top(), room, rect.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, name)

        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(theme.FAINT))
        painter.drawText(QRectF(rect.right() - 46, rect.top(), 32, rect.height()),
                         Qt.AlignVCenter | Qt.AlignRight, str(self.count))

        if not self.fence.collapsed:
            painter.setPen(QColor(255, 255, 255, 22))
            painter.drawLine(QPoint(int(rect.left()) + 12, int(rect.bottom())),
                             QPoint(int(rect.right()) - 12, int(rect.bottom())))


class FenceWindow(QWidget):
    """One container on the desktop. Owns no files - it only displays them."""

    def __init__(self, fence: dict, manager):
        super().__init__()
        self.fence = fence
        self.manager = manager
        self.items: list[Item] = []
        self.locked = False

        self.setWindowTitle(f"Arcane Fence - {fence['name']}")
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint
                            | Qt.WindowStaysOnBottomHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAcceptDrops(True)
        self.setMinimumSize(170, TITLE_HEIGHT)
        self.setStyleSheet(theme.qss())

        self._restoring = False
        self._save_timer = QTimer(self, singleShot=True, interval=600)
        self._save_timer.timeout.connect(self.persist)
        self._build()
        rect = fence.get("rect") or [60, 60, 300, 260]
        self._expanded_height = rect[3]
        self.setGeometry(*rect)
        if fence.get("collapsed"):
            self.apply_collapsed(True)

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.root = GlassRoot(self)
        self.root.setObjectName("Root")
        outer.addWidget(self.root)

        column = QVBoxLayout(self.root)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)

        self.title = TitleBar(self)
        column.addWidget(self.title)

        self.body = QFrame()
        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(8, 6, 6, 8)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        holder = QWidget()
        self.grid = FlowLayout(holder, margin=2, spacing=6)
        self.scroll.setWidget(holder)
        body_layout.addWidget(self.scroll)

        self.empty = QLabel("empty")
        self.empty.setObjectName("Empty")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.hide()
        body_layout.addWidget(self.empty)
        column.addWidget(self.body, 1)

        self.grip = QSizeGrip(self.root)
        self.grip.setFixedSize(14, 14)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "grip"):
            return
        self.grip.move(self.width() - 18, self.height() - 18)
        self.grip.setVisible(not self.collapsed and not self.locked)
        if not self.collapsed and not self._restoring:
            self._expanded_height = self.height()
        if hasattr(self, "_save_timer"):
            self._save_timer.start()

    def moveEvent(self, event):
        super().moveEvent(event)
        if hasattr(self, "_save_timer"):
            self._save_timer.start()

    def showEvent(self, event):
        super().showEvent(event)
        self.apply_glass()
        # Owning the window to Progman is what keeps it above the wallpaper.
        # Done inside showEvent the change is discarded by the rest of Qt's
        # show sequence, so defer it by one turn of the event loop.
        QTimer.singleShot(0, lambda: shellops.pin_to_desktop(self))

    # ------------------------------------------------------------------ state
    @property
    def collapsed(self) -> bool:
        return bool(self.fence.get("collapsed"))

    def toggle_collapsed(self) -> None:
        collapsing = not self.collapsed
        if not collapsing and self._expanded_height <= TITLE_HEIGHT + 60:
            # Never had a real height (rolled up since it was created): open it
            # at the size its contents want rather than at the minimum.
            self._expanded_height = self.manager.height_for_items(len(self.items),
                                                                  self.width())
        self.apply_collapsed(collapsing)
        self.persist()

    def apply_collapsed(self, value: bool) -> None:
        self.fence["collapsed"] = value
        self.body.setVisible(not value)
        self.grip.setVisible(not value and not self.locked)
        if value:
            self.setFixedHeight(TITLE_HEIGHT)
            return

        target = max(self._expanded_height, TITLE_HEIGHT + 60)
        # Lifting the height constraints resizes the window before we get to
        # ask for the height we actually want, and that intermediate resize
        # would otherwise be recorded as the new "expanded" height.
        self._restoring = True
        self.setMinimumHeight(TITLE_HEIGHT + 60)
        self.setMaximumHeight(16777215)
        self.resize(self.width(), target)
        self._restoring = False
        self._expanded_height = target

    def set_locked(self, value: bool) -> None:
        self.locked = value
        self.title.setCursor(Qt.ArrowCursor if value else Qt.SizeAllCursor)
        self.grip.setVisible(not self.collapsed and not value)

    def apply_glass(self) -> None:
        apply_acrylic(self, tint=theme.ACRYLIC_TINT,
                      enabled=bool(self.manager.store.settings["glass_blur"]))

    def persist(self) -> None:
        if self.collapsed:
            rect = [self.x(), self.y(), self.width(), self._expanded_height]
        else:
            rect = [self.x(), self.y(), self.width(), self.height()]
        self.fence["rect"] = rect
        self.manager.save()

    # --------------------------------------------------------------- contents
    def set_items(self, items: list[Item]) -> None:
        self.items = items
        while self.grid.count():
            entry = self.grid.takeAt(0)
            if entry.widget():
                entry.widget().deleteLater()

        for item in items:
            tile = Tile(item, item.name,
                        icon_for(item.path, item.name, thumbnail=item.wants_thumbnail),
                        width=TILE_W, height=TILE_H, icon_size=TILE_ICON,
                        double_click=True,
                        drag_data=(ITEM_MIME, item.path.encode("utf-8")))
            tile.activated.connect(self.open_item)
            tile.menu_requested.connect(self.item_menu)
            self.grid.addWidget(tile)

        self.title.count = len(items)
        self.title.update()
        self.empty.setVisible(not items)
        self.scroll.setVisible(bool(items))

    def open_item(self, item: Item) -> None:
        if not shellops.open_item(item.path):
            self.manager.notify(f"Could not open {item.name}")

    # ------------------------------------------------------------------ menus
    def item_menu(self, item: Item, pos: QPoint) -> None:
        menu = QMenu(self)
        entries = [("Open", lambda: self.open_item(item))]
        if not item.is_shell:
            entries += [
                ("Open file location", lambda: shellops.reveal(item.path)),
                ("Copy path", lambda: self.manager.copy_path(item.path)),
            ]
        for label, handler in entries:
            action = QAction(label, menu)
            action.triggered.connect(handler)
            menu.addAction(action)
        menu.addSeparator()

        move = menu.addMenu("Move to fence")
        for other in self.manager.store.fences:
            if other["id"] == self.fence["id"]:
                continue
            action = QAction(f"{other.get('glyph', '✦')}  {other['name']}", move)
            action.triggered.connect(
                lambda _=False, fid=other["id"]: self.manager.move_item(item.path, fid))
            move.addAction(action)
        move.setEnabled(bool(move.actions()))

        auto = QAction("Sort automatically", menu)
        auto.triggered.connect(lambda: self.manager.unpin(item.path))
        menu.addAction(auto)

        # The Recycle Bin and friends are shell locations, not files: renaming
        # or deleting them is meaningless.
        if not item.is_shell:
            menu.addSeparator()
            rename = QAction("Rename…", menu)
            rename.triggered.connect(lambda: self.manager.rename_item(item))
            menu.addAction(rename)
            delete = QAction("Delete (to Recycle Bin)", menu)
            delete.triggered.connect(lambda: self.manager.recycle_item(item))
            menu.addAction(delete)
        menu.exec(pos)

    def show_menu(self, pos: QPoint) -> None:
        menu = QMenu(self)
        rename = QAction("Rename fence…", menu)
        rename.triggered.connect(lambda: self.manager.rename_fence(self.fence))
        menu.addAction(rename)
        glyph = QAction("Change sigil…", menu)
        glyph.triggered.connect(lambda: self.manager.change_glyph(self.fence))
        menu.addAction(glyph)
        roll = QAction("Unroll" if self.collapsed else "Roll up", menu)
        roll.triggered.connect(self.toggle_collapsed)
        menu.addAction(roll)
        menu.addSeparator()

        kinds = menu.addMenu("Holds which kinds")
        for category, checked in self.manager.category_options(self.fence):
            action = QAction(category_label(category)[0], kinds)
            action.setCheckable(True)
            action.setChecked(checked)
            action.toggled.connect(
                lambda on, c=category: self.manager.set_category(self.fence, c, on))
            kinds.addAction(action)

        from ..fences import SORT_MODES
        order = menu.addMenu("Sort by")
        current = self.fence.get("sort", "name")
        for mode, label in SORT_MODES:
            action = QAction(label, order)
            action.setCheckable(True)
            action.setChecked(mode == current)
            action.triggered.connect(
                lambda _=False, m=mode: self.manager.set_sort(self.fence, m))
            order.addAction(action)

        rules = QAction("Extra rules…", menu)
        rules.triggered.connect(lambda: self.manager.edit_rules(self.fence))
        menu.addAction(rules)

        tidy = QAction("Fit to contents", menu)
        tidy.triggered.connect(lambda: self.manager.fit_to_contents(self))
        menu.addAction(tidy)
        menu.addSeparator()

        new = QAction("New fence", menu)
        new.triggered.connect(self.manager.new_fence_here)
        menu.addAction(new)
        delete = QAction("Delete fence", menu)
        delete.triggered.connect(lambda: self.manager.delete_fence(self.fence))
        menu.addAction(delete)
        menu.exec(pos)

    # ------------------------------------------------------------- drag/drop
    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(ITEM_MIME) or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        mime = event.mimeData()
        paths = []
        if mime.hasFormat(ITEM_MIME):
            paths.append(bytes(mime.data(ITEM_MIME)).decode("utf-8"))
        elif mime.hasUrls():
            paths = [url.toLocalFile() for url in mime.urls() if url.isLocalFile()]
        for path in paths:
            self.manager.move_item(path, self.fence["id"])
        event.acceptProposedAction()
