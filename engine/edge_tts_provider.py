"""Edge TTS provider - Microsoft neural voices.

Free and keyless: no API key, no terms acceptance, and it sounds like a real
person rather than the robotic SAPI5 fallback. Used as the primary voice so
NEXI never has to fall back to pyttsx3 for normal speech.

Voice/rate/pitch are env-tunable (NEXI_EDGE_TTS_VOICE / _RATE / _PITCH) so the
persona can be changed without touching code.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import threading
from dataclasses import dataclass

DEFAULT_VOICE = "en-US-AriaNeural"


@dataclass
class EdgeTTSResult:
    ok: bool
    provider: str = "edge"
    fallback_used: bool = False
    error: str = ""
    interrupted: bool = False


def _enabled() -> bool:
    return (os.getenv("NEXI_EDGE_TTS_ENABLED", "true") or "").strip().lower() in {"1", "true", "yes", "on"}


def is_configured() -> bool:
    """Available when the package imports and it is not disabled. No key needed."""
    if not _enabled():
        return False
    try:
        from engine.demo_mode import DemoMode
        if DemoMode.use_local_tts():
            print("[TTS] provider=pyttsx3 fallback_used=true reason=demo_mode", flush=True)
            return False
    except Exception:
        pass
    try:
        import edge_tts  # noqa: F401
    except Exception:
        return False
    return True


def synthesize_speech(text: str) -> bytes:
    """Render `text` to mp3 bytes via Edge TTS."""
    import edge_tts

    voice = os.getenv("NEXI_EDGE_TTS_VOICE", DEFAULT_VOICE).strip() or DEFAULT_VOICE
    rate = os.getenv("NEXI_EDGE_TTS_RATE", "+0%").strip() or "+0%"
    pitch = os.getenv("NEXI_EDGE_TTS_PITCH", "+0Hz").strip() or "+0Hz"

    async def _run() -> bytes:
        speaker = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        audio = bytearray()
        async for chunk in speaker.stream():
            if chunk.get("type") == "audio":
                audio.extend(chunk.get("data") or b"")
        return bytes(audio)

    try:
        return asyncio.run(_run())
    except RuntimeError:
        # A loop is already running on this thread (the wake pipeline does this):
        # render in a dedicated thread with its own loop instead of failing.
        box: dict[str, object] = {}

        def _worker() -> None:
            loop = asyncio.new_event_loop()
            try:
                box["audio"] = loop.run_until_complete(_run())
            except Exception as exc:  # surfaced by speak_text below
                box["error"] = exc
            finally:
                loop.close()

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout=float(os.getenv("NEXI_EDGE_TTS_TIMEOUT_SECONDS", "20")))
        if isinstance(box.get("error"), BaseException):
            raise box["error"]  # type: ignore[misc]
        return bytes(box.get("audio") or b"")


def speak_text(text: str) -> EdgeTTSResult:
    print("[TTS] provider=edge", flush=True)
    print("[TTS] speak_start", flush=True)
    path = ""
    try:
        audio = synthesize_speech(text)
        if not audio:
            return EdgeTTSResult(ok=False, error="empty_audio", fallback_used=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            tmp.write(audio)
            path = tmp.name
        # Reuse the existing playback chain so interrupt/stop behaves identically
        # to the Groq path (simpleaudio when available, playsound otherwise).
        from engine import groq_tts
        played = groq_tts._play_with_simpleaudio(path)
        if played is not None:
            if played.interrupted or not played.ok:
                return EdgeTTSResult(ok=played.ok, provider="edge",
                                     error=played.error, interrupted=played.interrupted)
        else:
            from playsound import playsound
            playsound(path)
        print("[TTS] speak_done", flush=True)
        print("[TTS] fallback_used=false", flush=True)
        return EdgeTTSResult(ok=True)
    except Exception as exc:
        reason = str(exc)[:80] if str(exc) else type(exc).__name__
        print(f"[TTS] edge_failed reason={reason}", flush=True)
        return EdgeTTSResult(ok=False, error=reason, fallback_used=True)
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


def stop() -> bool:
    from engine import groq_tts
    return groq_tts.stop()
