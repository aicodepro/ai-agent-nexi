from __future__ import annotations

import re


VENDOR_KEY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])("
    r"gsk_[A-Za-z0-9]{20,}"                 # Groq
    r"|AIza[A-Za-z0-9_\-]{35}"              # Google / Gemini
    r"|sk-ant-[A-Za-z0-9_\-]{20,}"          # Anthropic
    r"|sk-(?:proj-)?[A-Za-z0-9_\-]{20,}"    # OpenAI
    r"|gh[pousr]_[A-Za-z0-9]{36,}"          # GitHub
    r"|xox[baprs]-[A-Za-z0-9\-]{10,}"       # Slack
    r"|AKIA[0-9A-Z]{16}"                    # AWS access key id
    r"|hf_[A-Za-z0-9]{30,}"                 # HuggingFace
    r")"
)

_EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b')
_PHONE_PATTERN = re.compile(
    r'\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b'
)
_API_KEY_LIKE = re.compile(
    r'(?i)(api[_-]?key|apikey|api_key|token|secret|password|passwd|pwd)'
    r'\s*[=:]\s*\S{6,}'
)
_CARD_PATTERN = re.compile(r'\b(?:\d[ -]*?){13,19}\b')
_OTP_PATTERN = re.compile(
    r'(?i)(otp|one[ -]?time[ -]?pin|verification[ -]?code)\s*[=:]\s*\S+'
)
_BEARER_PATTERN = re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]{12,}")
_KEY_LABEL_PATTERN = re.compile(
    # separator may be ':', '=' or natural language ("my api key is abc123"),
    # otherwise spoken/typed secrets slip past is_safe_to_store().
    r"(?i)(api[_ -]?key|apikey|token|password|passwd|pwd|secret|cookie)"
    r"(?:\s*[:=]\s*|\s+is\s+|\s+was\s+)\S+"
)

# Bare mention of a high-signal secret word is enough to refuse storage, even
# without a "key: value" separator (e.g. "api key leaked"). 'token'/'cookie' are
# deliberately excluded here - too common in ordinary speech - and still match
# via _KEY_LABEL_PATTERN when they carry a value.
_SECRET_WORD_PATTERN = re.compile(
    r"(?i)\b(api[_ -]?key|apikey|password|passwd|private[_ -]?key|credential[s]?)\b"
)

_SECRET_PATTERNS = [
    _SECRET_WORD_PATTERN,
    _KEY_LABEL_PATTERN,
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    _BEARER_PATTERN,
    _CARD_PATTERN,
    VENDOR_KEY_PATTERN,
]

_REDACTIONS = [
    _KEY_LABEL_PATTERN,
    _BEARER_PATTERN,
    _CARD_PATTERN,
    VENDOR_KEY_PATTERN,
    _EMAIL_PATTERN,
    _PHONE_PATTERN,
    _API_KEY_LIKE,
    _OTP_PATTERN,
]

_REDACTED_PLACEHOLDER = "[REDACTED]"


def redact_sensitive(text: str) -> str | None:
    if text is None:
        return None
    value = str(text or "")
    t = value
    for pattern in _REDACTIONS:
        t = pattern.sub(_REDACTED_PLACEHOLDER, t)
    if t != value:
        print("[MEMORY] redacted=true", flush=True)
    return t


def is_safe_to_store(text: str) -> tuple[bool, str]:
    value = str(text or "")
    if not value.strip():
        return False, "empty"
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            print("[MEMORY] skipped reason=secret_or_sensitive", flush=True)
            return False, "secret_or_sensitive"
    return True, "ok"
