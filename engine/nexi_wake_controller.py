from __future__ import annotations

import threading

_wake_queue = None
_awake = False
_lock = threading.Lock()


def set_wake_queue(queue) -> None:
    global _wake_queue
    with _lock:
        _wake_queue = queue


def is_nexi_awake() -> bool:
    with _lock:
        return _awake


def wake_nexi(source: str) -> bool:
    """Wake internal Nexi, update UI state, start command capture.

    Status events (wake_detected, listening) are already posted by the
    AudioWakePipeline via InternalWakeSignalBus. This function only sets
    the internal awake flag and handles interruption. No duplicate posts.
    """
    global _awake
    safe_source = (source or "unknown").strip() or "unknown"
    with _lock:
        _awake = True
    try:
        from engine.interrupt_controller import is_speaking, request_interrupt, clear_interrupt
        if is_speaking():
            request_interrupt(source=safe_source, reason="wake")
            clear_interrupt()
    except Exception:
        pass
    print(f"[WAKE] internal_wake source={safe_source}", flush=True)
    return True


def sleep_nexi(reason: str = "") -> bool:
    """Put Nexi into sleep/idle state."""
    global _awake
    safe_reason = (reason or "").strip()
    with _lock:
        _awake = False
        queue = _wake_queue
    try:
        from engine.interrupt_controller import is_speaking, request_interrupt, clear_interrupt
        if is_speaking():
            request_interrupt(source="sleep", reason=safe_reason)
            clear_interrupt()
    except Exception:
        pass
    print(f"[WAKE] internal_sleep reason={safe_reason}", flush=True)
    if queue is not None:
        try:
            from engine.runtime_bridge import post_status
            post_status(queue, "sleeping", source="system")
        except Exception as e:
            print(f"[WAKE] internal_sleep_status_failed reason={type(e).__name__}", flush=True)
    return True
