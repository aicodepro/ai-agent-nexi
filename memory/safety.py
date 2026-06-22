"""Memory safety — redaction and content filtering."""

import re

SECRET_WORDS = {"password", "passwd", "token", "api_key", "apikey", "api key",
                "secret", "credential", "private_key", "access_key", "auth_token",
                "cookie", "session_id", "credit card", "cvv", "ssn", "otp"}

_REDACT_PATTERNS = [
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b\d{10,15}\b"), "[PHONE]"),
    (re.compile(r"\b(?:sk-|pk-|Bearer\s+)[A-Za-z0-9_-]{20,}\b"), "[API_KEY]"),
    (re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b"), "[CARD]"),
    (re.compile(r"\b\d{6}\b(?=.*otp)", re.IGNORECASE), "[OTP]"),
]


def is_safe_to_store(text: str) -> bool:
    lower = text.lower()
    return not any(w in lower for w in SECRET_WORDS)


def redact_sensitive(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def clean_for_storage(text: str, limit: int = 500) -> str:
    if not is_safe_to_store(text):
        return ""
    text = redact_sensitive(text)
    return text[:limit].strip()
