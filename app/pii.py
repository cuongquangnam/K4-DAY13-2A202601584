from __future__ import annotations

import hashlib
import re

PII_PATTERNS: dict[str, str] = {
    # Order matters: credit_card runs before cccd so a 16-digit card is not
    # partially eaten by the 12-digit rule, and both run before bare-number
    # patterns.
    "email": r"[\w\.-]+@[\w\.-]+\.\w+",
    "phone_vn": r"(?<!\d)(?:\+84|0)(?:[ .-]?\d){9}(?!\d)",
    "credit_card": r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b",
    "cccd": r"\b\d{12}\b",
    # Vietnamese passport: one letter + 7 digits. A bare [A-Z]\d{7} also matches
    # trace and ticket IDs, so require a nearby keyword to keep IDs readable.
    "passport_vn": r"(?i)\b(?:hộ chiếu|ho chieu|passport)\s*:?\s*[A-Z]\d{7}\b",
    # Address: keyword-anchored so ordinary prose is left alone. Accented and
    # unaccented spellings both appear in real user input.
    "address_vn": (
        r"(?i)\b(?:số nhà|so nha|đường|duong|phố|pho|ngõ|ngo|hẻm|hem|"
        r"quận|quan|phường|phuong|thôn|thon|xã|xa|huyện|huyen)\s+"
        r"[\w/.\- ]{1,40}?(?=[,.;\n]|$)"
    ),
    "bank_account_vn": (
        r"(?i)\b(?:stk|số tài khoản|so tai khoan|tài khoản|tai khoan)"
        r"\s*:?\s*\d{8,16}\b"
    ),
}


def scrub_text(text: str) -> str:
    safe = text
    for name, pattern in PII_PATTERNS.items():
        safe = re.sub(pattern, f"[REDACTED_{name.upper()}]", safe)
    return safe


def summarize_text(text: str, max_len: int = 80) -> str:
    safe = scrub_text(text).strip().replace("\n", " ")
    return safe[:max_len] + ("..." if len(safe) > max_len else "")


def hash_user_id(user_id: str) -> str:
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:12]
