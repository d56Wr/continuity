"""Find one-time security codes in SMS text (like macOS "Security Code AutoFill")."""
from __future__ import annotations

import re

# words that mark a message as carrying a code (cs, en, de, sk, pl and common services)
_KEYWORDS = re.compile(
    r"k[oó]d|code|heslo|hesla|pin\b|otp|ověř|overen|ověřen|potvr[dz]|autoriza|přihláš|prihlas|"
    r"verif|password|passcode|login|sign.?in|confirm|token|tan\b|bestätig|kod\b|weryfik|jednoráz",
    re.IGNORECASE)

# 4–8 digits, optionally split in two halves ("123 456", "123-456"); alphanumeric codes like G-123456
_CANDIDATE = re.compile(r"(?<![\w+/.,:-])(?:[A-Z]{1,3}-)?(\d{3,4}[ -]\d{3,4}|\d{4,8})(?![\w/.,:-]*\d)")
# things that look like numbers but aren't codes
_NOT_CODE = re.compile(r"^(19|20)\d{2}$")  # a year


def find_code(text: str) -> str:
    """The security code in `text`, digits only, or "" if the message doesn't look like one."""
    if not text or not _KEYWORDS.search(text):
        return ""
    best = ""
    for m in _CANDIDATE.finditer(text):
        digits = re.sub(r"\D", "", m.group(1))
        if not 4 <= len(digits) <= 8 or _NOT_CODE.match(digits):
            continue
        # amounts ("1500 Kč", "€ 2000") and phone numbers are not codes
        after = text[m.end():m.end() + 4].lower()
        before = text[max(0, m.start() - 2):m.start()]
        if re.match(r"\s?(kč|czk|eur|€|\$|,-|usd|%)", after) or re.search(r"[€$]\s?$", before):
            continue
        if len(digits) > len(best):
            best = digits
            if len(best) >= 6:
                break
    return best
