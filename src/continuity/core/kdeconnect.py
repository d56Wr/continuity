"""KDE Connect daemon access: device state, SMS conversations, phone notifications, actions.

Plain Python with listener callbacks so it can be tested without Qt; the Qt layer
(continuity.bridge) turns the callbacks into models and signals for QML.
"""
from __future__ import annotations

import configparser
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from gi.repository import GLib

from . import dbus

log = logging.getLogger(__name__)

SVC = "org.kde.kdeconnect"
DAEMON_PATH = "/modules/kdeconnect"
DAEMON_IF = "org.kde.kdeconnect.daemon"
DEV_IF = "org.kde.kdeconnect.device"
CONV_IF = "org.kde.kdeconnect.device.conversations"
NOTIF_IF = "org.kde.kdeconnect.device.notifications"
NOTIF_ITEM_IF = "org.kde.kdeconnect.device.notifications.notification"
MPRIS_IF = "org.kde.kdeconnect.device.mprisremote"
CLIP_IF = "org.kde.kdeconnect.device.clipboard"

# Android Telephony.Sms message types
TYPE_INBOX, TYPE_SENT, TYPE_DRAFT, TYPE_OUTBOX, TYPE_FAILED, TYPE_QUEUED = 1, 2, 3, 4, 5, 6


@dataclass
class Attachment:
    part_id: int
    mime: str
    thumbnail_b64: str
    unique_id: str


@dataclass
class Message:
    event: int
    body: str
    addresses: list[str]
    date: int  # ms since epoch
    type: int
    read: bool
    thread_id: int
    uid: int
    sub_id: int
    attachments: list[Attachment] = field(default_factory=list)

    @property
    def outgoing(self) -> bool:
        return self.type in (TYPE_SENT, TYPE_OUTBOX, TYPE_FAILED, TYPE_QUEUED)

    @classmethod
    def from_dbus(cls, t) -> "Message | None":
        # (i event, s body, a(s) addresses, x date, i type, i read, x threadID, i uID, x subID, a(xsss) attachments)
        try:
            ev, body, addrs, date, typ, read, tid, uid, sub, atts = t
        except (TypeError, ValueError):
            log.debug("unexpected message shape: %r", t)
            return None
        return cls(ev, body or "", [a[0] if isinstance(a, tuple) else str(a) for a in addrs],
                   int(date), int(typ), bool(read), int(tid), int(uid), int(sub),
                   [Attachment(int(a[0]), a[1], a[2], a[3]) for a in atts])


@dataclass
class PhoneNotification:
    id: str
    app: str = ""
    title: str = ""
    text: str = ""
    ticker: str = ""
    icon: str = ""
    dismissable: bool = True
    reply_id: str = ""
    silent: bool = False
    is_conversation: bool = False


Listener = Callable[[str, object], None]


