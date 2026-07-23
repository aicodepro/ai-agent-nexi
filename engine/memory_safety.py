from __future__ import annotations

import re


# Bare vendor key FORMATS. Every other pattern here needs a label ("api_key: x",
# "token=y") sitting in front of the secret. A key that arrives on its own — pasted
# into chat, read off the screen by screen_read, echoed from a config file, or
# spoken as "my key is gsk_wVx..." — carries no label, so the labelled patterns all
# miss it and the raw key gets written to the memory store in cleartext.
# Matched on shape instead. Shared with engine/memory/memory_redaction.py.
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

_SECRET_PATTERNS = [
    re.compile(r"\b(api[_ -]?key|token|password|secret|cookie|private[_ -]?key)\b", re.I),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", re.I),
    re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{12,}\b", re.I),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b"),
    VENDOR_KEY_PATTERN,
]

_REDACTIONS = [
    re.compile(r"(?i)(api[_ -]?key|token|password|secret|cookie)\s*[:=]\s*\S+"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9._\-]{12,}"),
    re.compile(r"\b(?:\d[ -]*?){13,19}\b"),
    VENDOR_KEY_PATTERN,
]


def redact_sensitive(text: str) -> str:
    value = str(text or "")
    redacted = value
    for pattern in _REDACTIONS:
        redacted = pattern.sub("[REDACTED]", redacted)
    if redacted != value:
        print("[MEMORY] redacted=true", flush=True)
    return redacted


def is_safe_to_store(text: str) -> tuple[bool, str]:
    value = str(text or "")
    if not value.strip():
        return False, "empty"
    for pattern in _SECRET_PATTERNS:
        if pattern.search(value):
            print("[MEMORY] skipped reason=secret_or_sensitive", flush=True)
            return False, "secret_or_sensitive"
    return True, "ok"
