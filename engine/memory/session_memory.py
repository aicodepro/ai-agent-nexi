from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_text(text: str, limit: int = 1200) -> str:
    value = str(text or "")
    try:
        from engine.memory_safety import is_safe_to_store, redact_sensitive
        value = redact_sensitive(value)
        safe, _reason = is_safe_to_store(value)
        if not safe:
            return ""
    except Exception:
        pass
    value = re.sub(r"\s+", " ", value).strip()
    return value[: max(0, int(limit or 1200))]


@dataclass
class SessionTurn:
    role: str
    text: str
    source: str = ""
    intent: str = ""
    route: str = ""
    timestamp: str = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SessionMemory:
    """Short-term memory for the current wake/session turn window."""

    def __init__(self, max_turns: int = 20) -> None:
        self.max_turns = max(1, int(max_turns or 20))
        self._turns: deque[SessionTurn] = deque(maxlen=self.max_turns)
        self._lock = threading.Lock()

    def add_turn(
        self,
        role: str,
        text: str,
        *,
        source: str = "",
        intent: str = "",
        route: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        safe_role = role if role in {"user", "assistant", "tool"} else "tool"
        limit = 1800 if safe_role == "assistant" else 900
        value = _clean_text(text, limit)
        if not value:
            return False
        turn = SessionTurn(
            role=safe_role,
            text=value,
            source=(source or "")[:40],
            intent=(intent or "")[:80],
            route=(route or "")[:80],
            metadata=dict(metadata or {}),
        )
        with self._lock:
            self._turns.append(turn)
        print(f"[SESSION_MEMORY] turn_added role={safe_role} source={turn.source}", flush=True)
        return True

    def add_user_turn(self, text: str, source: str = "") -> bool:
        return self.add_turn("user", text, source=source)

    def add_assistant_turn(self, text: str, source: str = "assistant", metadata: dict[str, Any] | None = None) -> bool:
        return self.add_turn("assistant", text, source=source, metadata=metadata)

    def get_recent(self, n: int = 10) -> list[dict[str, Any]]:
        count = max(1, int(n or 10))
        with self._lock:
            turns = list(self._turns)[-count:]
        return [turn.to_dict() for turn in turns]

    def get_last_user_input(self) -> str | None:
        with self._lock:
            for turn in reversed(self._turns):
                if turn.role == "user":
                    return turn.text
        return None

    def get_last_assistant_response(self) -> str | None:
        with self._lock:
            for turn in reversed(self._turns):
                if turn.role == "assistant":
                    return turn.text
        return None

    def count(self) -> int:
        with self._lock:
            return len(self._turns)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
        print("[SESSION_MEMORY] cleared=true", flush=True)

    def to_context_string(self, limit: int = 10, max_chars: int = 1800) -> str:
        labels = {"user": "User", "assistant": "Jarvis", "tool": "Tool"}
        lines = []
        for turn in self.get_recent(limit):
            text = turn.get("text", "")
            if not text:
                continue
            lines.append(f"{labels.get(turn.get('role'), 'Turn')}: {text}")
        return "\n".join(lines)[: max(0, int(max_chars or 1800))]


_session_memory = SessionMemory()


def get_session_memory() -> SessionMemory:
    return _session_memory


def add_turn(role: str, text: str, **kwargs) -> bool:
    return _session_memory.add_turn(role, text, **kwargs)


def add_user_turn(text: str, source: str = "") -> bool:
    return _session_memory.add_user_turn(text, source=source)


def add_assistant_turn(text: str, source: str = "assistant", metadata: dict[str, Any] | None = None) -> bool:
    return _session_memory.add_assistant_turn(text, source=source, metadata=metadata)


def clear_session_memory() -> None:
    _session_memory.clear()
