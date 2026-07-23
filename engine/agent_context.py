from __future__ import annotations

import json
import time
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class ContextMessage:
    role: str
    content: str
    timestamp: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "content": self.content}


@dataclass
class StructuredContext:
    user_intent: str = ""
    last_action: str = ""
    last_result: str = ""
    current_step: str = ""
    environment: dict[str, Any] = field(default_factory=dict)
    working_memory: dict[str, Any] = field(default_factory=dict)

    def update(self, **kw):
        for k, v in kw.items():
            if hasattr(self, k):
                setattr(self, k, v)

    def to_prompt_block(self) -> str:
        parts = ["[Context]"]
        if self.user_intent:
            parts.append(f"  Intent: {self.user_intent[:300]}")
        if self.last_action:
            parts.append(f"  Last: {self.last_action} → {str(self.last_result)[:200]}")
        if self.current_step:
            parts.append(f"  Step: {self.current_step}")
        if self.environment:
            env_str = "; ".join(f"{k}={v}" for k, v in list(self.environment.items())[:5])
            parts.append(f"  Env: {env_str}")
        if self.working_memory:
            mem_str = "; ".join(f"{k}={v}" for k, v in list(self.working_memory.items())[:3])
            parts.append(f"  Memory: {mem_str}")
        return "\n".join(parts)


class ContextManager:
    def __init__(self, max_turns: int = 25, max_tokens: int = 8000):
        self._messages: list[ContextMessage] = []
        self.max_turns = max_turns
        self.max_tokens = max_tokens
        self._structured = StructuredContext()
        self._token_estimate: int = 0

    def add(self, role: str, content: str, metadata: Optional[dict[str, Any]] = None):
        msg = ContextMessage(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {},
        )
        self._messages.append(msg)
        self._token_estimate += self._count_tokens(content) + 4
        self._prune()

    def _count_tokens(self, text: str) -> int:
        return len(text) // 4 + 1

    def _prune(self):
        while len(self._messages) > self.max_turns * 2:
            removed = self._messages.pop(0)
            self._token_estimate -= self._count_tokens(removed.content) + 4
        while self._token_estimate > self.max_tokens and len(self._messages) > 4:
            removed = self._messages.pop(0)
            self._token_estimate -= self._count_tokens(removed.content) + 4

    def get_history(self, n: Optional[int] = None) -> list[dict[str, Any]]:
        msgs = self._messages
        if n:
            msgs = msgs[-n:]
        return [m.to_dict() for m in msgs]

    def recent(self, roles: Optional[list[str]] = None, n: int = 5) -> list[ContextMessage]:
        filtered = [m for m in self._messages if not roles or m.role in roles]
        return filtered[-n:]

    def structured(self) -> StructuredContext:
        return self._structured

    def system_prompt(self, extra: str = "") -> str:
        parts = [
            "You are Nexi, an autonomous AI assistant with tool-use capability.",
            self._structured.to_prompt_block(),
        ]
        if extra:
            parts.append(extra)
        return "\n\n".join(parts)

    def build_messages(self, system_extra: str = "", recent_n: Optional[int] = None) -> list[dict[str, Any]]:
        messages = [{"role": "system", "content": self.system_prompt(system_extra)}]
        messages.extend(self.get_history(recent_n))
        return messages

    def save(self, path: str):
        data = {
            "messages": [asdict(m) for m in self._messages],
            "structured": asdict(self._structured),
            "max_turns": self.max_turns,
            "max_tokens": self.max_tokens,
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str):
        with open(path) as f:
            data = json.load(f)
        self._messages = [ContextMessage(**m) for m in data.get("messages", [])]
        self._structured = StructuredContext(**data.get("structured", {}))
        self.max_turns = data.get("max_turns", 25)
        self.max_tokens = data.get("max_tokens", 8000)
        self._token_estimate = sum(self._count_tokens(m.content) + 4 for m in self._messages)

    def clear(self):
        self._messages.clear()
        self._token_estimate = 0

    def token_count(self) -> int:
        return self._token_estimate

    def message_count(self) -> int:
        return len(self._messages)
