from __future__ import annotations

import time

_acks: dict[str, float] = {}
_ack_lock: any = None


def _get_lock():
    global _ack_lock
    if _ack_lock is None:
        import threading
        _ack_lock = threading.Lock()
    return _ack_lock


def _ack_key(session_id: str, state: str, sequence: int) -> str:
    return f"session|{session_id}|{state}|{sequence}"


def on_ui_state_ack(
    session_id: str,
    state: str,
    sequence: int,
    *,
    created_at: float = 0.0,
    label: str = "",
) -> None:
    with _get_lock():
        now = time.time()
        _acks[_ack_key(session_id, state, int(sequence))] = now
        if label:
            _acks[f"label|{session_id}|{state}|{sequence}|{label}"] = now
        if created_at:
            _acks[f"created_at|{session_id}|{state}|{sequence}"] = float(created_at)
        _acks["_last_any"] = now


def wait_for_ack(state: str, session_id: str, sequence: int, timeout_ms: int = 5000) -> bool:
    key = _ack_key(session_id, state, int(sequence))
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        with _get_lock():
            if key in _acks:
                return True
        time.sleep(0.05)
    return False


def get_last_ack() -> dict:
    with _get_lock():
        return dict(_acks)


def reset_acks() -> None:
    with _get_lock():
        _acks.clear()
