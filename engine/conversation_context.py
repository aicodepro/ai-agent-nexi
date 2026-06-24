from __future__ import annotations

import re
from collections import deque
from datetime import datetime
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive


_turns: deque[dict[str, Any]] = deque(maxlen=30)
_last_assistant_response = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(text: str, limit: int = 1400) -> str:
    value = redact_sensitive(str(text or ""))
    safe, _reason = is_safe_to_store(value)
    if not safe:
        return ""
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def add_turn(role: str, text: str, source: str = "", intent: str = "", route: str = "", metadata: dict | None = None) -> None:
    global _last_assistant_response
    safe_role = role if role in {"user", "assistant", "tool"} else "tool"
    meta = metadata or {}
    value = _clean(text, 1800 if safe_role == "assistant" else 900)
    if not value:
        return
    turn = {
        "role": safe_role,
        "text": value,
        "timestamp": _now(),
        "source": (source or "")[:40],
        "intent": (intent or "")[:80],
        "route": (route or meta.get("route", ""))[:80],
        "confidence": float(meta.get("confidence", 0.0) or 0.0),
        "result_summary": str(meta.get("result_summary", ""))[:240],
        "output_id": meta.get("output_id", ""),
        "metadata": dict(meta),
    }
    _turns.append(turn)
    if safe_role == "assistant":
        _last_assistant_response = value
    print(f"[CONTEXT] turn_added role={safe_role} source={turn['source']}", flush=True)
    print(f"[WORKING_MEMORY] turn_added role={safe_role}", flush=True)


def add_user_turn(text: str, source: str) -> None:
    add_turn("user", text, source=source)


def add_assistant_turn(text: str, source: str = "brain", metadata: dict | None = None) -> None:
    add_turn("assistant", text, source=source, metadata=metadata)


def get_recent_turns(limit: int = 10) -> list[dict]:
    count = max(1, int(limit or 10))
    turns = list(_turns)[-count:]
    print(f"[CONTEXT] recent_turns_built count={len(turns)}", flush=True)
    return [dict(turn) for turn in turns]


def get_working_memory(limit: int = 10, max_chars: int = 3000) -> str:
    labels = {"user": "User", "assistant": "Nexi", "tool": "Tool"}
    lines = []
    turns = get_recent_turns(limit)
    for turn in turns:
        text = turn.get("text", "")
        if not text:
            continue
        suffix = ""
        if turn.get("intent") or turn.get("route"):
            suffix = f" [{turn.get('route', '')}/{turn.get('intent', '')}]".rstrip()
        lines.append(f"{labels.get(turn.get('role'), 'Turn')}{suffix}: {text}")
    compact = "\n".join(lines)[:max(0, int(max_chars or 3000))]
    print(f"[WORKING_MEMORY] context_built turns={len(turns)}", flush=True)
    return compact


def get_current_task_context() -> dict:
    latest_assistant = get_last_assistant_response()
    recent_reference = None
    try:
        recent_reference = find_recent_reference("it")
    except Exception:
        recent_reference = None
    return {
        "recent_turns_count": len(_turns),
        "last_assistant_response": latest_assistant[:500],
        "recent_reference": recent_reference or {},
    }


def get_recent_context_text(limit: int = 10, max_chars: int = 2500) -> str:
    labels = {"user": "User", "assistant": "Nexi", "tool": "Tool"}
    lines = []
    for turn in get_recent_turns(limit):
        text = turn.get("text", "")
        if text:
            lines.append(f"{labels.get(turn.get('role'), 'Turn')}: {text}")
    compact = "\n".join(lines)
    return compact[:max(0, int(max_chars or 2500))]


def find_recent_reference(query: str) -> dict | None:
    q = (query or "").lower()
    wants_output = any(token in q for token in ("it", "that", "shorter", "continue", "copy", "latest", "before"))
    if not wants_output:
        return None
    for turn in reversed(_turns):
        if turn.get("role") == "assistant" and turn.get("text"):
            result = dict(turn)
            result["reference_type"] = "latest_assistant_output"
            print("[CONTEXT] reference_found type=latest_assistant_output", flush=True)
            return result
    return None


def get_last_assistant_response() -> str:
    return _last_assistant_response


def clear_recent_context() -> None:
    global _last_assistant_response
    _turns.clear()
    _last_assistant_response = ""


def build_compact_context(limit: int = 10) -> str:
    return get_working_memory(limit=limit, max_chars=2500)
