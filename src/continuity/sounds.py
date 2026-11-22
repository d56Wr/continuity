"""Alert sounds: a choice of tones from the installed sound themes, or a custom file.

A sound id is "<theme>/<name>" (e.g. "ocean/message-new-instant"), an absolute path to a
custom file, or "" for silence. Nothing plays while the desktop is in Do Not Disturb mode.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import QObject, QProcess

from .core import dbus

DIRS = (Path.home() / ".local/share/sounds", Path("/usr/share/sounds"))

# (id, English label) — shown only if the file is installed
MESSAGE_SOUNDS = [
    ("ocean/message-new-instant", "Ocean · New Message"),
    ("ocean/message-contact-in", "Ocean · Contact"),
    ("ocean/message-highlight", "Ocean · Highlight"),
    ("ocean/message-attention", "Ocean · Attention"),
    ("ocean/message-new-email", "Ocean · Mail"),
    ("ocean/dialog-information", "Ocean · Info"),
    ("ocean/bell", "Ocean · Bell"),
    ("freedesktop/message-new-instant", "Classic · New Message"),
    ("freedesktop/message", "Classic · Message"),
    ("freedesktop/complete", "Classic · Complete"),
    ("freedesktop/window-attention", "Classic · Attention"),
    ("freedesktop/bell", "Classic · Bell"),
]
RING_SOUNDS = [
    ("ocean/phone-incoming-call", "Ocean · Ringtone"),
    ("freedesktop/phone-incoming-call", "Classic · Ringtone"),
    ("freedesktop/phone-outgoing-calling", "Classic · Calling"),
    ("ocean/alarm-clock-elapsed", "Ocean · Alarm"),
    ("freedesktop/alarm-clock-elapsed", "Classic · Alarm"),
    ("ocean/bell", "Ocean · Bell"),
]
DEFAULT_MESSAGE = "ocean/message-new-instant"
DEFAULT_RING = "ocean/phone-incoming-call"


def resolve(sound: str) -> str:
    """File path for a sound id ("" if none/missing)."""
    if not sound:
        return ""
    if sound.startswith("/"):
        return sound if Path(sound).is_file() else ""
    theme, _, name = sound.partition("/")
    for d in DIRS:
        for ext in ("oga", "ogg", "wav"):
            f = d / theme / "stereo" / f"{name}.{ext}"
            if f.exists():
                return str(f)
    return ""


def choices(table: list[tuple[str, str]]) -> list[tuple[str, str]]:
    return [(sid, label) for sid, label in table if resolve(sid)]


def _do_not_disturb() -> bool:
    return bool(dbus.get("org.freedesktop.Notifications", "/org/freedesktop/Notifications",
                         "org.freedesktop.Notifications", "Inhibited", False))


class Sounds(QObject):
    def __init__(self, message: str, ring: str, parent=None):
        super().__init__(parent)
        self.message = message
        self.ringtone = ring
        self._ring: QProcess | None = None
        self._ringing = False

    @staticmethod
    def _command(sound: str) -> list[str]:
        f = resolve(sound)
        player = shutil.which("pw-play") or shutil.which("paplay")
        return [player, f] if f and player else []

    def preview(self, sound: str) -> None:
        cmd = self._command(sound)
        if cmd:
            QProcess.startDetached(cmd[0], cmd[1:])

    def play_message(self) -> None:
        if not _do_not_disturb():
            self.preview(self.message)

    def ring(self) -> None:
        if self._ringing or not self.ringtone or _do_not_disturb():
            return
        self._ringing = True
        self._ring_once()

    def _ring_once(self) -> None:
        cmd = self._command(self.ringtone)
        if not self._ringing or not cmd:
            return
        p = QProcess(self)
        p.finished.connect(lambda *a: (p.deleteLater(), self._ring_once()))
        self._ring = p
        p.start(cmd[0], cmd[1:])

    def stop_ring(self) -> None:
        self._ringing = False
        if self._ring and self._ring.state() != QProcess.ProcessState.NotRunning:
            self._ring.kill()
        self._ring = None
