"""The `phone` object QML talks to: device state, models and actions."""
from __future__ import annotations

import logging
import mimetypes
import time
from datetime import datetime

from PySide6.QtCore import QDateTime, QLocale, QObject, QTimer, QUrl, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication
from gi.repository import GLib

from .core.contacts import ContactBook, number_key
from .core.kdeconnect import KDEConnect, Message, PhoneNotification, TYPE_FAILED, TYPE_OUTBOX, TYPE_QUEUED
from .core.telephony import IN_PROGRESS, RINGING, AudioRoute, Telephony
from .models import DictListModel, FilterHelper
from . import otp, settings
from .gmessages import GMessages
from .google_login import GoogleLogin

log = logging.getLogger(__name__)


def _initials(name: str) -> str:
    parts = [p for p in name.replace("+", "").split() if p]
    if not parts or parts[0][:1].isdigit():
        return ""
    return (parts[0][:1] + (parts[-1][:1] if len(parts) > 1 else "")).upper()


def _avatar_color(seed: str) -> str:
    palette = ["#ff6b6b", "#f59f00", "#51cf66", "#20c997", "#339af0", "#845ef7", "#f06595", "#5c7cfa"]
    return palette[sum(map(ord, seed)) % len(palette)]


class Phone(QObject):
    deviceChanged = Signal()
    callChanged = Signal()
    threadChanged = Signal()
    toast = Signal(str)
    showWindowRequested = Signal()
    messageArrived = Signal("QVariantMap")   # incoming SMS/RCS for the floating banner
    openThreadRequested = Signal(str)        # banner clicked: show this conversation
    mediaChanged = Signal()
    clipboardChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locale = QLocale.system()
        self._conversations = DictListModel(
            ["threadId", "title", "snippet", "time", "unread", "avatar", "initials", "color", "fromMe", "date", "rcs"],
            key="threadId", parent=self)
        self._conv_filter = FilterHelper(self._conversations, lambda r, q: q in r["title"].casefold()
                                         or q in r["snippet"].casefold() or q in r.get("numbers", ""))
        self._messages = DictListModel(
            ["uid", "body", "outgoing", "time", "dayLabel", "showDay", "status", "images", "attachmentCount",
             "groupStart", "groupEnd", "sender", "showSender", "reactions", "receipt"], key="uid", parent=self)
        self._notifications = DictListModel(
            ["nid", "app", "title", "text", "icon", "dismissable", "canReply", "isConversation"],
            key="nid", parent=self)
        self._contacts = DictListModel(["name", "number", "avatar", "initials", "color"], parent=self)
        self._contact_filter = FilterHelper(self._contacts, lambda r, q: q in r["name"].casefold()
                                            or number_key(q) and number_key(q) in number_key(r["number"]))
        self._unread_only = False
        self._marked_unread: set[str] = set(settings.get("markedUnread", []) or [])
        self._conv_filter.extra = lambda r: r["unread"] or r["threadId"] == self._thread_id \
            if self._unread_only else True
        self._book: ContactBook | None = None
        self._thread_id = ""
        seen = settings.get("seen", {}) or {}
        self._unread_seen: dict[str, int] = {(k if k[:1] in "kg" else f"k{k}"): int(v) for k, v in seen.items()}
        # Google Messages (SMS + RCS) through the helper
        self._gm_convs: dict[str, dict] = {}
        self._gm_msgs: dict[str, dict[str, dict]] = {}
        self._gm_cursor: dict[str, dict | None] = {}
        self._gm_media: dict[str, str] = {}
        self._gm_downloading: set[str] = set()
        self._gm_qr = ""
        self._bannered: list[str] = []  # recently announced message ids
        self._gm_inactive = False
        self.gm = GMessages(self)
        self._was_gm_mode = False
        self.gm.event.connect(self._on_gm_event)
        self.gm.stateChanged.connect(self._on_gm_state)
        self._gm_emoji = ""
        self._gm_emoji_svg = ""
        self.glogin = GoogleLogin(self)
        self.glogin.cookiesReady.connect(self._on_google_cookies)
        self.glogin.failed.connect(self._on_google_login_failed)
        self.glogin.stateChanged.connect(self.gmChanged)
        self.gm.start()

        self.kc = KDEConnect(self._on_kc)
        route = AudioRoute(settings.get("callSpeaker", ""), settings.get("callMicrophone", ""))
        self.tel = Telephony(self._on_tel, route)
        self._clock = QTimer(self, interval=1000, timeout=self._tick)
        self._clock.start()
        self._threads_dirty = QTimer(self, singleShot=True, interval=150, timeout=self._rebuild_threads)
        self._thread_dirty = QTimer(self, singleShot=True, interval=80, timeout=self._rebuild_thread)

    @Property(QObject, constant=True)
    def conversations(self):
        return self._conversations

    @Property(QObject, constant=True)
    def messages(self):
        return self._messages

    @Property(QObject, constant=True)
    def notifications(self):
        return self._notifications

    @Property(QObject, constant=True)
    def contacts(self):
        return self._contacts

    # ================================================================ device
    @property
    def dev(self):
        return self.kc.device

    @Property(bool, notify=deviceChanged)
    def daemonAvailable(self):
        return self.kc.available

    @Property(bool, notify=deviceChanged)
    def connected(self):
        return bool(self.dev and self.dev.reachable)

    @Property(bool, notify=deviceChanged)
    def paired(self):
        return self.dev is not None

    @Property(str, notify=deviceChanged)
    def deviceName(self):
        return self.dev.name if self.dev else ""

    @Property(int, notify=deviceChanged)
    def battery(self):
        return self.dev.battery if self.dev else -1

    @Property(bool, notify=deviceChanged)
    def charging(self):
        return bool(self.dev and self.dev.charging)

    @Property(str, notify=deviceChanged)
    def networkType(self):
        return self.dev.network_type if self.dev else ""

    @Property(int, notify=deviceChanged)
    def networkStrength(self):
        return self.dev.network_strength if self.dev else -1

    @Property(int, notify=deviceChanged)
    def contactCount(self):
        return len(self._book.contacts) if self._book else 0

    @Property(bool, notify=callChanged)
    def callsAvailable(self):
        return self.tel.available

    def _on_kc(self, kind: str, payload) -> None:
        dev = self.dev
        if kind == "device":
            if dev and (self._book is None or self._book.dir.name != f"kdeconnect-{dev.id}"):
                self._book = ContactBook(dev.id)
                self._rebuild_contacts()
            self.deviceChanged.emit()
        elif kind == "threads":
            self._threads_dirty.start()
        elif kind in ("thread", "thread_loaded"):
            tid = payload if kind == "thread" else payload[0]
            if f"k{tid}" == self._thread_id:
                self._thread_dirty.start()
            if kind == "thread":
                self._threads_dirty.start()
        elif kind == "notifications":
            self._rebuild_notifications()
        elif kind == "contacts":
            if self._book:
                self._book.reload()
            self._rebuild_contacts()
            self._threads_dirty.start()
            self.deviceChanged.emit()
        elif kind == "attachment":
            self.toast.emit(self.tr("Attachment saved: %1").replace("%1", payload[1]))
        elif kind == "incoming_sms":
            if not self._gm_mode:  # with Google Messages paired the helper announces it
                self._announce_kc(payload)
        elif kind == "media":
            self.mediaChanged.emit()
        elif kind == "clipboard":
            self.clipboardChanged.emit()
        if kind == "device":
            self.mediaChanged.emit()
            self.clipboardChanged.emit()

    # ================================================================ conversations
    # Two sources feed the Messages tab:
    #   * Google Messages (helper, SMS + RCS) when paired  -> thread ids "g<conversation id>"
    #   * KDE Connect (SMS/MMS only) otherwise              -> thread ids "k<thread id>"

    def _name(self, number: str) -> str:
        return self._book.name_for(number) if self._book else number

    def _photo(self, number: str) -> str:
        c = self._book.lookup(number) if self._book else None
        return QUrl.fromLocalFile(c.photo).toString() if c and c.photo else ""

    def _fmt_list_time(self, ms: int) -> str:
        dt = datetime.fromtimestamp(ms / 1000)
        now = datetime.now()
        qdt = QDateTime.fromMSecsSinceEpoch(ms)
        if dt.date() == now.date():
            return self._locale.toString(qdt.time(), QLocale.FormatType.ShortFormat)
        if (now.date() - dt.date()).days < 7:
            return self._locale.dayName(dt.isoweekday(), QLocale.FormatType.ShortFormat)
        return self._locale.toString(qdt.date(), QLocale.FormatType.ShortFormat)

    @property
    def _gm_mode(self) -> bool:
        return self.gm.paired

    sourceChanged = Signal()

    @Property(str, notify=sourceChanged)
    def messageSource(self):
        return "google" if self._gm_mode else "kdeconnect"

    # ---------------------------------------------------------------- KDE Connect helpers
    def _detect_own_number(self) -> None:
        """KDE Connect lists the phone's own number among the addresses of MMS/RCS-fallback
        threads. Treat a number that shows up in most multi-address threads as our own."""
        own = settings.get("ownNumber", "")
        if own:
            self._own_keys = {number_key(own)}
            return
        groups = [m for m in self.dev.threads.values() if len(m.addresses) > 1] if self.dev else []
        counts: dict[str, int] = {}
        for m in groups:
            for k in {number_key(a) for a in m.addresses}:
                counts[k] = counts.get(k, 0) + 1
        self._own_keys = {k for k, c in counts.items() if c >= 3 and c >= 0.5 * len(groups)}

    def _others(self, m: Message) -> list[str]:
        """The thread's participants without our own number (falls back to all)."""
        own = getattr(self, "_own_keys", set())
        others = [a for a in m.addresses if number_key(a) not in own]
        return others or m.addresses

    def _kc_thread(self, tid: str) -> Message | None:
        if not tid.startswith("k") or not self.dev:
            return None
        return self.dev.threads.get(int(tid[1:]))

    # ---------------------------------------------------------------- Google Messages helpers
    def _gm_others(self, c: dict) -> list[dict]:
        """Participants other than us, deduplicated (Google lists a contact once per
        identifier, e.g. phone number and RCS address); 1:1 chats have exactly one."""
        own = getattr(self, "_own_keys", set())
        seen, others = set(), []
        for p in c.get("participants") or []:
            key = number_key(p.get("number", "")) or p.get("id")
            if p.get("isMe") or key in own or key in seen:
                continue
            seen.add(key)
            others.append(p)
        if not others:
            others = list(c.get("participants") or [])
        return others if c.get("group") else others[:1]

    def _gm_conv(self, tid: str) -> dict | None:
        return self._gm_convs.get(tid[1:]) if tid.startswith("g") else None

    # ---------------------------------------------------------------- thread list
    def _rebuild_threads(self) -> None:
        rows = []
        if self._gm_mode:
            for c in sorted(self._gm_convs.values(), key=lambda c: c.get("timestamp", 0), reverse=True):
                if c.get("archived"):
                    continue
                others = self._gm_others(c)
                title = c.get("name") or ", ".join(p.get("name") or p.get("number") for p in others) or "?"
                first = others[0].get("number", "") if len(others) == 1 else ""
                snippet = c.get("snippet") or self.tr("Attachment")
                if c.get("fromMe"):
                    snippet = self.tr("You: ") + snippet
                elif c.get("group") and c.get("snippetFrom"):
                    snippet = f"{c['snippetFrom']}: {snippet}"
                rows.append({
                    "threadId": "g" + c["id"], "title": title, "snippet": snippet,
                    "time": self._fmt_list_time(c.get("timestamp", 0)), "date": c.get("timestamp", 0),
                    "unread": ("g" + c["id"]) in self._marked_unread
                              or (bool(c.get("unread")) and "g" + c["id"] != self._thread_id),
                    "avatar": self._photo(first) if first else "",
                    "initials": _initials(title) if len(others) == 1 else str(len(others)),
                    "color": c.get("color") or _avatar_color(title), "fromMe": bool(c.get("fromMe")),
                    "rcs": c.get("type") == "rcs",
                    "numbers": " ".join(p.get("number", "") for p in others),
                })
        elif self.dev:
            dev = self.dev
            self._detect_own_number()
            for m in sorted(dev.threads.values(), key=lambda m: m.date, reverse=True):
                addrs = self._others(m)
                names = [self._name(a) for a in addrs] or ["?"]
                title = ", ".join(names)
                first = addrs[0] if addrs else ""
                tid = f"k{m.thread_id}"
                unread = tid in self._marked_unread or \
                    (not m.read and not m.outgoing and self._unread_seen.get(tid, 0) < m.date)
                rows.append({
                    "threadId": tid, "title": title,
                    "snippet": (self.tr("You: ") if m.outgoing else "") + (m.body or self.tr("Attachment")),
                    "time": self._fmt_list_time(m.date), "date": m.date, "unread": unread,
                    "avatar": self._photo(first) if len(addrs) == 1 else "",
                    "initials": _initials(title) if len(addrs) == 1 else str(len(addrs)),
                    "color": _avatar_color(title), "fromMe": m.outgoing, "rcs": False,
                    "numbers": " ".join(m.addresses),
                })
        self._conv_filter.set_all(rows)
        self.threadChanged.emit()

    @Slot(str)
    def filterConversations(self, q: str) -> None:
        self._conv_filter.set_query(q)

    unreadOnlyChanged = Signal()

    @Property(bool, notify=unreadOnlyChanged)
    def unreadOnly(self):
        return self._unread_only

    @unreadOnly.setter
    def unreadOnly(self, on: bool):
        if on != self._unread_only:
            self._unread_only = on
            self._conv_filter.apply()
            self.unreadOnlyChanged.emit()

    @Slot()
    def markAllRead(self) -> None:
        self._marked_unread.clear()
        settings.set("markedUnread", [])
        if self._gm_mode:
            for c in self._gm_convs.values():
                if c.get("unread") and c.get("latestId"):
                    self.gm.request("mark_read", conversation=c["id"], message=c["latestId"])
                    c["unread"] = False
        elif self.dev:
            for tid, m in self.dev.threads.items():
                key = f"k{tid}"
                self._unread_seen[key] = max(self._unread_seen.get(key, 0), m.date)
            settings.set("seen", self._unread_seen)
        self._rebuild_threads()

    @Slot(str)
    def markUnread(self, tid: str) -> None:
        """Local 'mark as unread' (the Google Messages protocol has no such action)."""
        self._marked_unread.add(tid)
        settings.set("markedUnread", sorted(self._marked_unread))
        self._rebuild_threads()

    @Slot(str)
    def markRead(self, tid: str) -> None:
        self._marked_unread.discard(tid)
        settings.set("markedUnread", sorted(self._marked_unread))
        c = self._gm_conv(tid)
        if c is not None and c.get("unread") and c.get("latestId"):
            self.gm.request("mark_read", None, conversation=c["id"], message=c["latestId"])
            c["unread"] = False
        m = self._kc_thread(tid)
        if m is not None:
            self._unread_seen[tid] = m.date
            settings.set("seen", self._unread_seen)
        self._rebuild_threads()

    @Property(str, notify=threadChanged)
    def threadId(self):
        return self._thread_id

    @Property(str, notify=threadChanged)
    def threadTitle(self):
        c = self._gm_conv(self._thread_id)
        if c:
            return c.get("name") or ", ".join(p.get("name") or p.get("number") for p in self._gm_others(c))
        m = self._kc_thread(self._thread_id)
        return ", ".join(self._name(a) for a in self._others(m)) if m else ""

    @Property(str, notify=threadChanged)
    def threadNumber(self):
        c = self._gm_conv(self._thread_id)
        if c:
            others = self._gm_others(c)
            return others[0].get("number", "") if len(others) == 1 and not c.get("group") else ""
        m = self._kc_thread(self._thread_id)
        others = self._others(m) if m else []
        return others[0] if len(others) == 1 else ""

    @Property(str, notify=threadChanged)
    def threadAvatar(self):
        n = self.threadNumber
        return self._photo(n) if n else ""

    @Property(bool, notify=threadChanged)
    def threadIsRcs(self):
        c = self._gm_conv(self._thread_id)
        return bool(c and c.get("type") == "rcs")

    @Property(int, notify=threadChanged)
    def unreadCount(self):
        return sum(1 for r in self._conv_filter.all if r["unread"])

    @Slot(str)
    def openThread(self, tid: str) -> None:
        if tid in self._marked_unread:
            self._marked_unread.discard(tid)
            settings.set("markedUnread", sorted(self._marked_unread))
        self._thread_id = tid
        c = self._gm_conv(tid)
        if c is not None:
            if c["id"] not in self._gm_cursor:
                self._gm_fetch(c["id"])
            if c.get("unread") and c.get("latestId"):
                self.gm.request("mark_read", conversation=c["id"], message=c["latestId"])
                c["unread"] = False
        else:
            m = self._kc_thread(tid)
            if m and self.dev:
                self._unread_seen[tid] = m.date
                settings.set("seen", self._unread_seen)
                if len(self.dev.messages.get(m.thread_id, {})) < 30:
                    self.dev.load_thread(m.thread_id, 50)
        self._rebuild_thread()
        self._threads_dirty.start()
        self.threadChanged.emit()

    @Slot()
    def loadOlder(self) -> None:
        c = self._gm_conv(self._thread_id)
        if c is not None:
            cur = self._gm_cursor.get(c["id"])
            if cur:  # None = nothing older
                self._gm_fetch(c["id"], cur)
            return
        m = self._kc_thread(self._thread_id)
        if m and self.dev:
            self.dev.loaded_counts[m.thread_id] = len(self.dev.messages.get(m.thread_id, {}))
            self.dev.load_thread(m.thread_id, 50)

    def _rebuild_thread(self) -> None:
        if self._thread_id.startswith("g"):
            self._rebuild_gm_thread()
            return
        m0 = self._kc_thread(self._thread_id)
        bucket = self.dev.messages.get(m0.thread_id, {}) if (m0 and self.dev) else {}
        msgs: list[Message] = sorted((m for m in bucket.values() if m.body or m.attachments), key=lambda m: m.date)
        items = []
        for m in msgs:
            status = "failed" if m.type == TYPE_FAILED else "sending" if m.type in (TYPE_OUTBOX, TYPE_QUEUED) else ""
            items.append({
                "uid": f"k{m.uid}", "date": m.date, "body": m.body, "outgoing": m.outgoing, "status": status,
                "images": [f"data:{a.mime};base64,{a.thumbnail_b64}" for a in m.attachments
                           if a.mime.startswith("image/") and a.thumbnail_b64],
                "attachmentCount": len(m.attachments), "sender": "", "reactions": "",
            })
        self._messages.set_rows(self._layout_bubbles(items, group=False))

    def _rebuild_gm_thread(self) -> None:
        cid = self._thread_id[1:]
        conv = self._gm_convs.get(cid, {})
        names = {p["id"]: (p.get("first") or p.get("name") or p.get("number")) for p in conv.get("participants") or []}
        items = []
        for m in sorted(self._gm_msgs.get(cid, {}).values(), key=lambda m: m.get("timestamp", 0)):
            if m.get("deleted") or (not m.get("text") and not m.get("media")):
                continue
            images = []
            for md in m.get("media") or []:
                if not (md.get("mime", "").startswith("image/") or md.get("thumbId")):
                    continue
                path = self._gm_media.get(md.get("thumbId") or md["id"])
                if path:
                    images.append(QUrl.fromLocalFile(path).toString())
                else:
                    self._gm_download(md.get("thumbId") or md["id"], md.get("thumbKey") or md.get("key"))
            reactions = " ".join(f"{r['emoji']}{r['count'] if r['count'] > 1 else ''}" for r in m.get("reactions") or [])
            st = m.get("status", "")
            items.append({
                "uid": "g" + m["id"], "date": m.get("timestamp", 0), "body": m.get("text", ""),
                "outgoing": bool(m.get("fromMe")),
                "status": {"sending": "sending", "failed": "failed"}.get(st, ""),
                "delivery": st if st in ("sent", "delivered", "read") else "",
                "images": images, "attachmentCount": len(m.get("media") or []),
                "sender": m.get("senderName") or names.get(m.get("sender"), "") if conv.get("group") else "",
                "reactions": reactions,
            })
        rows = self._layout_bubbles(items, group=bool(conv.get("group")))
        # iMessage-style receipt under the newest outgoing message only
        last_out = next((r for r in reversed(rows) if r["outgoing"]), None)
        for r in rows:
            r["receipt"] = ""
        if last_out and last_out.get("delivery"):
            last_out["receipt"] = {"sent": self.tr("Sent"), "delivered": self.tr("Delivered"),
                                   "read": self.tr("Read")}[last_out["delivery"]]
        self._messages.set_rows(rows)

    def _layout_bubbles(self, items: list[dict], group: bool) -> list[dict]:
        rows = []
        for i, it in enumerate(items):
            prev = items[i - 1] if i else None
            nxt = items[i + 1] if i + 1 < len(items) else None
            day = datetime.fromtimestamp(it["date"] / 1000).date()
            show_day = prev is None or datetime.fromtimestamp(prev["date"] / 1000).date() != day
            qdt = QDateTime.fromMSecsSinceEpoch(it["date"])
            same = lambda a, b: a and b and a["outgoing"] == b["outgoing"] and a.get("sender") == b.get("sender")
            group_start = show_day or not same(prev, it) or it["date"] - prev["date"] > 300_000
            group_end = nxt is None or not same(it, nxt) or nxt["date"] - it["date"] > 300_000 or \
                datetime.fromtimestamp(nxt["date"] / 1000).date() != day
            rows.append({
                **it,
                "time": self._locale.toString(qdt.time(), QLocale.FormatType.ShortFormat),
                "dayLabel": self._locale.toString(qdt.date(), QLocale.FormatType.LongFormat),
                "showDay": show_day, "groupStart": group_start, "groupEnd": group_end,
                "showSender": group and not it["outgoing"] and group_start and bool(it.get("sender")),
                "receipt": "",
            })
        return rows

    @Slot(str)
    def sendReply(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        c = self._gm_conv(self._thread_id)
        if c is not None:
            self.gm.request("send", lambda r, e: e and self.toast.emit(self.tr("Sending failed: %1").replace("%1", e)),
                            conversation=c["id"], text=text)
            return
        m = self._kc_thread(self._thread_id)
        if m and self.dev:
            self.dev.reply(m.thread_id, text)

    @Slot("QVariantList")
    def sendFilesToThread(self, urls) -> None:
        c = self._gm_conv(self._thread_id)
        if c is None:
            self.toast.emit(self.tr("Attachments need Google Messages"))
            return
        for u in urls:
            path = QUrl(u).toLocalFile() if not isinstance(u, QUrl) else u.toLocalFile()
            mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
            self.gm.request("send", lambda r, e: e and self.toast.emit(self.tr("Sending failed: %1").replace("%1", e)),
                            conversation=c["id"], file=path, mime=mime)

    @Slot(str, str)
    def sendNew(self, number: str, text: str) -> None:
        numbers = [n.strip() for n in number.split(",") if n.strip()]
        if not numbers or not text.strip():
            return
        if self._gm_mode:
            def opened(conv, err):
                if err or not conv:
                    self.toast.emit(self.tr("Sending failed: %1").replace("%1", err or "?"))
                    return
                self._gm_convs[conv["id"]] = conv
                self.gm.request("send", None, conversation=conv["id"], text=text.strip())
                self._rebuild_threads()
                self.openThread("g" + conv["id"])
            self.gm.request("new_conversation", opened, numbers=numbers)
        elif self.dev:
            self.dev.send_new(numbers, text.strip())
            self.toast.emit(self.tr("Message sent"))

    @Slot(str, result=str)
    def threadForNumber(self, number: str) -> str:
        """Existing 1:1 thread for a number, or ""."""
        k = number_key(number)
        if self._gm_mode:
            for c in self._gm_convs.values():
                others = self._gm_others(c)
                if not c.get("group") and len(others) == 1 and number_key(others[0].get("number", "")) == k:
                    return "g" + c["id"]
            return ""
        if not self.dev:
            return ""
        for m in self.dev.threads.values():
            others = self._others(m)
            if len(others) == 1 and number_key(others[0]) == k:
                return f"k{m.thread_id}"
        return ""

    @Slot(str, str)
    def react(self, uid: str, emoji: str) -> None:
        if uid.startswith("g"):
            self.gm.request("react", None, message=uid[1:], emoji=emoji)

    # ---------------------------------------------------------------- Google Messages plumbing
    def _gm_fetch(self, cid: str, cursor=None) -> None:
        def done(res, err):
            if err or not res:
                log.warning("fetch messages failed: %s", err)
                return
            bucket = self._gm_msgs.setdefault(cid, {})
            for m in res.get("messages") or []:
                bucket[m["id"]] = m
            cur = res.get("cursor")
            self._gm_cursor[cid] = cur if cur and cur.get("lastItemID") else None
            if self._thread_id == "g" + cid:
                self._thread_dirty.start()
        params = {"conversation": cid, "count": 50}
        if cursor:
            params["cursor"] = cursor
        self.gm.request("messages", done, **params)

    def _gm_download(self, media_id: str, key: str) -> None:
        if not media_id or media_id in self._gm_downloading:
            return
        self._gm_downloading.add(media_id)

        def done(res, err):
            self._gm_downloading.discard(media_id)
            if res and res.get("path"):
                self._gm_media[media_id] = res["path"]
                self._thread_dirty.start()
        self.gm.request("download", done, mediaId=media_id, key=key)

    def _on_gm_event(self, name: str, data) -> None:
        if name in ("ready", "conversations"):
            for c in (data or {}).get("conversations") or []:
                self._gm_convs[c["id"]] = c
            if name == "ready":
                self.gm.request("conversations", self._on_gm_conversations, count=300)
                if self._thread_id.startswith("g"):  # reconnected: refresh the open thread
                    self._gm_fetch(self._thread_id[1:])
            self._threads_dirty.start()
        elif name == "conversation":
            self._gm_convs[data["id"]] = data
            self._threads_dirty.start()
            if self._thread_id == "g" + data["id"]:
                self.threadChanged.emit()
        elif name == "message":
            cid = data.get("conversation", "")
            bucket = self._gm_msgs.setdefault(cid, {})
            if data.get("tmpId"):  # drop our optimistic copy once the phone echoes it
                bucket.pop("tmp:" + data["tmpId"], None)
            bucket[data["id"]] = data
            if self._thread_id == "g" + cid:
                self._thread_dirty.start()
                if not data.get("fromMe") and not data.get("old") and self._window_active():
                    self.gm.request("mark_read", None, conversation=cid, message=data["id"])
            if not data.get("fromMe") and not data.get("old") and not data.get("tmpId"):
                self._announce_gm(cid, data)
        elif name == "pair_emoji":
            self._gm_emoji = data.get("emoji", "")
            self._gm_emoji_svg = data.get("svg", "")
            self.gmChanged.emit()
            self.showWindowRequested.emit()
        elif name == "pair_failed":
            self._gm_emoji = self._gm_emoji_svg = ""
            reason = data.get("reason", "")
            self.toast.emit({
                "wrong_emoji": self.tr("Wrong emoji chosen on the phone, try again"),
                "no_phone": self.tr("No phone with Google Messages found on this Google account"),
                "phone_inactive": self.tr("Open Google Messages on the phone and try again"),
            }.get(reason, self.tr("Pairing failed: %1").replace("%1", reason)))
            self.gmChanged.emit()
        elif name in ("qr", "paired", "qr_expired", "logged_out", "inactive", "phone", "error", "recovered", "starting"):
            if name == "qr":
                self._gm_qr = QUrl.fromLocalFile(data["png"]).toString() + f"?{time.time()}" if data.get("png") else ""
            elif name in ("paired", "qr_expired", "logged_out"):
                self._gm_qr = ""
            if name == "paired":
                self._gm_emoji = self._gm_emoji_svg = ""
                self.glogin.cleanup()
                self.toast.emit(self.tr("Google Messages paired"))
            if name == "inactive":
                self._gm_inactive = True
            elif name in ("ready", "recovered"):
                self._gm_inactive = False
            if name == "logged_out":
                self._gm_convs.clear()
                self._gm_msgs.clear()
                self._gm_cursor.clear()
                if self._thread_id.startswith("g"):
                    self._thread_id = ""
                self._threads_dirty.start()
            self.gmChanged.emit()
        if name in ("ready", "inactive", "recovered"):
            self.gmChanged.emit()

    def _on_gm_conversations(self, res, err) -> None:
        if res:
            for c in res.get("conversations") or []:
                self._gm_convs[c["id"]] = c
            self._threads_dirty.start()

    def _window_active(self) -> bool:
        w = QGuiApplication.focusWindow()
        return w is not None and w.isActive()

    def _on_gm_state(self) -> None:
        if self._gm_mode != self._was_gm_mode:
            self._was_gm_mode = self._gm_mode
            self._thread_id = ""
            self._rebuild_threads()
            self._rebuild_thread()
            self.sourceChanged.emit()
        self.gmChanged.emit()

    gmChanged = Signal()

    @Property(bool, notify=gmChanged)
    def gmAvailable(self):
        return self.gm.available

    @Property(bool, notify=gmChanged)
    def gmPaired(self):
        return self.gm.paired

    @Property(bool, notify=gmChanged)
    def gmConnected(self):
        return self.gm.connected

    @Property(bool, notify=gmChanged)
    def gmInactive(self):
        return self._gm_inactive

    @Property(str, notify=gmChanged)
    def gmQr(self):
        return self._gm_qr

    @Slot()
    def gmPair(self) -> None:
        def done(res, err):
            if err:
                self.toast.emit(self.tr("Pairing failed: %1").replace("%1", err))
                return
            self._gm_qr = QUrl.fromLocalFile(res["png"]).toString() + f"?{time.time()}" if res.get("png") else ""
            self.gmChanged.emit()
        self.gm.start()
        QTimer.singleShot(300, lambda: self.gm.request("pair_qr", done))

    @Slot()
    def gmCancelPair(self) -> None:
        self._gm_qr = ""
        self._gm_emoji = self._gm_emoji_svg = ""
        self.glogin.cancel()
        self.gmChanged.emit()

    @Property(bool, notify=gmChanged)
    def gmGoogleLoginAvailable(self):
        return self.glogin.available

    @Property(bool, notify=gmChanged)
    def gmSigningIn(self):
        return self.glogin.active

    @Property(str, notify=gmChanged)
    def gmEmoji(self):
        return self._gm_emoji

    @Property(str, notify=gmChanged)
    def gmEmojiSvg(self):
        return self._gm_emoji_svg

    @Slot()
    def gmPairGoogle(self) -> None:
        self.gm.start()
        self._gm_qr = ""
        self.glogin.start()
        self.gmChanged.emit()

    def _on_google_cookies(self, rows: list, version: int) -> None:
        self.showWindowRequested.emit()
        self.toast.emit(self.tr("Signed in, contacting your phone…"))

        def done(res, err):
            if err:
                self.toast.emit(self.tr("Pairing failed: %1").replace("%1", err))
                self.gmChanged.emit()
        self.gm.request("pair_google", done, encrypted=rows, dbVersion=version)
        self.gmChanged.emit()

    def _on_google_login_failed(self, reason: str) -> None:
        if reason == "no_browser":
            self.toast.emit(self.tr("Install Microsoft Edge, Chrome or Chromium to sign in"))
        elif reason == "closed":
            self.toast.emit(self.tr("Sign-in window closed before signing in"))
        self.gmChanged.emit()

    @Slot()
    def gmActivate(self) -> None:
        self.gm.request("activate", lambda r, e: self._on_gm_event("recovered", None) if not e else None)

    @Slot()
    def gmUnpair(self) -> None:
        self.gm.request("unpair", lambda r, e: self._on_gm_event("logged_out", None))
        self.gm.paired = False
        self.gm.connected = False
        self._on_gm_state()

    # ================================================================ contacts
    def _rebuild_contacts(self) -> None:
        rows = []
        if self._book:
            for c in self._book.contacts:
                for n in c.numbers:
                    rows.append({"name": c.name, "number": n,
                                 "avatar": QUrl.fromLocalFile(c.photo).toString() if c.photo else "",
                                 "initials": _initials(c.name), "color": _avatar_color(c.name)})
        self._contact_filter.set_all(rows)

    @Slot(str)
    def filterContacts(self, q: str) -> None:
        self._contact_filter.set_query(q)

    @Slot()
    def syncContacts(self) -> None:
        if self.dev:
            self.dev.sync_contacts()
            self.toast.emit(self.tr("Syncing contacts…"))

    # ================================================================ notifications
    def _rebuild_notifications(self) -> None:
        rows = []
        if self.dev:
            for n in reversed(list(self.dev.notifications.values())):
                rows.append({"nid": n.id, "app": n.app, "title": n.title, "text": n.text,
                             "icon": QUrl.fromLocalFile(n.icon).toString() if n.icon else "",
                             "dismissable": n.dismissable, "canReply": bool(n.reply_id),
                             "isConversation": n.is_conversation})
        self._notifications.set_rows(rows)

    @Slot(str)
    def dismiss(self, nid: str) -> None:
        if self.dev:
            self.dev.dismiss(nid)

    @Slot()
    def dismissAll(self) -> None:
        if self.dev:
            self.dev.dismiss_all()

    @Slot(str, str)
    def replyNotification(self, nid: str, text: str) -> None:
        if self.dev and text.strip():
            self.dev.reply_notification(nid, text.strip())
            self.toast.emit(self.tr("Reply sent"))

    # ================================================================ phone actions
    @Slot()
    def ring(self) -> None:
        if self.dev:
            self.dev.ring()
            self.toast.emit(self.tr("Your phone is ringing"))

    @Slot("QVariantList")
    def sendFiles(self, urls) -> None:
        urls = [u.toString() if isinstance(u, QUrl) else str(u) for u in urls]
        if self.dev and urls:
            self.dev.share_urls(urls)
            self.toast.emit(self.tr("Sending %n file(s)…", "", len(urls)))

    @Slot()
    def browseFiles(self) -> None:
        if self.dev:
            self.dev.browse_files()

    @Slot()
    def sendClipboard(self) -> None:
        if self.dev:
            self.dev.send_clipboard()
            self.toast.emit(self.tr("Clipboard sent to phone"))

    @Slot(str)
    def shareText(self, text: str) -> None:
        if self.dev and text:
            self.dev.share_text(text)

    # ================================================================ message banners
    def _thread_visible(self, tid: str) -> bool:
        return self._thread_id == tid and self._window_active()

    def _announce(self, mid: str, tid: str, title: str, body: str, avatar: str,
                  initials: str, color: str) -> None:
        if mid in self._bannered or self._thread_visible(tid):
            return
        self._bannered = (self._bannered + [mid])[-100:]
        self.messageArrived.emit({
            "id": mid, "threadId": tid, "title": title, "body": body, "avatar": avatar,
            "initials": initials, "color": color, "code": otp.find_code(body),
        })

    def _announce_kc(self, m: Message) -> None:
        addrs = self._others(m)
        title = ", ".join(self._name(a) for a in addrs) or "?"
        self._announce(f"k{m.uid}", f"k{m.thread_id}", title, m.body or self.tr("Attachment"),
                       self._photo(addrs[0]) if len(addrs) == 1 else "",
                       _initials(title) if len(addrs) == 1 else str(len(addrs)), _avatar_color(title))

    def _announce_gm(self, cid: str, m: dict) -> None:
        c = self._gm_convs.get(cid, {})
        others = self._gm_others(c) if c else []
        title = c.get("name") or ", ".join(p.get("name") or p.get("number") for p in others) \
            or m.get("senderName") or "?"
        body = m.get("text") or self.tr("Attachment")
        if c.get("group") and m.get("senderName"):
            body = f"{m['senderName']}: {body}"
        first = others[0].get("number", "") if len(others) == 1 else ""
        self._announce("g" + m["id"], "g" + cid, title, body, self._photo(first) if first else "",
                       _initials(title) if len(others) <= 1 else str(len(others)),
                       c.get("color") or _avatar_color(title))

    @Slot(str, str)
    def replyToThread(self, tid: str, text: str) -> None:
        """Quick reply from the banner, without opening the conversation."""
        text = text.strip()
        if not text:
            return
        c = self._gm_conv(tid)
        if c is not None:
            self.gm.request("send", lambda r, e: e and self.toast.emit(self.tr("Sending failed: %1").replace("%1", e)),
                            conversation=c["id"], text=text)
            return
        m = self._kc_thread(tid)
        if m and self.dev:
            self.dev.reply(m.thread_id, text)

    @Slot(str)
    def showThread(self, tid: str) -> None:
        self.showWindowRequested.emit()
        self.openThreadRequested.emit(tid)

    @Slot(str)
    def copySilently(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)

    # ================================================================ clipboard sync
    @Property(bool, notify=clipboardChanged)
    def clipboardAutoShare(self):
        return bool(self.dev and self.dev.clipboard_auto_share())

    @clipboardAutoShare.setter
    def clipboardAutoShare(self, on: bool):
        if self.dev:
            self.dev.set_clipboard_auto_share(on)

    # ================================================================ phone media (mprisremote)
    def _media(self) -> dict:
        return self.dev.media if self.dev else {}

    @Property(bool, notify=mediaChanged)
    def mediaAvailable(self):
        return bool(self._media().get("playerList")) and bool(self._media().get("title"))

    @Property(str, notify=mediaChanged)
    def mediaTitle(self):
        return self._media().get("title", "")

    @Property(str, notify=mediaChanged)
    def mediaArtist(self):
        return self._media().get("artist", "")

    @Property(str, notify=mediaChanged)
    def mediaAlbum(self):
        return self._media().get("album", "")

    @Property(str, notify=mediaChanged)
    def mediaArt(self):
        url = self._media().get("localAlbumArtUrl", "")
        return url if url and "://" in url else (QUrl.fromLocalFile(url).toString() if url else "")

    @Property(bool, notify=mediaChanged)
    def mediaPlaying(self):
        return bool(self._media().get("isPlaying"))

    @Property(int, notify=mediaChanged)
    def mediaLength(self):
        return int(self._media().get("length", 0) or 0)

    @Property(int, notify=mediaChanged)
    def mediaPosition(self):
        return int(self._media().get("position", 0) or 0)

    @Property(bool, notify=mediaChanged)
    def mediaCanSeek(self):
        return bool(self._media().get("canSeek"))

    @Property("QStringList", notify=mediaChanged)
    def mediaPlayers(self):
        return list(self._media().get("playerList", []) or [])

    @Property(str, notify=mediaChanged)
    def mediaPlayer(self):
        return self._media().get("player", "")

    @Slot(str)
    def mediaAction(self, action: str) -> None:
        if self.dev:
            self.dev.media_action(action)

    @Slot(str)
    def mediaSelectPlayer(self, name: str) -> None:
        if self.dev:
            self.dev.media_set("player", GLib.Variant("s", name))

    @Slot(int)
    def mediaSeekTo(self, ms: int) -> None:
        if self.dev:
            self.dev.media_set("position", GLib.Variant("i", int(ms)))

    # ================================================================ calls
    def _on_tel(self, kind: str, payload) -> None:
        # incoming calls are shown by the floating call window (CallWindow.qml)
        self.callChanged.emit()

    def _call(self):
        return self.tel.ringing() or self.tel.current()

    @Property(str, notify=callChanged)
    def callState(self):
        c = self._call()
        if not c:
            return ""
        return "ringing" if c.state in RINGING else c.state

    @Property(str, notify=callChanged)
    def callName(self):
        c = self._call()
        if not c:
            return ""
        return self._name(c.number) if c.number else (c.name or self.tr("Unknown caller"))

    @Property(str, notify=callChanged)
    def callNumber(self):
        c = self._call()
        return c.number if c else ""

    @Property(str, notify=callChanged)
    def callAvatar(self):
        c = self._call()
        return self._photo(c.number) if c and c.number else ""

    @Property(str, notify=callChanged)
    def callDuration(self):
        c = self.tel.current()
        if not c or c.state != "active":
            return ""
        s = int(time.monotonic() - c.since)
        return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"

    @Property(bool, notify=callChanged)
    def callMuted(self):
        return self.tel.muted

    @Property(bool, notify=callChanged)
    def callSpeakerMuted(self):
        return self.tel.speaker_muted

    def _tick(self) -> None:
        if self.tel.current():
            self.callChanged.emit()

    @Slot()
    def answer(self):
        self.tel.answer()

    @Slot()
    def decline(self):
        self.tel.decline()

    @Slot()
    def hangup(self):
        self.tel.hangup()

    @Slot()
    def toggleMute(self):
        self.tel.set_muted(not self.tel.muted)

    @Slot(str, result="QVariantMap")
    def windowPlacement(self, key: str) -> dict:
        """Last saved position of a floating window (e.g. the call HUD); {} if none."""
        v = (settings.get("placement", {}) or {}).get(key)
        return v if isinstance(v, dict) else {}

    @Slot(str, "QVariantMap")
    def saveWindowPlacement(self, key: str, value: dict) -> None:
        placement = dict(settings.get("placement", {}) or {})
        placement[key] = {k: int(v) for k, v in value.items()}
        settings.set("placement", placement)

    @Slot()
    def toggleSpeakerMute(self):
        self.tel.set_speaker_muted(not self.tel.speaker_muted)

    @Slot(str)
    def sendTones(self, tones: str):
        self.tel.send_tones(tones)

    @Slot(str, result=bool)
    def dial(self, number: str) -> bool:
        number = "".join(ch for ch in number if ch.isdigit() or ch in "+*#")
        if not number:
            return False
        if not self.tel.dial(number):
            self.toast.emit(self.tr("Phone is not connected over Bluetooth"))
            return False
        return True

    # ================================================================ misc
    @Slot(str)
    def copyText(self, text: str) -> None:
        QGuiApplication.clipboard().setText(text)
        self.toast.emit(self.tr("Copied"))

    @Property(bool, constant=True)
    def autostartAvailable(self):
        return True

    autostartChanged = Signal()

    @Property(bool, notify=autostartChanged)
    def autostart(self):
        return settings.autostart_enabled()

    @autostart.setter
    def autostart(self, on: bool):
        settings.set_autostart(on)
        self.autostartChanged.emit()

    languageChanged = Signal()

    @Property(str, notify=languageChanged)
    def language(self):
        return settings.get("language", "")

    @language.setter
    def language(self, code: str):
        if code != settings.get("language", ""):
            settings.set("language", code)
            self.languageChanged.emit()
            self.toast.emit(self.tr("Restart Continuity to change the language"))

    def shutdown(self) -> None:
        self.tel.shutdown()
        self.gm.stop()
