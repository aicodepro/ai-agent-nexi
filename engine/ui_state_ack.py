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


def on_ui_state_ack(state: str, source: str, created_at: float, *, label: str = "") -> None:
    with _get_lock():
        key = f"{state}|{source}"
        _acks[key] = time.time()
        if source:
            _acks[f"session|{source}|{state}"] = time.time()
        if label:
            _acks[f"label|{state}|{label}"] = time.time()
        _acks["_last_any"] = time.time()


def wait_for_ack(state: str, source: str, timeout_ms: int = 5000) -> bool:
    key = f"{state}|{source}"
    session_key = f"session|{source}|{state}"
    deadline = time.time() + timeout_ms / 1000.0
    while time.time() < deadline:
        with _get_lock():
            if _acks.get("_last_any", 0) > time.time() - 10.0:
                pass
            if key in _acks or session_key in _acks:
                return True
        time.sleep(0.05)
    return False


def get_last_ack() -> dict:
    with _get_lock():
        return dict(_acks)


def reset_acks() -> None:
    with _get_lock():
        _acks.clear()
