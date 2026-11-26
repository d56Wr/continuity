"""Phone calls through Bluetooth Hands-Free (PipeWire's org.pipewire.Telephony service).

The PC acts as an HFP hands-free unit for the phone. PipeWire exposes the phone as an
AudioGateway and every call as a Call object with Answer/Hangup. While a call has audio
(SCO) the caller's voice has to reach a speaker and a microphone has to reach the phone:
PipeWire 1.6+ exposes the call audio as ordinary streams that connect to the default devices
by themselves; older versions expose a source/sink pair that we link with pw-loopback.
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
CALLER_NODE = "continuity-caller-playback"  # the stream playing the caller's voice


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
        self.speaker_muted = False
        self._loops: list[subprocess.Popen] = []
        self._streams: tuple[str, str] | None = None  # (caller playback, mic capture) on PipeWire 1.6+
        self._bt_sink: str | None = None
        self._default_source_before: str | None = None
        # calls are announced by each gateway's own object manager (PipeWire 1.6+), so listen
        # below the root too
        dbus.subscribe(SVC, "org.freedesktop.DBus.ObjectManager", None, ROOT, self._changed,
                       path_prefix=True)
        dbus.subscribe(SVC, "org.freedesktop.DBus.Properties", "PropertiesChanged", ROOT,
                       self._changed, path_prefix=True)
        dbus.watch_name(SVC, self.sync, self.sync)
        GLib.timeout_add_seconds(3, self._tick)
        GLib.idle_add(self._sync_once)  # after the owner has finished constructing

    # ------------------------------------------------------------ state
    _audio_pending = False

    @property
    def _audio_on(self) -> bool:
        return bool(self._loops or self._streams)

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
        # Older PipeWire lists calls in the root object manager, newer ones only under each
        # audio gateway (/org/pipewire/Telephony/agN/callM).
        for ag in gateways:
            objs.update(dbus.call(SVC, ag, "org.freedesktop.DBus.ObjectManager", "GetManagedObjects",
                                  None, "(a{oa{sa{sv}}})") or {})
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
        if in_call and not self._audio_on and not self._audio_pending:
            self._audio_pending = True
            GLib.timeout_add(300, self._start_audio)
        elif not calls and self._audio_on:
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
        if self._streams:
            _stream_cmd("source-output", self._streams[1], "mute", "1" if muted else "0")
        elif self._bt_sink:
            _pactl("set-sink-mute", self._bt_sink, "1" if muted else "0")
        self._listener("calls", None)

    def set_speaker_muted(self, muted: bool) -> None:
        """Silence the caller's voice on this computer (the phone keeps the call)."""
        self.speaker_muted = muted
        if self._streams:
            _stream_cmd("sink-input", self._streams[0], "mute", "1" if muted else "0")
        elif self._loops:
            _mute_stream(CALLER_NODE, muted)
        self._listener("calls", None)

    # ------------------------------------------------------------ audio routing
    @staticmethod
    def _bt_nodes() -> tuple[str | None, str | None, bool]:
        """(caller's voice, to the phone, are they streams). Streams on PipeWire 1.6+."""
        try:
            dump = json.loads(subprocess.run(["pw-dump"], capture_output=True, text=True,
                                             timeout=5).stdout or "[]")
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError):
            return None, None, False
        src = sink = None
        streams = False
        for o in dump:
            props = (o.get("info") or {}).get("props") or {}
            if o.get("type") != "PipeWire:Interface:Node":
                continue
            name = str(props.get("node.name", ""))
            profile = str(props.get("api.bluez5.profile", ""))
            if not name.startswith("bluez_") or not any(k in profile for k in ("hfp", "hsp", "headset")):
                continue
            cls = props.get("media.class")
            if cls in ("Audio/Source", "Stream/Output/Audio"):
                src = name
                streams = cls.startswith("Stream")
            elif cls in ("Audio/Sink", "Stream/Input/Audio"):
                sink = name
        return src, sink, streams

    def _start_audio(self, attempt: int = 0) -> bool:
        if self._audio_on or not self.current():
            self._audio_pending = False
            return False
        src, sink, streams = self._bt_nodes()
        if not (src and sink):
            if attempt < 20:
                GLib.timeout_add(250, self._start_audio, attempt + 1)
            else:
                # the phone may keep the audio (call taken on the handset); retried on the next change
                log.info("call active but no Bluetooth audio yet")
                self._audio_pending = False
            return False
        self._audio_pending = False
        if streams:
            # PipeWire already plays the caller on the default output and records the default
            # input; only move them when the user picked other devices
            self._streams = (src, sink)
            if self.route.speaker:
                _stream_cmd("sink-input", src, "move", self.route.speaker)
            if self.route.microphone:
                _stream_cmd("source-output", sink, "move", self.route.microphone)
            if self.speaker_muted:
                _stream_cmd("sink-input", src, "mute", "1")
            if self.muted:
                _stream_cmd("source-output", sink, "mute", "1")
            log.info("call audio: %s and %s (PipeWire streams)", src, sink)
            return False
        if not shutil.which("pw-loopback"):
            log.error("pw-loopback not found")
            return False
        self._bt_sink = sink
        self._default_source_before = _pactl("get-default-source")
        keep = ["--capture-props=node.dont-reconnect=true", "--playback-props=node.dont-reconnect=true"]
        caller = ["pw-loopback", "-n", "continuity-caller", "-C", src,
                  "--capture-props=node.dont-reconnect=true",
                  f"--playback-props=node.dont-reconnect=true node.name={CALLER_NODE}"]
        mic = ["pw-loopback", "-n", "continuity-mic", "-P", sink, *keep]
        if self.route.speaker:
            caller += ["-P", self.route.speaker]
        if self.route.microphone:
            mic += ["-C", self.route.microphone]
        log.info("routing call audio: %s -> %s, %s -> %s", src, self.route.speaker or "default",
                 self.route.microphone or "default", sink)
        self._loops = [subprocess.Popen(caller), subprocess.Popen(mic)]
        GLib.timeout_add(1500, self._restore_default_source)
        if self.speaker_muted:
            GLib.timeout_add(800, lambda: _mute_stream(CALLER_NODE, True) and False)
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
        streams, self._streams = self._streams, None
        self._bt_sink = None
        self.muted = False
        self.speaker_muted = False
        if not streams:
            self._restore_default_source()

    def shutdown(self) -> None:
        self._stop_audio()


def _pactl(*args: str) -> str:
    try:
        return subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _stream_cmd(kind: str, node_name: str, action: str, value: str) -> bool:
    """pactl set-<kind>-mute / move-<kind> on a stream found by its PipeWire node.name
    (kind is "sink-input" or "source-output")."""
    try:
        items = json.loads(_pactl("-f", "json", "list", kind + "s") or "[]")
    except json.JSONDecodeError:
        return False
    for it in items:
        if (it.get("properties") or {}).get("node.name") == node_name:
            cmd = f"set-{kind}-mute" if action == "mute" else f"move-{kind}"
            _pactl(cmd, str(it["index"]), value)
            return True
    log.warning("call stream %s not found", node_name)
    return False


def _mute_stream(node_name: str, muted: bool) -> bool:
    """Mute a playback stream (sink input) by its PipeWire node.name."""
    try:
        inputs = json.loads(_pactl("-f", "json", "list", "sink-inputs") or "[]")
    except json.JSONDecodeError:
        return False
    for si in inputs:
        if (si.get("properties") or {}).get("node.name") == node_name:
            _pactl("set-sink-input-mute", str(si["index"]), "1" if muted else "0")
            return True
    log.warning("call playback stream %s not found", node_name)
    return False
