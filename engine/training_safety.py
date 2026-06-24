from __future__ import annotations

import re
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive


_BLOCKED = re.compile(
    r"\b(api[_ -]?key|token|password|secret|cookie|private[_ -]?key|aadhaar|aadhar|credit card|card number|cvv)\b"
    r"|\b(i am conscious|i am alive|i am sentient|i feel|real self-awareness)\b"
    r"|\b(ignore safety|bypass safety|fake tool success|pretend.*succeeded)\b",
    re.I,
)


def redact_training_text(text: str) -> str:
    return redact_sensitive(str(text or ""))


def is_safe_training_item(item: dict) -> bool:
    text = " ".join(str(value) for value in (item or {}).values() if isinstance(value, (str, int, float)))
    text = redact_training_text(text)
    if _BLOCKED.search(text):
        print("[TRAINING_SAFETY] blocked=true", flush=True)
        return False
    safe, _reason = is_safe_to_store(text)
    return bool(safe)


def validate_training_rule(rule: dict) -> dict:
    data = dict(rule or {})
    if not is_safe_training_item(data):
        return {"valid": False, "reason": "unsafe_training_item", "rule": {}}
    for key in ("trigger", "action", "negative_action", "condition", "need"):
        if key in data:
            data[key] = redact_training_text(str(data.get(key) or ""))[:500]
    examples = []
    for example in data.get("examples", []) or []:
        value = redact_training_text(str(example or ""))[:800]
        if value and not _BLOCKED.search(value):
            examples.append(value)
    if examples:
        data["examples"] = examples[-5:]
    return {"valid": True, "reason": "ok", "rule": data}


def validate_text(text: str) -> tuple[bool, str]:
    value = redact_training_text(text)
    if _BLOCKED.search(value):
        return False, "unsafe_training_text"
    return is_safe_to_store(value)
