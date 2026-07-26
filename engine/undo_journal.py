"""What NEXI did, and how to take it back.

"Undo that" is only answerable if the assistant recorded what it changed. Each
entry carries the state before, the action, the state after, the evidence that
it happened, and the specific inverse operation - so NEXI can say

    "I removed the empty Project Alpha folder I created on your Desktop."

rather than "Undone."

Two deliberate limits:

  - Entries expire. An undo offered an hour later is a trap: the user has moved
    on and the world has changed underneath it.
  - Only reversible actions are journalled, and the inverse is checked for
    safety at undo time, not recorded as a blind command. Deleting a folder
    NEXI created is reasonable only while that folder is still the empty thing
    NEXI made.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

DEFAULT_TTL_SECONDS = 15 * 60.0
MAX_ENTRIES = 50


@dataclass
class UndoEntry:
    entry_id: str
    action: str                      # "create_folder"
    description: str                 # "created Project Alpha on your Desktop"
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)
    evidence: str = ""
    undo_action: str = ""            # "delete_empty_folder"
    undo_args: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    expires_at: float = 0.0
    undone: bool = False

    def is_expired(self, now: float | None = None) -> bool:
        stamp = time.time() if now is None else now
        return self.expires_at > 0.0 and stamp >= self.expires_at

    def is_undoable(self) -> bool:
        return bool(self.undo_action) and not self.undone and not self.is_expired()

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "action": self.action,
                "description": self.description, "undo_action": self.undo_action,
                "undo_args": dict(self.undo_args), "undone": self.undone,
                "evidence": self.evidence}


_lock = threading.RLock()
_entries: list[UndoEntry] = []
#: undo_action name -> callable(**undo_args) -> (ok, message)
_handlers: dict[str, Callable[..., tuple[bool, str]]] = {}


def register_undo_handler(name: str, handler: Callable[..., tuple[bool, str]]) -> None:
    with _lock:
        _handlers[name] = handler


def record(*, action: str, description: str, undo_action: str = "",
           undo_args: dict[str, Any] | None = None,
           before: dict[str, Any] | None = None,
           after: dict[str, Any] | None = None,
           evidence: str = "", ttl_seconds: float = DEFAULT_TTL_SECONDS) -> UndoEntry:
    now = time.time()
    entry = UndoEntry(
        entry_id=uuid.uuid4().hex[:10], action=action,
        description=(description or "").strip()[:300],
        before=dict(before or {}), after=dict(after or {}),
        evidence=str(evidence or "")[:300],
        undo_action=undo_action or "", undo_args=dict(undo_args or {}),
        created_at=now, expires_at=now + max(1.0, float(ttl_seconds)))
    with _lock:
        _entries.append(entry)
        if len(_entries) > MAX_ENTRIES:
            del _entries[:-MAX_ENTRIES]
    print(f"[UNDO] recorded action={action} undoable={bool(undo_action)}", flush=True)
    return entry


def last_undoable() -> UndoEntry | None:
    with _lock:
        for entry in reversed(_entries):
            if entry.is_undoable():
                return entry
    return None


def history(limit: int = 10) -> list[UndoEntry]:
    with _lock:
        return list(reversed(_entries[-max(1, limit):]))


def undo_last() -> tuple[bool, str]:
    """Undo the most recent reversible action.

    Returns (ok, message). The message names what was reversed, because "Undone."
    tells a user who cannot see the screen nothing at all.
    """
    entry = last_undoable()
    if entry is None:
        return False, "There's nothing recent I can undo."

    with _lock:
        handler = _handlers.get(entry.undo_action)
    if handler is None:
        return False, f"I recorded {entry.description}, but I don't know how to reverse it."

    try:
        ok, detail = handler(**entry.undo_args)
    except Exception as exc:
        print(f"[UNDO] failed action={entry.undo_action} reason={type(exc).__name__}", flush=True)
        return False, f"I couldn't undo {entry.description}."

    if not ok:
        print(f"[UNDO] refused action={entry.undo_action}", flush=True)
        return False, detail or f"I couldn't undo {entry.description}."

    with _lock:
        entry.undone = True
    print(f"[UNDO] done action={entry.undo_action}", flush=True)
    return True, detail or f"I undid {entry.description}."


def reset_for_tests() -> None:
    with _lock:
        _entries.clear()
        _handlers.clear()
