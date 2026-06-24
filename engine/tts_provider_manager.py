from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable


@dataclass
class TTSProviderResult:
    provider: str
    ok: bool
    fallback_used: bool
    error: str = ""


def _provider_order() -> list[str]:
    primary = os.getenv("TTS_PRIMARY_PROVIDER", "").strip().lower()
    raw = os.getenv("TTS_PROVIDER_ORDER", "groq,pyttsx3")
    providers = [p.strip().lower() for p in raw.split(",") if p.strip()]
    if primary and primary not in providers:
        providers.insert(0, primary)
    return providers or ["pyttsx3"]


def speak_with_provider(
    text: str,
    *,
    display_text: str | None = None,
    fallback_speaker: Callable[[str], None] | None = None,
    on_display: Callable[[str], None] | None = None,
) -> TTSProviderResult:
    value = str(text or "")
    shown = str(display_text if display_text is not None else value)
    max_chars = int(os.getenv("TTS_MAX_CHARS", "700"))
    if len(value) > max_chars and os.getenv("TTS_SUMMARIZE_LONG_OUTPUT", "true").lower() in {"1", "true", "yes", "on"}:
        from engine.tts_response_manager import build_spoken_text
        value = build_spoken_text(value, max_chars=max_chars)

    for provider in _provider_order():
        if provider == "groq":
            from engine import groq_tts
            if not groq_tts.is_configured():
                print("[TTS] provider=pyttsx3 fallback_used=true reason=missing_groq_key", flush=True)
                continue
            if on_display:
                on_display(shown)
            result = groq_tts.speak_text(value)
            if result.ok:
                return TTSProviderResult(provider="groq", ok=True, fallback_used=False)
            error_hint = result.error[:60] if result.error else "unknown"
            print(f"[TTS] provider=pyttsx3 fallback_used=true reason=groq_failed:{error_hint}", flush=True)
            continue
        if provider == "pyttsx3" and fallback_speaker is not None:
            fallback_speaker(value)
            return TTSProviderResult(provider="pyttsx3", ok=True, fallback_used=True)

    if fallback_speaker is not None:
        fallback_speaker(value)
        return TTSProviderResult(provider="pyttsx3", ok=True, fallback_used=True)
    return TTSProviderResult(provider="none", ok=False, fallback_used=False, error="no_provider")


def stop_all() -> bool:
    stopped = False
    try:
        from engine import groq_tts
        stopped = groq_tts.stop() or stopped
    except Exception:
        pass
    try:
        from engine.interrupt_controller import request_interrupt
        request_interrupt("tts_provider_manager", "stop_all")
        stopped = True
    except Exception:
        pass
    return stopped