class Device:
    """One paired phone."""

    def __init__(self, device_id: str, emit: Listener):
        self.id = device_id
        self.path = f"{DAEMON_PATH}/devices/{device_id}"
        self._emit = emit
        self.name = ""
        self.reachable = False
        self.type = "phone"
        self.battery = -1
        self.charging = False
        self.network_type = ""
        self.network_strength = -1
        self.threads: dict[int, Message] = {}           # thread -> newest message
        self.messages: dict[int, dict[int, Message]] = {}  # thread -> uid -> message
        self.loaded_counts: dict[int, int] = {}
        self.notifications: dict[str, PhoneNotification] = {}
        self.media: dict = {}  # mprisremote properties of the phone's current player
        self._subs: list[int] = []
        self._subscribe()
        # refresh() is called by the owner once this object is reachable as `kc.device`

    # ------------------------------------------------------------ lifecycle
    def _subscribe(self) -> None:
        s = dbus.subscribe
        p = self.path
        self._subs += [
            s(SVC, DEV_IF, None, p, self._on_device_signal),
            s(SVC, "org.kde.kdeconnect.device.battery", "refreshed", p + "/battery", self._on_battery),
            s(SVC, "org.kde.kdeconnect.device.connectivity_report", "refreshed",
              p + "/connectivity_report", self._on_network),
            s(SVC, CONV_IF, None, p, self._on_conversation_signal),
            s(SVC, NOTIF_IF, None, p + "/notifications", self._on_notification_signal),
            s(SVC, NOTIF_ITEM_IF, "ready", p + "/notifications/", self._on_notification_ready, path_prefix=True),
            s(SVC, "org.kde.kdeconnect.device.contacts", "localCacheSynchronized", p + "/contacts",
              lambda *a: self._emit("contacts", None)),
            s(SVC, MPRIS_IF, "propertiesChanged", p + "/mprisremote", lambda *a: self._load_media()),
            s(SVC, CLIP_IF, "autoShareDisabledChanged", p + "/clipboard",
              lambda *a: self._emit("clipboard", None)),
            s(SVC, "org.kde.kdeconnect.device.conversations", "attachmentReceived", p,
              lambda path, sig, args: self._emit("attachment", args)),
        ]

    def close(self) -> None:
        for sid in self._subs:
            dbus.unsubscribe(sid)
        self._subs.clear()

    def refresh(self) -> None:
        props = dbus.get_all(SVC, self.path, DEV_IF)
        self.name = props.get("name", self.name or self.id)
        self.reachable = bool(props.get("isReachable", False))
        self.type = props.get("type", "phone")
        bat = dbus.get_all(SVC, self.path + "/battery", "org.kde.kdeconnect.device.battery")
        if bat:
            self.battery = int(bat.get("charge", -1))
            self.charging = bool(bat.get("isCharging", False))
        net = dbus.get_all(SVC, self.path + "/connectivity_report",
                           "org.kde.kdeconnect.device.connectivity_report")
        if net:
            self.network_type = net.get("cellularNetworkType", "")
            self.network_strength = int(net.get("cellularNetworkStrength", -1))
        self._emit("device", None)
        if self.reachable:
            self.load_threads()
            self.load_notifications()
            dbus.call_async(SVC, self.path + "/mprisremote", MPRIS_IF, "requestPlayerList")
            self._load_media()

    # ------------------------------------------------------------ device signals
    def _on_device_signal(self, path, sig, args) -> None:
        if sig in ("reachableChanged", "nameChanged", "pluginsChanged", "linksChanged", "pairStateChanged"):
            self.refresh()

    def _on_battery(self, path, sig, args) -> None:
        self.charging, self.battery = bool(args[0]), int(args[1])
        self._emit("device", None)

    def _on_network(self, path, sig, args) -> None:
        self.network_type, self.network_strength = args[0], int(args[1])
        self._emit("device", None)

    # ------------------------------------------------------------ conversations
    def load_threads(self) -> None:
        msgs = dbus.call(SVC, self.path, CONV_IF, "activeConversations", None, "(av)") or []
        for t in msgs:
            m = Message.from_dbus(t)
            if m:
                self._store(m, notify=False)
        self._emit("threads", None)
        dbus.call_async(SVC, self.path, CONV_IF, "requestAllConversationThreads")

    def load_thread(self, thread_id: int, count: int = 50) -> None:
        """Ask the phone for (more) messages of a thread; they arrive via conversationUpdated."""
        start = self.loaded_counts.get(thread_id, 0)
        dbus.call_async(SVC, self.path, CONV_IF, "requestConversation",
                        GLib.Variant("(xii)", (thread_id, start, start + count)))

    def _store(self, m: Message, notify: bool = True) -> None:
        bucket = self.messages.setdefault(m.thread_id, {})
        bucket[m.uid] = m
        newest = self.threads.get(m.thread_id)
        if newest is None or m.date >= newest.date:
            self.threads[m.thread_id] = m
        if notify:
            self._emit("thread", m.thread_id)

    def _on_conversation_signal(self, path, sig, args) -> None:
        if sig in ("conversationCreated", "conversationUpdated"):
            m = Message.from_dbus(args[0])
            if m:
                is_new_thread = m.thread_id not in self.threads
                newest_before = self.threads.get(m.thread_id)
                self._store(m)
                if is_new_thread or (newest_before and m.date > newest_before.date):
                    self._emit("threads", None)
                    if not m.outgoing and newest_before is not None and m.date > newest_before.date:
                        self._emit("incoming_sms", m)
        elif sig == "conversationLoaded":
            tid, count = int(args[0]), int(args[1])
            self.loaded_counts[tid] = len(self.messages.get(tid, {}))
            self._emit("thread_loaded", (tid, count))
        elif sig == "conversationRemoved":
            tid = int(args[0])
            self.threads.pop(tid, None)
            self.messages.pop(tid, None)
            self._emit("threads", None)

    def reply(self, thread_id: int, text: str, attachments: list[str] | None = None) -> None:
        atts = [GLib.Variant("s", a) for a in (attachments or [])]
        dbus.call_async(SVC, self.path, CONV_IF, "replyToConversation",
                        GLib.Variant("(xsav)", (thread_id, text, atts)))

    def send_new(self, addresses: list[str], text: str, attachments: list[str] | None = None) -> None:
        addrs = [GLib.Variant("(s)", (a,)) for a in addresses]
        atts = [GLib.Variant("s", a) for a in (attachments or [])]
        dbus.call_async(SVC, self.path, CONV_IF, "sendWithoutConversation",
                        GLib.Variant("(avsav)", (addrs, text, atts)))

    def request_attachment(self, part_id: int, unique_id: str) -> None:
        dbus.call_async(SVC, self.path, CONV_IF, "requestAttachmentFile",
                        GLib.Variant("(xs)", (part_id, unique_id)))

    # ------------------------------------------------------------ notifications
    def load_notifications(self) -> None:
        ids = dbus.call(SVC, self.path + "/notifications", NOTIF_IF, "activeNotifications", None, "(as)") or []
        self.notifications = {}
        for nid in ids:
            n = self._read_notification(nid)
            if n:
                self.notifications[nid] = n
        self._emit("notifications", None)

    def _read_notification(self, nid: str) -> PhoneNotification | None:
        p = dbus.get_all(SVC, f"{self.path}/notifications/{nid}", NOTIF_ITEM_IF)
        if not p:
            return None
        return PhoneNotification(
            id=nid, app=p.get("appName", ""), title=p.get("title", ""), text=p.get("text", ""),
            ticker=p.get("ticker", ""), icon=p.get("iconPath", "") if p.get("hasIcon") else "",
            dismissable=bool(p.get("dismissable", True)), reply_id=p.get("replyId", ""),
            silent=bool(p.get("silent", False)), is_conversation=bool(p.get("isConversation", False)))

    def _on_notification_signal(self, path, sig, args) -> None:
        if sig in ("notificationPosted", "notificationUpdated"):
            nid = args[0]
            n = self._read_notification(nid)
            if n:
                self.notifications[nid] = n
                self._emit("notifications", None)
                if sig == "notificationPosted":
                    self._emit("notification_posted", n)
        elif sig == "notificationRemoved":
            if self.notifications.pop(args[0], None) is not None:
                self._emit("notifications", None)
        elif sig == "allNotificationsRemoved":
            self.notifications.clear()
            self._emit("notifications", None)

    def _on_notification_ready(self, path, sig, args) -> None:
        nid = path.rsplit("/", 1)[-1]
        n = self._read_notification(nid)
        if n:
            self.notifications[nid] = n
            self._emit("notifications", None)

    def dismiss(self, nid: str) -> None:
        dbus.call_async(SVC, f"{self.path}/notifications/{nid}", NOTIF_ITEM_IF, "dismiss")
        # the daemon also forgets it locally; drop it right away for a snappy UI
        if self.notifications.pop(nid, None) is not None:
            self._emit("notifications", None)

    def dismiss_all(self) -> None:
        for nid, n in list(self.notifications.items()):
            if n.dismissable:
                self.dismiss(nid)

    def reply_notification(self, nid: str, text: str) -> None:
        dbus.call_async(SVC, f"{self.path}/notifications/{nid}", NOTIF_ITEM_IF, "sendReply",
                        GLib.Variant("(s)", (text,)))

    # ------------------------------------------------------------ media on the phone
    def _load_media(self) -> None:
        self.media = dbus.get_all(SVC, self.path + "/mprisremote", MPRIS_IF) if self.reachable else {}
        self._emit("media", None)

    def media_action(self, action: str) -> None:
        """PlayPause, Play, Pause, Next, Previous, Stop."""
        dbus.call_async(SVC, self.path + "/mprisremote", MPRIS_IF, "sendAction", GLib.Variant("(s)", (action,)))

    def media_set(self, prop: str, value: GLib.Variant) -> None:
        dbus.call_async(SVC, self.path + "/mprisremote", "org.freedesktop.DBus.Properties", "Set",
                        GLib.Variant("(ssv)", (MPRIS_IF, prop, value)),
                        lambda *a: self._load_media())

    # ------------------------------------------------------------ clipboard sync
    def clipboard_auto_share(self) -> bool:
        return not dbus.get(SVC, self.path + "/clipboard", CLIP_IF, "isAutoShareDisabled", True)

    def set_clipboard_auto_share(self, on: bool) -> None:
        """Same setting as KDE Connect's clipboard plugin dialog (the daemon reloads on configChanged)."""
        cfg = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kdeconnect" / self.id \
            / "kdeconnect_clipboard" / "config"
        cp = configparser.ConfigParser()
        cp.optionxform = str
        cp.read(cfg)
        if not cp.has_section("General"):
            cp.add_section("General")
        cp["General"]["autoShare"] = "true" if on else "false"
        cfg.parent.mkdir(parents=True, exist_ok=True)
        with open(cfg, "w") as f:
            cp.write(f, space_around_delimiters=False)
        dbus.bus().emit_signal(None, f"/kdeconnect/{self.id}/kdeconnect_clipboard",
                               "org.kde.kdeconnect.config", "configChanged", None)
        GLib.timeout_add(400, lambda: self._emit("clipboard", None) and False)

    # ------------------------------------------------------------ other actions
    def ring(self) -> None:
        dbus.call_async(SVC, self.path + "/findmyphone", "org.kde.kdeconnect.device.findmyphone", "ring")

    def share_urls(self, urls: list[str]) -> None:
        dbus.call_async(SVC, self.path + "/share", "org.kde.kdeconnect.device.share", "shareUrls",
                        GLib.Variant("(as)", (urls,)))

    def share_text(self, text: str) -> None:
        dbus.call_async(SVC, self.path + "/share", "org.kde.kdeconnect.device.share", "shareText",
                        GLib.Variant("(s)", (text,)))

    def browse_files(self) -> None:
        dbus.call_async(SVC, self.path + "/sftp", "org.kde.kdeconnect.device.sftp", "startBrowsing")

    def send_clipboard(self) -> None:
        dbus.call_async(SVC, self.path + "/clipboard", "org.kde.kdeconnect.device.clipboard", "sendClipboard")

    def sync_contacts(self) -> None:
        dbus.call_async(SVC, self.path + "/contacts", "org.kde.kdeconnect.device.contacts",
                        "synchronizeRemoteWithLocal")


