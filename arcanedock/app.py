"""Application entry point: single instance, fences on the desktop, tray menu."""
from __future__ import annotations

import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import shellops
from .config import APP_NAME, APP_TITLE, Store
from .accentwatch import AccentWatcher
from .desktopclick import DesktopDoubleClick
from .fences import FenceManager
from .ui import theme
from .tray import Tray, make_icon

SERVER_NAME = f"{APP_NAME}.singleton"


def _already_running(command: bytes = b"show") -> bool:
    """A second launch talks to the instance that is already up."""
    socket = QLocalSocket()
    socket.connectToServer(SERVER_NAME)
    if socket.waitForConnected(250):
        socket.write(command)
        socket.flush()
        socket.waitForBytesWritten(250)
        socket.disconnectFromServer()
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    wants_quit = "--quit" in argv

    app = QApplication(argv)
    app.setApplicationName(APP_TITLE)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(make_icon())

    if _already_running(b"quit" if wants_quit else b"show"):
        return 0
    if wants_quit:
        return 0  # nothing was running
    QLocalServer.removeServer(SERVER_NAME)
    server = QLocalServer()
    server.listen(SERVER_NAME)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, APP_TITLE, "No system tray is available on this desktop.")
        return 1

    store = Store()
    # Peek hides every fence. If that state were restored at startup with the
    # Windows icons also hidden, the desktop would come up completely blank
    # with only the tray icon as a way back.
    if not store.settings["fences_visible"] and store.settings["hide_native_icons"]:
        store.settings["fences_visible"] = True

    if store.settings["system_accent"]:
        theme.set_accent(shellops.accent_color())

    manager = FenceManager(store)
    manager.start()

    if store.settings["hide_native_icons"]:
        shellops.set_native_icons(False)

    launcher = {"window": None}

    def open_launcher() -> None:
        """The app grid is a side feature now, so it is built on first use."""
        if launcher["window"] is None:
            from .ui.window import DockWindow

            window = DockWindow(store)
            if not store.groups:
                window.rescan()
            launcher["window"] = window
        launcher["window"].show_dock()

    def restore_icons() -> None:
        """Never leave someone staring at an empty desktop with no way back."""
        if not shellops.native_icons_visible():
            shellops.set_native_icons(True)

    # Covers the tray's Quit, but also logging off or shutting Windows down.
    app.aboutToQuit.connect(restore_icons)

    def quit_app() -> None:
        restore_icons()
        store.save()
        tray.hide()
        manager.close_all()
        server.close()
        app.quit()

    tray = Tray(store, manager, open_launcher, quit_app)
    manager.notifier = tray.message
    tray.show()

    def refresh_accent() -> None:
        theme.set_accent(shellops.accent_color()
                         if store.settings["system_accent"] else None)
        tray.menu.setStyleSheet(theme.qss())
        manager.restyle()

    def peek() -> None:
        if store.settings["peek_on_double_click"]:
            manager.set_visible(not store.settings["fences_visible"])

    peeker = DesktopDoubleClick(peek)
    manager.peeker = peeker
    if store.settings["peek_on_double_click"]:
        peeker.start()
    app.aboutToQuit.connect(peeker.stop)

    # Follow the Windows accent colour while running, not just at startup.
    accent_watcher = AccentWatcher(refresh_accent)
    app.installNativeEventFilter(accent_watcher)
    app._accent_watcher = accent_watcher  # keep it alive

    def on_second_launch() -> None:
        connection = server.nextPendingConnection()

        def handle() -> None:
            command = bytes(connection.readAll()).strip()
            connection.deleteLater()
            if command == b"quit":
                quit_app()
            else:
                manager.set_visible(True)

        connection.readyRead.connect(handle)

    server.newConnection.connect(on_second_launch)

    if "--startup" not in argv:
        tray.message("Fences are on your desktop. Right-click one to change it.")

    return app.exec()
