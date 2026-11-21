"""Client for the continuity-gmessages helper (Google Messages: SMS + RCS).

The helper speaks JSON lines on stdin/stdout; this class runs it with QProcess,
matches replies to requests and re-emits events as a Qt signal.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QProcess, QTimer, Signal

log = logging.getLogger(__name__)

DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "continuity" / "gmessages"
HERE = Path(__file__).resolve().parent


def find_helper() -> str | None:
    candidates = [
        os.environ.get("CONTINUITY_GM_HELPER", ""),
        str(HERE / "bin" / "continuity-gmessages"),
        shutil.which("continuity-gmessages") or "",
        str(HERE.parent.parent / "build" / "continuity-gmessages"),  # source checkout
    ]
    return next((c for c in candidates if c and os.access(c, os.X_OK)), None)


class GMessages(QObject):
    event = Signal(str, object)       # name, data
    stateChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.helper = find_helper()
        self.paired = False
        self.connected = False
        self.running = False
        self._next_id = 1
        self._pending: dict[int, Callable[[Any, str | None], None]] = {}
        self._buf = b""
        self._proc: QProcess | None = None
        self._restarts = 0
        DATA.mkdir(parents=True, exist_ok=True)
        os.chmod(DATA, 0o700)

    @property
    def available(self) -> bool:
        return self.helper is not None

    # ------------------------------------------------------------ process
    def start(self) -> None:
        if not self.helper or self._proc:
            return
        p = QProcess(self)
        p.setProgram(self.helper)
        p.setArguments(["-session", str(DATA / "session.json"), "-media", str(DATA / "media")])
        p.setProcessChannelMode(QProcess.ProcessChannelMode.SeparateChannels)
        p.readyReadStandardOutput.connect(self._read)
        p.readyReadStandardError.connect(
            lambda: log.debug("helper: %s", bytes(p.readAllStandardError()).decode(errors="replace").rstrip()))
        p.finished.connect(self._finished)
        p.start()
        self._proc = p
        self.running = True

    def stop(self) -> None:
        if self._proc:
            self._proc.finished.disconnect(self._finished)
            self._proc.closeWriteChannel()
            if not self._proc.waitForFinished(3000):
                self._proc.kill()
            self._proc = None
        self.running = self.connected = False

    def _finished(self, code, status) -> None:
        log.warning("gmessages helper exited (%s)", code)
        self._proc = None
        self.running = self.connected = False
        for cb in self._pending.values():
            cb(None, "helper exited")
        self._pending.clear()
        self.stateChanged.emit()
        if self._restarts < 5:
            self._restarts += 1
            QTimer.singleShot(3000 * self._restarts, self.start)

    def _read(self) -> None:
        self._buf += bytes(self._proc.readAllStandardOutput())
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                log.warning("bad line from helper: %r", line[:200])
                continue
            if "id" in msg and ("ok" in msg or "error" in msg):
                cb = self._pending.pop(msg["id"], None)
                if cb:
                    cb(msg.get("result"), msg.get("error"))
                elif msg.get("error"):
                    log.warning("helper error: %s", msg["error"])
            elif "event" in msg:
                self._on_event(msg["event"], msg.get("data"))

    def _on_event(self, name: str, data) -> None:
        if name == "starting":
            self.paired = bool(data and data.get("paired"))
            self._restarts = 0
        elif name == "ready":
            self.connected = True
        elif name == "paired":
            self.paired = True
        elif name == "logged_out":
            self.paired = self.connected = False
        elif name == "error" and data and data.get("fatal"):
            self.connected = False
        elif name == "recovered":
            self.connected = True
        if name in ("starting", "ready", "paired", "logged_out", "error", "recovered"):
            self.stateChanged.emit()
        self.event.emit(name, data)

    # ------------------------------------------------------------ requests
    def request(self, cmd: str, done: Callable[[Any, str | None], None] | None = None, **params) -> None:
        if not self._proc:
            if done:
                done(None, "helper not running")
            return
        rid = self._next_id
        self._next_id += 1
        if done:
            self._pending[rid] = done
        self._proc.write((json.dumps({"id": rid, "cmd": cmd, **params}) + "\n").encode())
