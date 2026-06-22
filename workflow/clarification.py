"""Clarification manager — handles vague commands and slot filling."""

import re

_pending = {}

_CLARIFICATION_MAP = {
    "open": ("What would you like me to open?", "open_app"),
    "search": ("What would you like me to search for?", "web_search"),
    "create": ("What would you like me to create? (file, folder, or project)", "create_file"),
    "play": ("What would you like me to play?", "play_music"),
    "find": ("What are you looking for?", "find_places"),
    "close": ("What would you like me to close?", "close_app"),
    "send": ("What would you like me to send?", "send_email"),
}


def ask_clarification(text: str, reason: str = "") -> dict | None:
    lower = text.strip().lower()

    for keyword, (question, followup_type) in _CLARIFICATION_MAP.items():
        if lower == keyword or lower == keyword + " something":
            _pending["type"] = followup_type
            _pending["question"] = question
            _pending["original"] = text
            return {"question": question, "followup_type": followup_type}

    return None


def ask_custom(question: str, followup_type: str = "general") -> dict:
    _pending["type"] = followup_type
    _pending["question"] = question
    return {"question": question, "followup_type": followup_type}


def has_pending() -> bool:
    return bool(_pending.get("type"))


def get_pending() -> dict:
    return _pending.copy()


def receive_answer(text: str) -> dict:
    if not has_pending():
        return {"handled": False}

    followup_type = _pending.get("type", "")
    clear()
    return {"handled": True, "answer": text.strip(), "followup_type": followup_type}


def clear(reason: str = ""):
    _pending.clear()
