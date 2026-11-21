"""Contacts synced from the phone by KDE Connect's contacts plugin (vCards on disk)."""
from __future__ import annotations

import base64
import hashlib
import logging
import quopri
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

DATA = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
CACHE = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "continuity" / "avatars"


def number_key(number: str) -> str:
    """Comparable form of a phone number: digits only, last 9 (national significant number)."""
    digits = re.sub(r"\D", "", number or "")
    return digits[-9:] if len(digits) >= 9 else digits


@dataclass
class Contact:
    name: str
    numbers: list[str] = field(default_factory=list)
    photo: str = ""  # file path


def _unfold(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.replace("\r\n", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and lines:
            lines[-1] += raw[1:]
        elif lines and lines[-1].endswith("=") and "QUOTED-PRINTABLE" in lines[-1].split(":", 1)[0].upper():
            lines[-1] = lines[-1][:-1] + raw  # quoted-printable soft line break (vCard 2.1)
        else:
            lines.append(raw)
    return lines


def _decode_value(key: str, value: str) -> str:
    params = key.upper()
    if "QUOTED-PRINTABLE" in params:
        charset = "utf-8"
        for p in key.split(";"):
            if p.upper().startswith("CHARSET="):
                charset = p.split("=", 1)[1]
        try:
            return quopri.decodestring(value.encode("ascii", "replace")).decode(charset, "replace")
        except LookupError:
            return quopri.decodestring(value.encode("ascii", "replace")).decode("utf-8", "replace")
    return value


def _unescape(v: str) -> str:
    return v.replace("\\,", ",").replace("\\;", ";").replace("\\n", "\n").replace("\\\\", "\\")


def parse_vcard(text: str) -> Contact | None:
    name = ""
    n_field = ""
    numbers: list[str] = []
    photo_b64 = ""
    for line in _unfold(text):
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        prop = key.split(";", 1)[0].upper()
        if prop != "PHOTO":
            value = _decode_value(key, value)
        if prop == "FN":
            name = _unescape(value).strip()
        elif prop == "N" and not n_field:
            parts = [_unescape(p).strip() for p in value.split(";")]
            n_field = " ".join(p for p in (parts[1:2] + parts[0:1]) if p)
        elif prop == "TEL":
            num = value.strip()
            if num.lower().startswith("tel:"):
                num = num[4:]
            if num:
                numbers.append(num)
        elif prop == "PHOTO" and ("ENCODING=B" in key.upper() or value.startswith("data:")):
            photo_b64 = value.split(",", 1)[1] if value.startswith("data:") else value
    name = name or n_field
    if not name and not numbers:
        return None
    c = Contact(name or numbers[0], numbers)
    if photo_b64:
        try:
            raw = base64.b64decode(photo_b64)
            CACHE.mkdir(parents=True, exist_ok=True)
            p = CACHE / (hashlib.sha1(raw).hexdigest() + ".jpg")
            if not p.exists():
                p.write_bytes(raw)
            c.photo = str(p)
        except Exception:
            log.debug("bad contact photo for %s", name)
    return c


class ContactBook:
    def __init__(self, device_id: str):
        self.dir = DATA / "kpeoplevcard" / f"kdeconnect-{device_id}"
        self.contacts: list[Contact] = []
        self._by_number: dict[str, Contact] = {}
        self.reload()

    def reload(self) -> None:
        self.contacts.clear()
        self._by_number.clear()
        if not self.dir.is_dir():
            return
        for f in self.dir.glob("*.vcf"):
            try:
                c = parse_vcard(f.read_text(errors="replace"))
            except OSError:
                continue
            if not c:
                continue
            self.contacts.append(c)
            for n in c.numbers:
                self._by_number.setdefault(number_key(n), c)
        self.contacts.sort(key=lambda c: c.name.casefold())
        log.info("loaded %d contacts", len(self.contacts))

    def lookup(self, number: str) -> Contact | None:
        return self._by_number.get(number_key(number))

    def name_for(self, number: str) -> str:
        c = self.lookup(number)
        return c.name if c else number
