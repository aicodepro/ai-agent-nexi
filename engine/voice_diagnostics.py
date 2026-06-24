from __future__ import annotations

import json
from typing import Any


def _safe_bool(fn, default: bool = False) -> bool:
    try:
        return bool(fn())
    except Exception:
        return default


def get_voice_diagnostics() -> dict[str, Any]:
    from engine.voice_state_machine import get_voice_state_machine

    vsm = get_voice_state_machine()
    state = vsm.get_state()
    last_transition = vsm.get_last_transition()
    tts_active = _safe_bool(lambda: __import__("engine.interrupt_controller", fromlist=["is_speaking"]).is_speaking())
    cooldown_remaining = 0
    try:
        from engine.post_tts_cleanup import get_cooldown_remaining_ms
        cooldown_remaining = max(cooldown_remaining, int(get_cooldown_remaining_ms()))
    except Exception:
        pass
    try:
        cooldown_remaining = max(cooldown_remaining, int(vsm.get_cooldown_remaining_ms()))
    except Exception:
        pass

    memory_exchange_count = 0
    rolling_summary_status = "unavailable"
    try:
        from engine.autonomous_memory import get_last_exchanges, get_rolling_summary
        exchanges = get_last_exchanges()
        summary = get_rolling_summary()
        memory_exchange_count = len(exchanges)
        rolling_summary_status = "present" if summary.strip() else "empty"
    except Exception:
        pass

    hotword_active = False
    try:
        from engine.audio_wake_pipeline import OWW_ENABLED
        hotword_active = bool(OWW_ENABLED)
    except Exception:
        hotword_active = False

    return {
        "current_voice_state": state,
        "previous_voice_state": vsm.get_previous_state(),
        "last_transition_event": last_transition.get("event", ""),
        "last_transition": last_transition,
        "tts_active": tts_active,
        "hotword_detector_active": hotword_active,
        "full_command_listening_active": state in {"listening", "recording_utterance"},
        "interrupt_listening_active": state == "speaking" or tts_active,
        "last_transcript": vsm.get_last_transcript(),
        "last_ignored_voice_event_reason": vsm.get_last_ignored_voice_event_reason(),
        "cooldown_remaining_ms": cooldown_remaining,
        "memory_exchange_count": memory_exchange_count,
        "rolling_summary_status": rolling_summary_status,
        "last_interruption_reason": vsm.get_last_interruption_reason(),
    }


def format_voice_diagnostics(payload: dict[str, Any] | None = None) -> str:
    payload = payload or get_voice_diagnostics()
    lines = [
        f"Voice state: {payload.get('current_voice_state', '')}",
        f"Previous state: {payload.get('previous_voice_state', '') or 'none'}",
        f"Last transition: {payload.get('last_transition_event', '') or 'none'}",
        f"TTS active: {payload.get('tts_active')}",
        f"Hotword detector active: {payload.get('hotword_detector_active')}",
        f"Full command listening active: {payload.get('full_command_listening_active')}",
        f"Interrupt listening active: {payload.get('interrupt_listening_active')}",
        f"Last transcript: {(payload.get('last_transcript') or 'none')[:120]}",
        f"Last ignored voice event: {payload.get('last_ignored_voice_event_reason') or 'none'}",
        f"Cooldown remaining: {payload.get('cooldown_remaining_ms', 0)} ms",
        f"Memory exchanges: {payload.get('memory_exchange_count', 0)}",
        f"Rolling summary: {payload.get('rolling_summary_status', 'unknown')}",
        f"Last interruption reason: {payload.get('last_interruption_reason') or 'none'}",
    ]
    return "\n".join(lines)


def format_last_ten_exchanges() -> str:
    try:
        from engine.autonomous_memory import get_last_exchanges
        exchanges = get_last_exchanges(10)
    except Exception:
        exchanges = []
    if not exchanges:
        return "No recent exchanges stored."
    rendered = []
    for idx, ex in enumerate(exchanges, 1):
        user = (ex.get("user_text") or "")[:120]
        assistant = (ex.get("assistant_text") or "")[:120]
        rendered.append(f"{idx}. User: {user or 'none'} | Nexi: {assistant or 'none'}")
    return "\n".join(rendered)


def diagnostics_json() -> str:
    return json.dumps(get_voice_diagnostics(), ensure_ascii=False)