class KDEConnect:
    """Tracks the daemon and the paired phone(s); `listener(kind, payload)` gets every change."""

    def __init__(self, listener: Listener):
        self._listener = listener
        self.available = False
        self.device: Device | None = None
        dbus.subscribe(SVC, DAEMON_IF, None, DAEMON_PATH, self._on_daemon_signal)
        dbus.watch_name(SVC, self._appeared, self._vanished)

    def _appeared(self) -> None:
        self.available = True
        self._pick_device()

    def _vanished(self) -> None:
        self.available = False
        if self.device:
            self.device.close()
            self.device = None
        self._listener("device", None)

    def _on_daemon_signal(self, path, sig, args) -> None:
        if sig in ("deviceAdded", "deviceRemoved", "deviceListChanged", "deviceVisibilityChanged"):
            self._pick_device()

    def paired_devices(self) -> dict[str, str]:
        return dbus.call(SVC, DAEMON_PATH, DAEMON_IF, "deviceNames",
                         GLib.Variant("(bb)", (False, True)), "(a{ss})") or {}

    def _pick_device(self) -> None:
        devices = self.paired_devices()
        reachable = dbus.call(SVC, DAEMON_PATH, DAEMON_IF, "devices",
                              GLib.Variant("(bb)", (True, True)), "(as)") or []
        want = next((d for d in reachable if d in devices), next(iter(devices), None))
        if self.device and self.device.id == want:
            self.device.refresh()
            return
        if self.device:
            self.device.close()
        self.device = Device(want, self._listener) if want else None
        if self.device:
            self.device.refresh()
        else:
            self._listener("device", None)


