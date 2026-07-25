# ui_event_bridge.py
#
# Pushes Nexi backend state to the Mark-style Eel UI.
# Single source of truth for UI state updates.
# Safe: redacts secrets, survives Eel failure, no API key exposure.

from __future__ import annotations

import json
import threading
from typing import Any

_lock = threading.Lock()

_ALLOWED_STATES = {
    "idle", "listening", "thinking", "speaking", "processing",
    "error", "sleeping", "wake_detected", "transcribing",
    "hotword_detected", "double_clap_detected", "recognising", "online",
    "waiting_for_speech",
}

_SECRET_PATTERNS = [
    "api_key", "apikey", "secret", "token", "password", "auth",
    "GEMINI_API_KEY", "GROQ_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
]


def _redact_secrets(text: str) -> str:
    if not text:
        return ""
    result = text
    for pattern in _SECRET_PATTERNS:
        if pattern in result.lower():
            result = result.replace(pattern, "***")
    return result


def _safe_eel_call(fn_name: str, payload: dict[str, Any]) -> bool:
    try:
        import eel
        getattr(eel, fn_name)(payload)
        return True
    except AttributeError:
        print(f"[UI_BRIDGE] eel.{fn_name} not exposed", flush=True)
        return False
    except Exception as e:
        print(f"[UI_BRIDGE] eel.{fn_name} failed reason={type(e).__name__}", flush=True)
        return False


def studio_event(*, run_id: str = "", stage: str = "", status: str = "",
                 gate: str = "", agent: str = "", model: str = "", mode: str = "",
                 message: str = "", completed: list[str] | None = None,
                 total_stages: int = 0) -> dict[str, Any]:
    """Push a live Studio/agency update to the UI panel.

    Darsh wants a dedicated space that opens when a build runs and shows what NEXI is
    doing right now — which stage, which agent, which model/mode, and what finished.
    Everything is redacted and length-capped because stage messages can carry tool output.
    Best-effort: if the UI is closed, `_safe_eel_call` logs and the build carries on.
    """
    payload = {
        "run_id": str(run_id)[:64],
        "stage": str(stage)[:64],
        "status": str(status)[:32],
        "gate": str(gate)[:16],
        "agent": str(agent)[:64],
        "model": str(model)[:80],
        "mode": str(mode)[:32],
        "message": _redact_secrets(str(message or "")[:500]),
        "completed": [str(s)[:64] for s in (completed or [])][:20],
        "total_stages": int(total_stages or 0),
    }
    with _lock:
        _safe_eel_call("studioEvent", payload)
        print(f"[UI_BRIDGE] studio stage={payload['stage']} status={payload['status']}", flush=True)
        return payload


def set_state(state: str) -> dict[str, Any]:
    with _lock:
        from engine.ui_state_manager import canonical_state, emit_state
        safe_state = canonical_state(state)
        event = emit_state(safe_state, source="system", status=state or safe_state)
        payload = event.to_payload() if event else {"state": safe_state, "source": "system"}
        print(f"[UI_BRIDGE] set_state={safe_state}", flush=True)
        return payload


def append_user_message(text: str) -> dict[str, Any]:
    safe = _redact_secrets((text or "")[:2000])
    with _lock:
        _safe_eel_call("senderText", {"text": safe})
        return {"ok": True}


def append_assistant_message(text: str) -> dict[str, Any]:
    safe = _redact_secrets((text or "")[:5000])
    with _lock:
        _safe_eel_call("receiverText", {"text": safe})
        return {"ok": True}


def append_log(level: str, message: str) -> dict[str, Any]:
    safe_level = level if level in {"info", "warn", "error", "route", "tool", "voice"} else "info"
    safe_msg = _redact_secrets((message or "")[:500])
    print(f"[UI_LOG] level={safe_level} message={safe_msg[:120]}", flush=True)
    return {"ok": True, "level": safe_level, "message": safe_msg}


def show_error(message: str) -> dict[str, Any]:
    safe = _redact_secrets((message or "")[:300])
    with _lock:
        payload = {"state": "error", "source": "system", "text": safe}
        _safe_eel_call("updateNexiState", payload)
        print(f"[UI_BRIDGE] show_error message={safe[:120]}", flush=True)
        return payload


def speech_start() -> dict[str, Any]:
    return set_state("saying")


def speech_stop() -> dict[str, Any]:
    return set_state("sleep")


def listening_start() -> dict[str, Any]:
    return set_state("listening")


def listening_stop() -> dict[str, Any]:
    return set_state("sleep")


def thinking_start() -> dict[str, Any]:
    return set_state("thinking")


def thinking_stop() -> dict[str, Any]:
    return set_state("sleep")


def wake_detected() -> dict[str, Any]:
    return set_state("wake_detected")


def sleeping() -> dict[str, Any]:
    return set_state("sleep")
