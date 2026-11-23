"""Keep the phone's Bluetooth Hands-Free link up.

Phones rarely reconnect to a computer by themselves: Android treats it like a headset that
is expected to call back. Like a car kit, we ask BlueZ to connect the phone's Hands-Free
Audio Gateway whenever it is paired but not connected: on start, when the phone shows up
over KDE Connect (so it is nearby), after resume, and every so often in between.
"""
from __future__ import annotations

import logging
from typing import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

log = logging.getLogger(__name__)

BLUEZ = "org.bluez"
DEVICE_IF = "org.bluez.Device1"
ADAPTER_IF = "org.bluez.Adapter1"
HFP_AG = "0000111f-0000-1000-8000-00805f9b34fb"  # Hands-Free Audio Gateway (the phone side)

NEAR_INTERVAL = 30    # s between tries while KDE Connect sees the phone
FAR_INTERVAL = 120    # s between tries otherwise
MAX_INTERVAL = 600    # backoff cap after repeated failures


class BluetoothReconnect:
    def __init__(self, has_gateway: Callable[[], bool], phone_name: Callable[[], str],
                 phone_nearby: Callable[[], bool]):
        self._has_gateway = has_gateway
        self._phone_name = phone_name
        self._phone_nearby = phone_nearby
        self.enabled = True
        self._busy = False
        self._failures = 0
        self._timer = 0
        try:
            self._bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        except GLib.Error as e:
            log.info("no system bus, Bluetooth reconnect disabled: %s", e.message)
            self._bus = None
            return
        # a device or adapter changing state (phone left, adapter powered on after resume…)
        self._bus.signal_subscribe(BLUEZ, "org.freedesktop.DBus.Properties", "PropertiesChanged",
                                   None, None, Gio.DBusSignalFlags.NONE, self._on_props)
        self._schedule(5)

    # ------------------------------------------------------------ scheduling
    def poke(self) -> None:
        """Something happened that makes a connection likely to succeed now (phone seen)."""
        self._failures = 0
        self._schedule(2)

    def _schedule(self, seconds: int) -> None:
        if not self._bus:
            return
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add_seconds(seconds, self._fire)

    def _next(self) -> None:
        base = NEAR_INTERVAL if self._phone_nearby() else FAR_INTERVAL
        self._schedule(min(MAX_INTERVAL, base * 2 ** min(self._failures, 4)))

    def _fire(self) -> bool:
        self._timer = 0
        self.try_connect()
        if not self._timer:
            self._next()
        return False

    def _on_props(self, conn, sender, path, iface, signal, params) -> None:
        changed_iface, changed, _ = params.unpack()
        if changed_iface == ADAPTER_IF and changed.get("Powered") is True:
            self.poke()
        elif changed_iface == DEVICE_IF and changed.get("Connected") is False:
            self._next()  # the phone left or was disconnected: try again at the normal pace

    # ------------------------------------------------------------ connecting
    def _candidates(self) -> list[tuple[str, dict]]:
        try:
            res = self._bus.call_sync(BLUEZ, "/", "org.freedesktop.DBus.ObjectManager",
                                      "GetManagedObjects", None, None,
                                      Gio.DBusCallFlags.NONE, 3000, None)
        except GLib.Error:
            return []
        objs = res.unpack()[0]
        powered = {p for p, i in objs.items() if i.get(ADAPTER_IF, {}).get("Powered")}
        out = []
        for path, ifaces in objs.items():
            d = ifaces.get(DEVICE_IF)
            if not d or not d.get("Paired") or d.get("Blocked") or d.get("Connected"):
                continue
            if HFP_AG not in [u.lower() for u in d.get("UUIDs", [])]:
                continue
            if d.get("Adapter") not in powered:
                continue
            out.append((path, d))
        # the phone KDE Connect knows about first
        name = self._phone_name().casefold()
        out.sort(key=lambda pd: pd[1].get("Name", "").casefold() != name)
        return out

    def try_connect(self) -> None:
        if not self._bus or not self.enabled or self._busy or self._has_gateway():
            return
        devices = self._candidates()
        if not devices:
            return
        path, d = devices[0]
        log.info("connecting Bluetooth Hands-Free to %s", d.get("Name", path))
        self._busy = True

        def done(conn, result):
            self._busy = False
            try:
                conn.call_finish(result)
                self._failures = 0
                log.info("Bluetooth Hands-Free connected")
            except GLib.Error as e:
                self._failures += 1
                log.info("Bluetooth connect failed: %s", e.message)

        self._bus.call(BLUEZ, path, DEVICE_IF, "ConnectProfile", GLib.Variant("(s)", (HFP_AG,)),
                       None, Gio.DBusCallFlags.NONE, 20000, None, done)