# ---------------------------------------------------------------- KDE Connect's own popups
NOTIFYRC = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "kdeconnect.notifyrc"


def set_desktop_popups(notifications: bool, calls: bool) -> None:
    """Turn kdeconnectd's own desktop popups on or off: phone notifications and missed calls
    (`notifications`), incoming calls (`calls`). Continuity shows its own banners instead.
    Writes the same file as System Settings › Notifications › KDE Connect and asks running
    apps to reload it."""
    cfg = configparser.ConfigParser(interpolation=None, strict=False)
    cfg.optionxform = str
    try:
        cfg.read(NOTIFYRC, encoding="utf-8")
    except configparser.Error as e:
        log.warning("can't read %s: %s", NOTIFYRC, e)
        return
    changed = False
    # a missed call also shows up as the phone app's own notification, which Continuity shows as a banner
    for event, on in (("notification", notifications), ("missedCall", notifications), ("callReceived", calls)):
        sec = f"Event/{event}"
        if on:
            # only undo our own "no action" (an empty Action), never what the user set
            if cfg.has_option(sec, "Action") and cfg.get(sec, "Action") == "":
                cfg.remove_option(sec, "Action")
                if not cfg.options(sec):
                    cfg.remove_section(sec)
                changed = True
        elif not (cfg.has_option(sec, "Action") and cfg.get(sec, "Action") == ""):
            if not cfg.has_section(sec):
                cfg.add_section(sec)
            cfg.set(sec, "Action", "")
            changed = True
    if not changed:
        return
    with open(NOTIFYRC, "w", encoding="utf-8") as f:
        cfg.write(f, space_around_delimiters=False)
    dbus.bus().emit_signal(None, "/Config", "org.kde.knotification", "reparseConfiguration",
                           GLib.Variant("(s)", ("kdeconnect",)))
