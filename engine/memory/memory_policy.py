import re

SENSITIVITY_MAP = {
    "LOW": "LOW",
    "MEDIUM": "MEDIUM",
    "HIGH": "HIGH",
}

_PASSWORD_PATTERN = re.compile(
    r'(?i)(?:password|passwd|pwd)\s*[=:]\s*\S+|\bpassword\s+is\s+\S+'
)
_API_KEY_PATTERN = re.compile(
    r'(?i)(api[_-]?key|apikey|api_key)\s*[=:]\s*\S{8,}'
)
_TOKEN_PATTERN = re.compile(
    r'(?i)(token|auth_token|refresh_token|access_token|secret_token)'
    r'\s*[=:]\s*\S{8,}'
)
_COOKIE_PATTERN = re.compile(
    r'(?i)(cookie|cookies|session_id)\s*[=:]\s*\S{8,}'
)
_CARD_PATTERN = re.compile(
    r'\b(?:\d[ -]*?){13,19}\b'
)
_OTP_PATTERN = re.compile(
    r'(?i)(otp|one[ -]?time[ -]?pin|verification[ -]?code)\s*[=:]\s*\S+'
)
_SECRET_PATTERN = re.compile(
    r'(?i)(secret|private_key|ssh[_-]?key)\s*[=:]\s*\S+'
)
_PHONE_PATTERN = re.compile(
    r'\b\+?\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}\b'
)
_EMAIL_PATTERN = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'
)
_SCREENSHOT_PATTERN = re.compile(
    r'(?i)(screenshot|screen[_-]?shot|screen[_-]?capture|screen[_-]?grab)'
)
_AUDIO_PATTERN = re.compile(
    r'(?i)(raw[_-]?audio|raw\saudio|audio[_-]?recording|voice[_-]?recording|mic[_-]?capture)'
)

BLOCKED_PATTERNS = [
    _PASSWORD_PATTERN, _API_KEY_PATTERN, _TOKEN_PATTERN,
    _COOKIE_PATTERN, _CARD_PATTERN, _OTP_PATTERN, _SECRET_PATTERN,
]

CONFIRM_PATTERNS = [
    _PHONE_PATTERN, _EMAIL_PATTERN, _SCREENSHOT_PATTERN, _AUDIO_PATTERN,
]

SAFE_PREFIXES = [
    "assistant name", "my name is", "preferred", "favourite", "favorite",
    "i like", "i prefer", "i use", "my repo", "my project",
    "my browser", "my model", "my language", "speak",
]


def classify_memory_text(text):
    if not text or not text.strip():
        return "ALLOW", "Empty text"
    t = text.strip()
    for pat in BLOCKED_PATTERNS:
        if pat.search(t):
            return "REJECT", f"Contains blocked content: {pat.pattern[:40]}"
    for pat in CONFIRM_PATTERNS:
        if pat.search(t):
            return "REQUIRE_CONFIRMATION", f"Contains sensitive pattern: {pat.pattern[:40]}"
    return "ALLOW", "Safe memory content"


def classify_key_value(key, value):
    combined = f"{key} {value}"
    decision, reason = classify_memory_text(combined)
    if decision != "ALLOW":
        return decision, reason
    blocked_keys = [
        "password", "passwd", "pwd", "api_key", "apikey", "token",
        "auth_token", "cookie", "session_id", "secret", "private_key",
        "ssh_key", "otp", "pin", "credit_card", "card_number",
    ]
    k = key.lower().strip()
    for bk in blocked_keys:
        if bk in k:
            return "REJECT", f"Key '{key}' is blocked"
    if isinstance(value, str) and len(value) > 100:
        return "REQUIRE_CONFIRMATION", "Value is unusually long"
    return "ALLOW", "Safe key-value memory"


def sensitivity_for(decision):
    if decision == "REJECT":
        return "HIGH"
    if decision == "REQUIRE_CONFIRMATION":
        return "MEDIUM"
    return "LOW"


def is_key_blocked(key):
    decision, _ = classify_key_value(key, "")
    return decision == "REJECT"
