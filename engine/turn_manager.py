from __future__ import annotations

import threading

_lock = threading.Lock()
_state = "idle"
_last_question = ""
_reason = ""
_workflow_id = ""
_auto_listen_requested = False
_interrupted = False
_interrupt_source = ""
_interrupt_reason = ""


def mark_user_turn_started(source: str) -> None:
    global _state, _auto_listen_requested
    with _lock:
        _state = "listening"
        _auto_listen_requested = False
    print(f"[TURN] user_turn_started source={(source or 'unknown').strip() or 'unknown'}", flush=True)


def mark_assistant_speaking(text: str = "") -> None:
    global _state
    with _lock:
        _state = "speaking"
    print("[TURN] state=speaking", flush=True)


def mark_assistant_done(text: str = "") -> None:
    global _state
    with _lock:
        if _state == "speaking":
            _state = "idle"
    print("[TURN] state=idle", flush=True)


def mark_waiting_for_user(question: str, reason: str = "", workflow_id: str | None = None) -> None:
    global _state, _last_question, _reason, _workflow_id, _auto_listen_requested
    safe_reason = (reason or "assistant_question").strip() or "assistant_question"
    with _lock:
        _state = "waiting_for_user_answer"
        _last_question = (question or "").strip()[:500]
        _reason = safe_reason
        _workflow_id = (workflow_id or "").strip()
        _auto_listen_requested = True
    print(f"[TURN] waiting_for_user followup_type={(workflow_id or safe_reason or 'generic')}", flush=True)
    print(f"[TURN] state=waiting_for_user reason={safe_reason}", flush=True)
    print(f"[TURN] auto_listen requested reason={safe_reason}", flush=True)


def should_auto_listen() -> bool:
    with _lock:
        return bool(_auto_listen_requested)


def consume_auto_listen_request() -> bool:
    global _auto_listen_requested
    with _lock:
        requested = bool(_auto_listen_requested)
        _auto_listen_requested = False
        return requested


def request_interrupt(source: str, reason: str = "") -> None:
    global _state, _interrupted, _interrupt_source, _interrupt_reason
    safe_source = (source or "unknown").strip() or "unknown"
    safe_reason = (reason or "").strip()
    with _lock:
        _state = "interrupted"
        _interrupted = True
        _interrupt_source = safe_source
        _interrupt_reason = safe_reason
    print(f"[TURN] interrupted source={safe_source} reason={safe_reason}", flush=True)


def is_interrupted() -> bool:
    with _lock:
        return bool(_interrupted)


def clear_interrupt() -> None:
    global _interrupted, _interrupt_source, _interrupt_reason
    with _lock:
        _interrupted = False
        _interrupt_source = ""
        _interrupt_reason = ""


def get_turn_state() -> dict:
    with _lock:
        return {
            "state": _state,
            "last_question": _last_question,
            "reason": _reason,
            "workflow_id": _workflow_id,
            "auto_listen_requested": _auto_listen_requested,
            "interrupted": _interrupted,
            "interrupt_source": _interrupt_source,
            "interrupt_reason": _interrupt_reason,
        }
