"""Application entry point: single instance, tray icon, QML window."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator, QUrl, Qt, QTimer
from PySide6.QtGui import QAction, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
import shiboken6
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__, settings
from .bridge import Phone

HERE = Path(__file__).resolve().parent
APP_ID = "continuity"
SOCKET = f"continuity-{os.getuid()}"


def _send_to_running(command: str) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(SOCKET)
    if not sock.waitForConnected(300):
        return False
    sock.write(command.encode())
    sock.flush()
    sock.waitForBytesWritten(300)
    sock.disconnectFromServer()
    return True


def _icon() -> QIcon:
    icon = QIcon.fromTheme(APP_ID)
    if icon.isNull():
        icon = QIcon(str(HERE / "data" / "continuity.svg"))
    return icon


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="continuity", description="Your Android phone on the Linux desktop")
    ap.add_argument("--background", action="store_true", help="start hidden in the system tray")
    ap.add_argument("--answer", action="store_true", help="answer the ringing call (in the running instance)")
    ap.add_argument("--hangup", action="store_true", help="decline or hang up (in the running instance)")
    ap.add_argument("--toggle-call", action="store_true", help="answer if ringing, otherwise hang up")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--page", type=int, default=0, help=argparse.SUPPRESS)  # for screenshots/tests
    ap.add_argument("--screenshot", default="", help=argparse.SUPPRESS)  # grab the window to PNG and quit
    ap.add_argument("--version", action="version", version=__version__)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s: %(message)s")

    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "org.kde.desktop")
    QApplication.setDesktopFileName(APP_ID)
    try:  # optional: embedded Google Messages for Web (RCS)
        from PySide6.QtWebEngineQuick import QtWebEngineQuick
        QtWebEngineQuick.initialize()
        webengine = True
    except ImportError:
        webengine = False
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Continuity")
    app.setOrganizationName("continuity")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(_icon())
    app.setQuitOnLastWindowClosed(False)

    command = "answer" if args.answer else "hangup" if args.hangup else "toggle" if args.toggle_call else \
        "background" if args.background else "show"
    if _send_to_running(command):
        return 0
    if command in ("answer", "hangup", "toggle"):
        print("Continuity is not running", file=sys.stderr)
        return 1

    translator = QTranslator()
    lang = settings.get("language", "")
    loaded = translator.load(f"continuity_{lang}", str(HERE / "i18n")) if lang and lang != "en" else \
        False if lang == "en" else translator.load(QLocale.system(), "continuity", "_", str(HERE / "i18n"))
    if loaded:
        app.installTranslator(translator)

    phone = Phone()
    engine = QQmlApplicationEngine()
    qml_log = logging.getLogger("continuity.qml")
    engine.warnings.connect(lambda ws: [qml_log.warning(w.toString()) for w in ws])
    engine.rootContext().setContextProperty("phone", phone)
    engine.rootContext().setContextProperty("appVersion", __version__)
    engine.rootContext().setContextProperty("webEngineAvailable", webengine)
    engine.setUiLanguage(lang if lang else QLocale.system().name())
    engine.load(QUrl.fromLocalFile(str(HERE / "qml" / "Main.qml")))
    if not engine.rootObjects():
        return 1
    root = engine.rootObjects()[0]
    window = shiboken6.wrapInstance(shiboken6.getCppPointer(root)[0], QQuickWindow)
    window.setProperty("page", args.page)

    def show_window():
        window.show()
        window.raise_()
        window.requestActivate()

    phone.showWindowRequested.connect(show_window)

    server = QLocalServer()
    QLocalServer.removeServer(SOCKET)
    server.listen(SOCKET)

    def on_connection():
        sock = server.nextPendingConnection()
        sock.waitForReadyRead(300)
        cmd = bytes(sock.readAll()).decode(errors="ignore").strip()
        if cmd == "answer":
            phone.answer()
        elif cmd == "hangup":
            phone.tel.decline() or phone.hangup()
        elif cmd == "toggle":
            phone.tel.toggle()
        elif cmd != "background":
            show_window()
        sock.deleteLater()

    server.newConnection.connect(on_connection)

    tray = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = QSystemTrayIcon(_icon())
        tray.setToolTip("Continuity")
        menu = QMenu()
        menu.addAction(app.translate("tray", "Open Continuity"), show_window)
        menu.addAction(app.translate("tray", "Find my phone"), phone.ring)
        menu.addSeparator()
        quit_action = QAction(app.translate("tray", "Quit"), menu)
        quit_action.triggered.connect(app.quit)
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(lambda reason: (window.hide() if window.isVisible() else show_window())
                               if reason == QSystemTrayIcon.ActivationReason.Trigger else None)

        def update_tray():
            parts = ["Continuity"]
            if phone.connected:
                parts.append(f"{phone.deviceName} — {phone.battery}%")
            tray.setToolTip("\n".join(parts))

        phone.deviceChanged.connect(update_tray)
        update_tray()
        tray.show()
    else:
        app.setQuitOnLastWindowClosed(True)

    if not args.background or tray is None:
        show_window()

    if args.screenshot:
        def grab():
            window.grabWindow().save(args.screenshot)
            app.quit()
        QTimer.singleShot(int(os.environ.get("CONTINUITY_SHOT_DELAY", "7000")), grab)

    signal.signal(signal.SIGINT, lambda *a: app.quit())
    signal.signal(signal.SIGTERM, lambda *a: app.quit())
    QTimer(app, interval=500, timeout=lambda: None).start()  # let Python see signals
    app.aboutToQuit.connect(phone.shutdown)
    code = app.exec()
    server.close()
    return code
