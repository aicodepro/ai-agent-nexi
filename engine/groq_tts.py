from __future__ import annotations

import json
import os
import tempfile
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

_soft_disabled_until: float = 0.0
_play_lock = threading.Lock()
_current_play_handle = None


@dataclass
class GroqTTSResult:
    ok: bool
    provider: str = "groq"
    fallback_used: bool = False
    error: str = ""
    interrupted: bool = False


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _soft_disable_cooldown_secs() -> int:
    try:
        return max(60, int(os.getenv("GROQ_TTS_SOFT_DISABLE_SECONDS", "300")))
    except (TypeError, ValueError):
        return 300


def _playback_timeout_secs() -> float:
    try:
        return max(1.0, float(os.getenv("GROQ_TTS_PLAYBACK_TIMEOUT_SECONDS", "120")))
    except (TypeError, ValueError):
        return 120.0


def is_configured() -> bool:
    global _soft_disabled_until
    try:
        from engine.demo_mode import DemoMode
        if DemoMode.use_local_tts():
            print("[TTS] provider=pyttsx3 fallback_used=true reason=demo_mode", flush=True)
            return False
    except Exception:
        pass
    if time.time() < _soft_disabled_until:
        print("[TTS] provider=pyttsx3 fallback_used=true reason=groq_soft_disabled", flush=True)
        return False
    return _env_bool("GROQ_TTS_ENABLED", True) and bool(os.getenv("GROQ_API_KEY"))


def reset_soft_disable() -> None:
    global _soft_disabled_until
    _soft_disabled_until = 0.0


def stop() -> bool:
    global _current_play_handle
    with _play_lock:
        handle = _current_play_handle
        _current_play_handle = None
    if handle is None:
        return False
    try:
        handle.stop()
        print("[TTS] groq_stop_requested=true", flush=True)
        return True
    except Exception as exc:
        print(f"[TTS] groq_stop_failed reason={type(exc).__name__}", flush=True)
        return False


def _play_with_simpleaudio(path: str) -> GroqTTSResult | None:
    if not path.lower().endswith(".wav"):
        return None
    try:
        import simpleaudio as sa
    except Exception:
        return None
    try:
        from engine.interrupt_controller import should_interrupt, get_interrupt_source
        wave_obj = sa.WaveObject.from_wave_file(path)
        handle = wave_obj.play()
        global _current_play_handle
        with _play_lock:
            _current_play_handle = handle
        started = time.monotonic()
        while handle.is_playing():
            if should_interrupt():
                stop()
                print(f"[TTS] interrupted source={get_interrupt_source() or 'unknown'}", flush=True)
                return GroqTTSResult(ok=True, interrupted=True, error="interrupted")
            if time.monotonic() - started >= _playback_timeout_secs():
                stop()
                print("[TTS] playback_timeout", flush=True)
                return GroqTTSResult(ok=False, fallback_used=True, error="playback_timeout")
            time.sleep(0.05)
        with _play_lock:
            if _current_play_handle is handle:
                _current_play_handle = None
        return GroqTTSResult(ok=True)
    except Exception as exc:
        safe_reason = str(exc)[:80] if str(exc) else type(exc).__name__
        print(f"[TTS] simpleaudio_failed reason={safe_reason}", flush=True)
        return None


def synthesize_speech(text: str) -> bytes:
    global _soft_disabled_until
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("missing_groq_api_key")
    payload = {
        "model": os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english"),
        "voice": os.getenv("GROQ_TTS_VOICE", "Fritz-PlayAI"),
        "input": text,
        "response_format": os.getenv("GROQ_TTS_RESPONSE_FORMAT", "wav"),
    }
    request = urllib.request.Request(
        "https://api.groq.com/openai/v1/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            # Without an explicit UA, Cloudflare in front of api.groq.com rejects
            # urllib's default agent with 403 (code 1010) - which looked like an
            # auth/terms failure and silently forced the robotic pyttsx3 voice.
            "User-Agent": "Nexi-Access/1.0",
        },
        method="POST",
    )
    timeout = float(os.getenv("GROQ_TTS_TIMEOUT_SECONDS", "10"))
    max_retries = max(0, int(os.getenv("GROQ_TTS_MAX_RETRIES", "3")))
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                _soft_disabled_until = 0.0
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < max_retries:
                backoff = 2 ** attempt
                print(f"[TTS] rate_limited retry_in={backoff}s attempt={attempt + 1}/{max_retries}", flush=True)
                time.sleep(backoff)
                continue
            if exc.code == 403:
                _soft_disabled_until = time.time() + _soft_disable_cooldown_secs()
            raise RuntimeError(f"groq_http_{exc.code}") from exc


def speak_text(text: str) -> GroqTTSResult:
    print("[TTS] provider=groq", flush=True)
    print("[TTS] speak_start", flush=True)
    suffix = "." + os.getenv("GROQ_TTS_RESPONSE_FORMAT", "wav").lstrip(".")
    path = ""
    try:
        audio = synthesize_speech(text)
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(audio)
            path = tmp.name
        simple_result = _play_with_simpleaudio(path)
        if simple_result is not None:
            if simple_result.interrupted or not simple_result.ok:
                return simple_result
        else:
            from playsound import playsound
            playsound(path)
        print("[TTS] speak_done", flush=True)
        print("[TTS] fallback_used=false", flush=True)
        return GroqTTSResult(ok=True)
    except Exception as exc:
        safe_reason = str(exc)[:80] if str(exc) else type(exc).__name__
        print(f"[TTS] groq_failed reason={safe_reason}", flush=True)
        return GroqTTSResult(ok=False, error=safe_reason, fallback_used=True)
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass
        stop()
