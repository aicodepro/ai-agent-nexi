"""Re-exports redact_sensitive from the authoritative engine/memory_safety.py.

Kept as a separate module to avoid breaking existing imports. All redaction
logic is owned by engine/memory_safety.py — edit there, not here.
"""
from engine.memory_safety import redact_sensitive, VENDOR_KEY_PATTERN

_REDACTED_PLACEHOLDER = "[REDACTED]"


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
