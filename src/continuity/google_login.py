"""Google account sign-in for Google Messages pairing.

Google refuses sign-in inside embedded browsers, so we open a real Chromium-based
browser (Edge, Chrome, Chromium, Brave, Vivaldi) with a *separate, throw-away profile*
used only for this. The profile uses the "basic" password store, so its cookie
database is encrypted with Chromium's well-known fallback key instead of the user's
keyring. Once the Google cookies appear we hand the encrypted rows to the helper,
close that browser window and delete the profile after pairing.
"""
from __future__ import annotations

import base64
import logging
import shutil
import sqlite3
import tempfile
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

from .gmessages import DATA

log = logging.getLogger(__name__)

PROFILE = DATA / "google-login"
START_URL = "https://accounts.google.com/AccountChooser?continue=https://messages.google.com/web/config"
BROWSERS = ["microsoft-edge-stable", "microsoft-edge", "google-chrome-stable", "google-chrome",
            "chromium", "brave", "brave-browser", "vivaldi-stable"]
REQUIRED = {"SID", "HSID", "SSID", "APISID", "SAPISID", "OSID"}


def find_browser() -> str | None:
    return next((p for b in BROWSERS if (p := shutil.which(b))), None)


class GoogleLogin(QObject):
    cookiesReady = Signal(list, int)   # encrypted rows, cookie DB schema version
    failed = Signal(str)
    stateChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.browser = find_browser()
        self._proc: QProcess | None = None
        self._timer = QTimer(self, interval=2500, timeout=self._poll)
        self.active = False

    @property
    def available(self) -> bool:
        return self.browser is not None

    def start(self) -> None:
        if not self.browser:
            self.failed.emit("no_browser")
            return
        self.cancel()
        shutil.rmtree(PROFILE, ignore_errors=True)
        PROFILE.mkdir(parents=True, exist_ok=True)
        p = QProcess(self)
        p.setProgram(self.browser)
        p.setArguments([f"--user-data-dir={PROFILE}", "--password-store=basic", "--no-first-run",
                        "--no-default-browser-check", "--disable-sync", "--new-window",
                        "--class=continuity-google-login", START_URL])
        p.finished.connect(self._browser_closed)
        p.start()
        self._proc = p
        self.active = True
        self._timer.start()
        self.stateChanged.emit()

    def cancel(self) -> None:
        self._timer.stop()
        if self._proc:
            self._proc.finished.disconnect(self._browser_closed)
            self._proc.terminate()
            if not self._proc.waitForFinished(3000):
                self._proc.kill()
            self._proc = None
        if self.active:
            self.active = False
            self.stateChanged.emit()

    def cleanup(self) -> None:
        """Forget the throw-away profile (after pairing the helper keeps its own session)."""
        self.cancel()
        shutil.rmtree(PROFILE, ignore_errors=True)

    def _browser_closed(self, *a) -> None:
        self._proc = None
        # one last look: cookies are flushed when the browser exits
        if not self._poll() and self.active:
            self._timer.stop()
            self.active = False
            self.stateChanged.emit()
            self.failed.emit("closed")

    def _poll(self) -> bool:
        db = next((p for p in (PROFILE / "Default" / "Network" / "Cookies", PROFILE / "Default" / "Cookies")
                   if p.exists()), None)
        if not db:
            return False
        rows, version = self._read(db)
        names = {r["name"] for r in rows if r["value"] or r["enc"]}
        if not REQUIRED <= names:
            return False
        log.info("Google sign-in cookies found")
        self._timer.stop()
        self.active = False
        self.cookiesReady.emit(rows, version)
        if self._proc:
            self._proc.finished.disconnect(self._browser_closed)
            self._proc.terminate()
            self._proc = None
        self.stateChanged.emit()
        return True

    @staticmethod
    def _read(db: Path) -> tuple[list[dict], int]:
        # the browser keeps the database open; read a private copy (with its WAL)
        with tempfile.TemporaryDirectory() as tmp:
            for suffix in ("", "-wal", "-journal"):
                src = Path(str(db) + suffix)
                if src.exists():
                    shutil.copy2(src, Path(tmp) / ("Cookies" + suffix))
            try:
                con = sqlite3.connect(f"file:{Path(tmp) / 'Cookies'}?mode=ro", uri=True)
                version = int((con.execute("SELECT value FROM meta WHERE key='version'").fetchone() or [0])[0])
                cur = con.execute("SELECT name, host_key, value, encrypted_value FROM cookies "
                                  "WHERE host_key LIKE '%google.com'")
                rows = [{"name": n, "host": h, "value": v or "",
                         "enc": base64.b64encode(e or b"").decode()} for n, h, v, e in cur]
                con.close()
            except sqlite3.Error as e:
                log.debug("cookie db not readable yet: %s", e)
                return [], 0
        return rows, version
