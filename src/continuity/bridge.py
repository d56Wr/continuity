"""The `phone` object QML talks to: device state, models and actions."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from PySide6.QtCore import QDateTime, QLocale, QObject, QTimer, QUrl, Property, Signal, Slot
from PySide6.QtGui import QGuiApplication

from .core.contacts import ContactBook, number_key
from .core.kdeconnect import KDEConnect, Message, PhoneNotification, TYPE_FAILED, TYPE_OUTBOX, TYPE_QUEUED
from .core.telephony import IN_PROGRESS, RINGING, AudioRoute, Telephony
from .models import DictListModel, FilterHelper
from . import desktop_notify, settings

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self._locale = QLocale.system()
        self._conversations = DictListModel(
            ["threadId", "title", "snippet", "time", "unread", "avatar", "initials", "color", "fromMe", "date"],
            key="threadId", parent=self)
        self._conv_filter = FilterHelper(self._conversations, lambda r, q: q in r["title"].casefold()
                                         or q in r["snippet"].casefold() or q in r.get("numbers", ""))
        self._messages = DictListModel(
            ["uid", "body", "outgoing", "time", "dayLabel", "showDay", "status", "images", "attachmentCount",
             "groupStart", "groupEnd"], key="uid", parent=self)
        self._notifications = DictListModel(
            ["nid", "app", "title", "text", "icon", "dismissable", "canReply", "isConversation"],
            key="nid", parent=self)
        self._contacts = DictListModel(["name", "number", "avatar", "initials", "color"], parent=self)
        self._contact_filter = FilterHelper(self._contacts, lambda r, q: q in r["name"].casefold()
                                            or number_key(q) and number_key(q) in number_key(r["number"]))
        self._book: ContactBook | None = None
        self._thread_id = -1
        self._unread_seen: dict[int, int] = settings.get("seen", {}) or {}
        self._unread_seen = {int(k): int(v) for k, v in self._unread_seen.items()}

        self.kc = KDEConnect(self._on_kc)
        route = AudioRoute(settings.get("callSpeaker", ""), settings.get("callMicrophone", ""))
        self.tel = Telephony(self._on_tel, route)
        self._call_notification = 0
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
            if tid == self._thread_id:
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

    # ================================================================ conversations
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

    def _rebuild_threads(self) -> None:
        dev = self.dev
        rows = []
        if dev:
            for m in sorted(dev.threads.values(), key=lambda m: m.date, reverse=True):
                names = [self._name(a) for a in m.addresses] or ["?"]
                title = ", ".join(names)
                first = m.addresses[0] if m.addresses else ""
                unread = (not m.read and not m.outgoing and self._unread_seen.get(m.thread_id, 0) < m.date)
                rows.append({
                    "threadId": m.thread_id, "title": title,
                    "snippet": (self.tr("You: ") if m.outgoing else "") + (m.body or self.tr("Attachment")),
                    "time": self._fmt_list_time(m.date), "date": m.date, "unread": unread,
                    "avatar": self._photo(first) if len(m.addresses) == 1 else "",
                    "initials": _initials(title) if len(m.addresses) == 1 else str(len(m.addresses)),
                    "color": _avatar_color(title), "fromMe": m.outgoing,
                    "numbers": " ".join(m.addresses),
                })
        self._conv_filter.set_all(rows)
        self.threadChanged.emit()

    @Slot(str)
    def filterConversations(self, q: str) -> None:
        self._conv_filter.set_query(q)

    @Property(int, notify=threadChanged)
    def threadId(self):
        return self._thread_id

    @Property(str, notify=threadChanged)
    def threadTitle(self):
        m = self.dev.threads.get(self._thread_id) if self.dev else None
        return ", ".join(self._name(a) for a in m.addresses) if m else ""

    @Property(str, notify=threadChanged)
    def threadNumber(self):
        m = self.dev.threads.get(self._thread_id) if self.dev else None
        return m.addresses[0] if m and len(m.addresses) == 1 else ""

    @Property(str, notify=threadChanged)
    def threadAvatar(self):
        n = self.threadNumber
        return self._photo(n) if n else ""

    @Property(int, notify=threadChanged)
    def unreadCount(self):
        return sum(1 for r in self._conv_filter.all if r["unread"])

    @Slot(int)
    def openThread(self, tid: int) -> None:
        self._thread_id = tid
        if self.dev:
            newest = self.dev.threads.get(tid)
            if newest:
                self._unread_seen[tid] = newest.date
                settings.set("seen", {str(k): v for k, v in self._unread_seen.items()})
            if len(self.dev.messages.get(tid, {})) < 30:
                self.dev.load_thread(tid, 50)
        self._rebuild_thread()
        self._threads_dirty.start()
        self.threadChanged.emit()

    @Slot()
    def loadOlder(self) -> None:
        if self.dev and self._thread_id >= 0:
            self.dev.loaded_counts[self._thread_id] = len(self.dev.messages.get(self._thread_id, {}))
            self.dev.load_thread(self._thread_id, 50)

    def _rebuild_thread(self) -> None:
        msgs: list[Message] = sorted((self.dev.messages.get(self._thread_id, {}) if self.dev else {}).values(),
                                     key=lambda m: m.date)
        rows = []
        prev: Message | None = None
        for i, m in enumerate(msgs):
            nxt = msgs[i + 1] if i + 1 < len(msgs) else None
            day = datetime.fromtimestamp(m.date / 1000).date()
            show_day = prev is None or datetime.fromtimestamp(prev.date / 1000).date() != day
            qdt = QDateTime.fromMSecsSinceEpoch(m.date)
            group_start = show_day or prev is None or prev.outgoing != m.outgoing or m.date - prev.date > 300_000
            group_end = nxt is None or nxt.outgoing != m.outgoing or nxt.date - m.date > 300_000 or \
                datetime.fromtimestamp(nxt.date / 1000).date() != day
            images = [f"data:{a.mime};base64,{a.thumbnail_b64}" for a in m.attachments
                      if a.mime.startswith("image/") and a.thumbnail_b64]
            status = "failed" if m.type == TYPE_FAILED else "sending" if m.type in (TYPE_OUTBOX, TYPE_QUEUED) else ""
            rows.append({
                "uid": m.uid, "body": m.body, "outgoing": m.outgoing,
                "time": self._locale.toString(qdt.time(), QLocale.FormatType.ShortFormat),
                "dayLabel": self._locale.toString(qdt.date(), QLocale.FormatType.LongFormat),
                "showDay": show_day, "status": status, "images": images,
                "attachmentCount": len(m.attachments), "groupStart": group_start, "groupEnd": group_end,
            })
            prev = m
        self._messages.set_rows(rows)

    @Slot(str)
    def sendReply(self, text: str) -> None:
        text = text.strip()
        if not text or not self.dev or self._thread_id < 0:
            return
        self.dev.reply(self._thread_id, text)

    @Slot(str, str)
    def sendNew(self, number: str, text: str) -> None:
        if self.dev and number.strip() and text.strip():
            self.dev.send_new([n.strip() for n in number.split(",") if n.strip()], text.strip())
            self.toast.emit(self.tr("Message sent"))

    @Slot(str, result=int)
    def threadForNumber(self, number: str) -> int:
        """Existing 1:1 thread for a number, or -1."""
        if not self.dev:
            return -1
        k = number_key(number)
        for m in self.dev.threads.values():
            if len(m.addresses) == 1 and number_key(m.addresses[0]) == k:
                return m.thread_id
        return -1

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

    # ================================================================ calls
    def _on_tel(self, kind: str, payload) -> None:
        ringing = self.tel.ringing()
        if ringing and not self._call_notification:
            self._notify_call(ringing)
        elif not ringing and self._call_notification:
            desktop_notify.close(self._call_notification)
            self._call_notification = 0
        self.callChanged.emit()

    def _notify_call(self, call) -> None:
        name = self._name(call.number) if call.number else (call.name or self.tr("Unknown caller"))
        body = name if name == call.number or not call.number else f"{name}\n{call.number}"
        self._call_notification = desktop_notify.notify(
            self.tr("Incoming call"), body, "call-start",
            [("answer", self.tr("Answer")), ("decline", self.tr("Decline")), ("default", "")],
            self._on_call_notification_action, urgency=2, category="call.incoming", resident=True)

    def _on_call_notification_action(self, action: str) -> None:
        if action == "answer":
            self.tel.answer()
            self.showWindowRequested.emit()
        elif action == "decline":
            self.tel.decline()
        elif action == "default":
            self.showWindowRequested.emit()
        self._call_notification = 0

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
