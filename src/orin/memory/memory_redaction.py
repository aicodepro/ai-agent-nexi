import re

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

_REDACTED_PLACEHOLDER = "[REDACTED]"


def redact_sensitive(text):
    if not text or not isinstance(text, str):
        return text
    t = text
    t = _API_KEY_LIKE.sub(lambda m: m.group(1) + "=" + _REDACTED_PLACEHOLDER, t)
    t = _EMAIL_PATTERN.sub(_REDACTED_PLACEHOLDER, t)
    t = _PHONE_PATTERN.sub(_REDACTED_PLACEHOLDER, t)
    t = _CARD_PATTERN.sub(_REDACTED_PLACEHOLDER, t)
    t = _OTP_PATTERN.sub(lambda m: m.group(1) + "=" + _REDACTED_PLACEHOLDER, t)
    return t


def redact_dict(data):
    if not isinstance(data, dict):
        return data
    result = {}
    for key, value in data.items():
        if isinstance(value, str):
            result[key] = redact_sensitive(value)
        elif isinstance(value, dict):
            result[key] = redact_dict(value)
        elif isinstance(value, list):
            result[key] = [redact_sensitive(v) if isinstance(v, str) else v for v in value]
        else:
            result[key] = value
    return result


def sanitize_for_summary(memory_item):
    item = dict(memory_item)
    if "value" in item and isinstance(item["value"], str):
        item["value"] = redact_sensitive(item["value"])
    if "key" in item and isinstance(item["key"], str):
        item["key"] = redact_sensitive(item["key"])
    return item
