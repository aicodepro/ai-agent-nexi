"""Text-to-Speech — Groq TTS (primary) + pyttsx3 (fallback)."""

import os
import json
import time
import tempfile
import threading
from core.config import cfg

_speaking = False
_speak_lock = threading.Lock()
_interrupt_requested = False


def _get_tts_provider() -> str:
    return cfg.tts_provider_order or "groq"


_speaking_event = None


def set_speaking_event(ev) -> None:
    """Register a cross-process flag set while NEXI is speaking.

    The wake pipeline checks this so the mic ignores NEXI's own voice
    (prevents a self-listening feedback loop).
    """
    global _speaking_event
    _speaking_event = ev


def is_speaking() -> bool:
    return _speaking


def request_interrupt():
    global _interrupt_requested
    _interrupt_requested = True


def clear_interrupt():
    global _interrupt_requested
    _interrupt_requested = False


def _should_interrupt() -> bool:
    return _interrupt_requested


def _set_speaking(val: bool):
    global _speaking
    _speaking = val


def speak_groq(text: str) -> bool:
    """TTS via Groq API. Returns True on success."""
    api_key = cfg.groq_api_key
    if not api_key:
        return False
    try:
        import urllib.request
        import urllib.error
        body = json.dumps({
            "model": cfg.groq_tts_model,
            "input": text[:1500],
            "voice": cfg.groq_tts_voice,
            "response_format": "wav",
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/audio/speech",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        timeout = int(os.getenv("GROQ_TTS_TIMEOUT_SECONDS", "10"))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            audio_bytes = resp.read()
        if not audio_bytes:
            return False
        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.write(audio_bytes)
        tmp.close()
        try:
            from playsound3 import playsound
            _set_speaking(True)
            playsound(tmp.name)
        finally:
            _set_speaking(False)
            try:
                os.unlink(tmp.name)
            except OSError:
                pass
        return True
    except urllib.error.HTTPError as e:
        print(f"[TTS] groq_failed http={e.code} (check GROQ_TTS_MODEL terms/rate limits; "
              f"falling back to pyttsx3)", flush=True)
        return False
    except Exception as e:
        print(f"[TTS] groq_failed reason={type(e).__name__}", flush=True)
        return False


def speak_pyttsx3(text: str) -> bool:
    """Offline TTS via pyttsx3. Returns True on success."""
    try:
        import pyttsx3
        engine = pyttsx3.init("sapi5")
        voices = engine.getProperty("voices")
        if voices:
            engine.setProperty("voice", voices[0].id)
        engine.setProperty("rate", 175)
        _set_speaking(True)
        engine.say(text)
        engine.runAndWait()
        _set_speaking(False)
        return True
    except Exception as e:
        _set_speaking(False)
        print(f"[TTS] pyttsx3_failed reason={type(e).__name__}", flush=True)
        return False


def _summarize(text: str, limit: int = 700) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "..."


def speak(text: str, display: bool = True) -> None:
    """Main TTS entry — tries providers in order, handles interrupts and UI."""
    if not text or not text.strip():
        return

    if _should_interrupt():
        clear_interrupt()
        return

    voice_text = _summarize(text) if cfg.tts_summarize else text

    if display:
        try:
            from core.ui_state import emit_state, safe_eel_call
            emit_state("saying", text=voice_text[:80])
            safe_eel_call("receiverText", text)
        except Exception:
            pass

    if _speaking_event is not None:
        _speaking_event.set()
    try:
        for provider in cfg.tts_providers:
            if _should_interrupt():
                clear_interrupt()
                return
            if provider == "groq" and speak_groq(voice_text):
                break
            elif provider == "pyttsx3" and speak_pyttsx3(voice_text):
                break
        else:
            print("[TTS] all_providers_failed", flush=True)
    finally:
        if _speaking_event is not None:
            _speaking_event.clear()

    try:
        from core.ui_state import emit_state
        if cfg.auto_listen_after_question:
            emit_state("listening")
        else:
            emit_state("sleep")
    except Exception:
        pass
