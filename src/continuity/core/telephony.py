"""Phone calls through Bluetooth Hands-Free (PipeWire's org.pipewire.Telephony service).

The PC acts as an HFP hands-free unit for the phone. PipeWire exposes the phone as an
AudioGateway and every call as a Call object with Answer/Hangup. While a call has audio
(SCO) we link the caller's voice to a speaker sink and a microphone source to the phone.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

from gi.repository import GLib

from . import dbus

log = logging.getLogger(__name__)

SVC = "org.pipewire.Telephony"
ROOT = "/org/pipewire/Telephony"
AG_IF = "org.pipewire.Telephony.AudioGateway1"
TR_IF = "org.pipewire.Telephony.AudioGatewayTransport1"
CALL_IF = "org.pipewire.Telephony.Call1"

RINGING = ("incoming", "waiting")
IN_PROGRESS = ("active", "dialing", "alerting", "held")


@dataclass
class Call:
    path: str
    state: str
    number: str
    name: str
    incoming: bool
    since: float  # monotonic time the call entered its current state


@dataclass
class AudioRoute:
    speaker: str = ""   # sink for the caller's voice ("" = default output)
    microphone: str = ""  # source sent to the phone ("" = default input)


class Telephony:
    def __init__(self, listener: Callable[[str, object], None], route: AudioRoute | None = None):
        self._listener = listener
        self.route = route or AudioRoute()
        self.gateways: dict[str, dict] = {}
        self.calls: dict[str, Call] = {}
        self.muted = False
        self._loops: list[subprocess.Popen] = []
        self._bt_sink: str | None = None
        self._default_source_before: str | None = None
        dbus.subscribe(SVC, "org.freedesktop.DBus.ObjectManager", None, ROOT, self._changed)
        dbus.subscribe(SVC, "org.freedesktop.DBus.Properties", "PropertiesChanged", ROOT,
                       self._changed, path_prefix=True)
        dbus.watch_name(SVC, self.sync, self.sync)
        GLib.timeout_add_seconds(3, self._tick)
        GLib.idle_add(self._sync_once)  # after the owner has finished constructing

    # ------------------------------------------------------------ state
    @property
    def available(self) -> bool:
        return bool(self.gateways)

    def _changed(self, *a) -> None:
        GLib.idle_add(self._sync_once)

    def _sync_once(self) -> bool:
        self.sync()
        return False

    def _tick(self) -> bool:
        self.sync()
        return True

    def sync(self) -> None:
        objs = dbus.call(SVC, ROOT, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                         None, "(a{oa{sa{sv}}})") or {}
        gateways = {p: i[AG_IF] for p, i in objs.items() if AG_IF in i}
        calls: dict[str, Call] = {}
        for p, i in objs.items():
            if CALL_IF not in i:
                continue
            c = i[CALL_IF]
            state = c.get("State", "")
            old = self.calls.get(p)
            calls[p] = Call(p, state, c.get("LineIdentification", ""), c.get("Name", ""),
                            incoming=(old.incoming if old else state in RINGING),
                            since=old.since if old and old.state == state else time.monotonic())
        changed = gateways.keys() != self.gateways.keys() or \
            {(p, c.state) for p, c in calls.items()} != {(p, c.state) for p, c in self.calls.items()}
        self.gateways, self.calls = gateways, calls
        if changed:
            self._listener("calls", None)
        in_call = any(c.state in IN_PROGRESS for c in calls.values())
        if in_call and not self._loops:
            GLib.timeout_add(300, self._start_audio)
        elif not calls and self._loops:
            self._stop_audio()

    def ringing(self) -> Call | None:
        return next((c for c in self.calls.values() if c.state in RINGING), None)

    def current(self) -> Call | None:
        return next((c for c in self.calls.values() if c.state in IN_PROGRESS), None)

    # ------------------------------------------------------------ actions
    def answer(self) -> bool:
        c = self.ringing()
        if not c:
            return False
        dbus.call_async(SVC, c.path, CALL_IF, "Answer")
        return True

    def decline(self) -> bool:
        c = self.ringing()
        if not c:
            return False
        dbus.call_async(SVC, c.path, CALL_IF, "Hangup")
        return True

    def hangup(self) -> bool:
        if not self.calls:
            return False
        for gw in {c.path.rsplit("/", 1)[0] for c in self.calls.values()}:
            dbus.call_async(SVC, gw, AG_IF, "HangupAll")
        return True

    def toggle(self) -> bool:
        return self.answer() or self.hangup()

    def dial(self, number: str) -> bool:
        if not self.gateways:
            return False
        gw = next(iter(self.gateways))
        dbus.call_async(SVC, gw, AG_IF, "Dial", GLib.Variant("(s)", (number,)))
        return True

    def send_tones(self, tones: str) -> None:
        for gw in self.gateways:
            dbus.call_async(SVC, gw, AG_IF, "SendTones", GLib.Variant("(s)", (tones,)))

    def set_muted(self, muted: bool) -> None:
        """Mute what we send to the phone (the microphone loopback)."""
        self.muted = muted
        if self._bt_sink:
            _pactl("set-sink-mute", self._bt_sink, "1" if muted else "0")
        self._listener("calls", None)

    # ------------------------------------------------------------ audio routing
    @staticmethod
    def _bt_nodes() -> tuple[str | None, str | None]:
        try:
            dump = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True,
                                             timeout=5).stdout or "[]")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None, None
        src = sink = None
        for o in dump:
            props = (o.get("info") or {}).get("props") or {}
            if o.get("type") != "PipeWire:Interface:Node":
                continue
            name = str(props.get("node.name", ""))
            profile = str(props.get("api.bluez5.profile", ""))
            if not name.startswith("bluez_") or not any(k in profile for k in ("hfp", "hsp", "headset")):
                continue
            if props.get("media.class") == "Audio/Source":
                src = name
            elif props.get("media.class") == "Audio/Sink":
                sink = name
        return src, sink

    def _start_audio(self, attempt: int = 0) -> bool:
        if self._loops or not self.current():
            return False
        src, sink = self._bt_nodes()
        if not (src and sink):
            if attempt < 20:
                GLib.timeout_add(250, self._start_audio, attempt + 1)
            else:
                log.warning("call active but no Bluetooth audio nodes appeared")
            return False
        if not shutil.which("pw-loopback"):
            log.error("pw-loopback not found")
            return False
        self._bt_sink = sink
        self._default_source_before = _pactl("get-default-source")
        keep = ["--capture-props=node.dont-reconnect=true", "--playback-props=node.dont-reconnect=true"]
        caller = ["pw-loopback", "-n", "continuity-caller", "-C", src, *keep]
        mic = ["pw-loopback", "-n", "continuity-mic", "-P", sink, *keep]
        if self.route.speaker:
            caller += ["-P", self.route.speaker]
        if self.route.microphone:
            mic += ["-C", self.route.microphone]
        log.info("routing call audio: %s -> %s, %s -> %s", src, self.route.speaker or "default",
                 self.route.microphone or "default", sink)
        self._loops = [subprocess.Popen(caller), subprocess.Popen(mic)]
        GLib.timeout_add(1500, self._restore_default_source)
        return False

    def _restore_default_source(self) -> bool:
        before = self._default_source_before
        if before and _pactl("get-default-source") != before:
            _pactl("set-default-source", before)
        return False

    def _stop_audio(self) -> None:
        for p in self._loops:
            p.terminate()
        for p in self._loops:
            try:
                p.wait(2)
            except subprocess.TimeoutExpired:
                p.kill()
        self._loops = []
        self._bt_sink = None
        self.muted = False
        self._restore_default_source()

    def shutdown(self) -> None:
        self._stop_audio()


def _pactl(*args: str) -> str:
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""
