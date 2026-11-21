"""Count badge on the dock / task manager icon (com.canonical.Unity.LauncherEntry).

Plasma's task manager, Latte, Dash to Dock, Plank and others listen for the
`Update` signal and draw the number over the app's launcher icon.
"""
from __future__ import annotations

from gi.repository import GLib

from .core import dbus

IFACE = "com.canonical.Unity.LauncherEntry"
PATH = "/com/canonical/unity/launcherentry/continuity"

_last: tuple[int, bool] | None = None


def set_count(app_id: str, count: int, urgent: bool = False) -> None:
    global _last
    state = (count, urgent)
    if state == _last:
        return
    _last = state
    props = {
        "count": GLib.Variant("x", count),
        "count-visible": GLib.Variant("b", count > 0),
        "urgent": GLib.Variant("b", urgent),
    }
    try:
        dbus.bus().emit_signal(None, PATH, IFACE, "Update",
                               GLib.Variant("(sa{sv})", (f"application://{app_id}.desktop", props)))
    except GLib.Error:
        pass
