"""Conversation context — in-memory turn history."""

import re
from collections import deque
from datetime import datetime
from memory.safety import redact_sensitive

_turns = deque(maxlen=30)
_last_assistant_response = ""


def _now() -> str:
    return datetime.now().isoformat()


def _clean(text: str, limit: int = 500) -> str:
    result = redact_sensitive(text)[:limit].strip()
    if len(text) > limit:
        print(f"[MEMORY] context truncated from {len(text)} to {limit} chars", flush=True)
    return result


def add_turn(role: str, text: str, source: str = "", intent: str = "",
             route: str = "", metadata: dict = None) -> None:
    global _last_assistant_response
    cleaned = _clean(text)
    if not cleaned:
        return
    turn = {
        "role": role, "text": cleaned, "source": source,
        "intent": intent, "route": route,
        "metadata": metadata or {}, "timestamp": _now(),
    }
    _turns.append(turn)
    if role == "assistant":
        _last_assistant_response = cleaned


def add_user_turn(text: str, source: str = "") -> None:
    add_turn("user", text, source=source)


def add_assistant_turn(text: str, source: str = "", metadata: dict = None) -> None:
    add_turn("assistant", text, source=source, metadata=metadata)


def get_recent_turns(limit: int = 10) -> list:
    return list(_turns)[-limit:]


def get_working_memory(limit: int = 8, max_chars: int = 2500) -> str:
    turns = get_recent_turns(limit)
    if not turns:
        return ""
    lines = []
    for t in turns:
        prefix = "User" if t["role"] == "user" else "Nexi"
        lines.append(f"{prefix}: {t['text'][:200]}")
    text = "\n".join(lines)
    return text[:max_chars]


def get_last_assistant_response() -> str:
    return _last_assistant_response


def find_recent_reference(query: str) -> str:
    """Resolve pronouns like 'it', 'that' to the last assistant response."""
    lower = query.lower().strip()
    if lower in {"it", "that", "this", "the answer", "what you said"}:
        return _last_assistant_response
    return ""


def clear() -> None:
    global _last_assistant_response
    _turns.clear()
    _last_assistant_response = ""

