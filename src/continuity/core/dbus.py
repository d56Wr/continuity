"""Small helpers around Gio's D-Bus API.

Qt on Linux runs its event loop on GLib, so Gio signal subscriptions made here are
dispatched from the Qt main loop without any extra integration.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

log = logging.getLogger(__name__)

_bus: Gio.DBusConnection | None = None


def bus() -> Gio.DBusConnection:
    global _bus
    if _bus is None:
        _bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return _bus


def call(service: str, path: str, iface: str, method: str,
         args: GLib.Variant | None = None, reply: str | None = None,
         timeout: int = 5000) -> Any:
    """Synchronous call; returns the unpacked reply (single value unwrapped) or None on error."""
    try:
        res = bus().call_sync(service, path, iface, method, args,
                              GLib.VariantType(reply) if reply else None,
                              Gio.DBusCallFlags.NONE, timeout, None)
    except GLib.Error as e:
        log.debug("D-Bus %s.%s on %s failed: %s", iface, method, path, e.message)
        return None
    if res is None:
        return None
    out = res.unpack()
    return out[0] if len(out) == 1 else out


def call_async(service: str, path: str, iface: str, method: str,
               args: GLib.Variant | None = None,
               done: Callable[[Any, str | None], None] | None = None,
               timeout: int = 10000) -> None:
    def _finish(conn, result):
        try:
            res = conn.call_finish(result)
            out = res.unpack() if res is not None else ()
            value = out[0] if len(out) == 1 else (out or None)
            if done:
                done(value, None)
        except GLib.Error as e:
            log.warning("D-Bus %s.%s failed: %s", iface, method, e.message)
            if done:
                done(None, e.message)

    bus().call(service, path, iface, method, args, None, Gio.DBusCallFlags.NONE,
               timeout, None, _finish)


def get_all(service: str, path: str, iface: str) -> dict:
    return call(service, path, "org.freedesktop.DBus.Properties", "GetAll",
                GLib.Variant("(s)", (iface,)), "(a{sv})") or {}


def get(service: str, path: str, iface: str, prop: str, default: Any = None) -> Any:
    v = call(service, path, "org.freedesktop.DBus.Properties", "Get",
             GLib.Variant("(ss)", (iface, prop)), "(v)")
    return default if v is None else v


def subscribe(service: str | None, iface: str | None, member: str | None,
              path: str | None, cb: Callable[..., None], *, path_prefix: bool = False) -> int:
    """Subscribe to a signal; cb(path, member, args_tuple)."""
    flags = Gio.DBusSignalFlags.NONE

    def _cb(conn, sender, obj_path, interface, signal, params):
        if path_prefix and path and not obj_path.startswith(path):
            return
        try:
            cb(obj_path, signal, params.unpack() if params is not None else ())
        except Exception:  # never let a handler kill the main loop
            log.exception("signal handler for %s.%s failed", interface, signal)

    return bus().signal_subscribe(service, iface, member, None if path_prefix else path,
                                  None, flags, _cb)


def unsubscribe(sub_id: int) -> None:
    bus().signal_unsubscribe(sub_id)


def name_has_owner(name: str) -> bool:
    return bool(call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                     "NameHasOwner", GLib.Variant("(s)", (name,)), "(b)"))


def watch_name(name: str, appeared: Callable[[], None], vanished: Callable[[], None]) -> int:
    return Gio.bus_watch_name_on_connection(bus(), name, Gio.BusNameWatcherFlags.NONE,
                                            lambda *a: appeared(), lambda *a: vanished())
