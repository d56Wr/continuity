"""Desktop notifications with actions (org.freedesktop.Notifications)."""
from __future__ import annotations

from typing import Callable

from gi.repository import GLib

from .core import dbus

SVC = "org.freedesktop.Notifications"
PATH = "/org/freedesktop/Notifications"
_handlers: dict[int, Callable[[str], None]] = {}
_subscribed = False


def _on_signal(path, sig, args) -> None:
    if sig == "ActionInvoked":
        nid, action = args
        cb = _handlers.pop(int(nid), None)
        if cb:
            cb(action)
    elif sig == "NotificationClosed":
        _handlers.pop(int(args[0]), None)


def notify(summary: str, body: str, icon: str, actions: list[tuple[str, str]],
           on_action: Callable[[str], None] | None = None, *, urgency: int = 1,
           category: str = "", resident: bool = False, replaces: int = 0) -> int:
    global _subscribed
    if not _subscribed:
        dbus.subscribe(SVC, SVC, None, PATH, _on_signal)
        _subscribed = True
    flat: list[str] = []
    for key, label in actions:
        flat += [key, label]
    hints = {"urgency": GLib.Variant("y", urgency), "desktop-entry": GLib.Variant("s", "continuity")}
    if category:
        hints["category"] = GLib.Variant("s", category)
    if resident:
        hints["resident"] = GLib.Variant("b", True)
    nid = dbus.call(SVC, PATH, SVC, "Notify", GLib.Variant(
        "(susssasa{sv}i)", ("Continuity", replaces, icon, summary, body, flat, hints, 0)), "(u)") or 0
    if nid and on_action:
        _handlers[int(nid)] = on_action
    return int(nid)


def close(nid: int) -> None:
    _handlers.pop(nid, None)
    dbus.call_async(SVC, PATH, SVC, "CloseNotification", GLib.Variant("(u)", (nid,)))
