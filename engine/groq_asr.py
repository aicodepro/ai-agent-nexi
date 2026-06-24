# groq_asr.py
#
# Thin wrapper around the Groq Whisper transcription API.
#
# Pure I/O module. Never logs the API key. Returns "" on any failure
# so the caller never crashes mid-pipeline.

import io
import os
import time
import wave
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def _safe_log(msg: str) -> None:
    line = f"[ASR] {msg}"
    try:
        from engine.debug_trace import line as trace_line
        trace_line(line)
    except Exception:
        print(line, flush=True)


def _resolve_key() -> str:
    return (os.getenv("GROQ_API_KEY", "") or "").strip()


def _resolve_model() -> str:
    return (
        os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo") or ""
    ).strip() or "whisper-large-v3-turbo"


def _resolve_timeout() -> float:
    try:
        return float(os.getenv("GROQ_TIMEOUT_SECONDS", "10"))
    except (TypeError, ValueError):
        return 10.0


def _resolve_language() -> str:
    return (os.getenv("GROQ_ASR_LANGUAGE", "en") or "en").strip() or "en"


def _resolve_temperature() -> str:
    return str(os.getenv("GROQ_ASR_TEMPERATURE", "0") or "0").strip() or "0"


def _load_asr_prompt() -> str:
    try:
        from engine.prompt_loader import load_prompt_file
        return load_prompt_file("nexi_asr_prompt.txt", "Transcribe English desktop assistant commands for Nexi. Return only the spoken words.")
    except Exception:
        return "Transcribe English desktop assistant commands for Nexi. Return only the spoken words."


def _demo_transcript() -> str:
    try:
        from engine.demo_mode import DemoMode
        if DemoMode.is_active():
            return (os.getenv("NEXI_DEMO_ASR_FALLBACK_TEXT", "hello") or "hello").strip()
    except Exception:
        pass
    return ""


def _wav_duration_ms(audio_wav_bytes: bytes) -> int:
    try:
        with wave.open(io.BytesIO(audio_wav_bytes), "rb") as wf:
            rate = max(1, int(wf.getframerate()))
            return int((wf.getnframes() / rate) * 1000)
    except Exception:
        return 0


def pcm_float32_to_wav_bytes(audio, sample_rate: int = 16000) -> bytes:
    """Convert a 1-D numpy float32 audio array in [-1, 1] to mono PCM16 WAV bytes.

    Accepts numpy arrays, plain Python lists, or a bytes object that is
    already valid 16-bit PCM (returned as a WAV-wrapped form).
    """
    try:
        import numpy as np
    except ImportError:
        np = None  # type: ignore

    # If caller already gave us raw PCM16 bytes, wrap them in WAV.
    if isinstance(audio, (bytes, bytearray)) and not isinstance(audio, memoryview):
        pcm_bytes = bytes(audio)
    elif np is not None and hasattr(audio, "dtype"):
        arr = audio
        if arr.dtype != np.int16:
            # clip + scale float32 [-1, 1] to int16
            clipped = np.clip(arr, -1.0, 1.0)
            int16 = (clipped * 32767.0).astype(np.int16)
        else:
            int16 = arr
        pcm_bytes = int16.tobytes()
    else:
        # list/iterable of floats
        try:
            import array
            int_samples = array.array("h")
            for s in audio:
                v = max(-1.0, min(1.0, float(s)))
                int_samples.append(int(v * 32767.0))
            pcm_bytes = int_samples.tobytes()
        except Exception:
            pcm_bytes = b""

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(int(sample_rate))
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def transcribe_audio_bytes(
    audio_wav_bytes: bytes,
    *,
    filename: str = "command.wav",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    timeout_seconds: Optional[float] = None,
) -> str:
    """POST a WAV blob to Groq Whisper. Returns the stripped transcript or "".

    The API key is never logged. On any failure (missing key, HTTP error,
    timeout, malformed body), a single safe log line is emitted and "" is
    returned.
    """
    if not audio_wav_bytes:
        _safe_log("provider=groq failed reason=empty_audio")
        return _demo_transcript()

    key = (api_key or _resolve_key()).strip()
    if not key:
        _safe_log("provider=groq failed reason=missing_key")
        return _demo_transcript()

    chosen_model = (model or _resolve_model()).strip()
    chosen_timeout = float(timeout_seconds) if timeout_seconds is not None else _resolve_timeout()

    headers = {"Authorization": f"Bearer {key}"}
    files = {"file": (filename, audio_wav_bytes, "audio/wav")}
    language = _resolve_language()
    temperature = _resolve_temperature()
    data = {
        "model": chosen_model,
        "response_format": "json",
        "language": language,
        "temperature": temperature,
        "prompt": _load_asr_prompt(),
    }

    _safe_log(f"provider=groq language={language}")
    _safe_log(f"record_ms={_wav_duration_ms(audio_wav_bytes)}")

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        _safe_log(f"provider=groq request_started attempt={attempt}")
        started = time.perf_counter()
        try:
            resp = requests.post(
                GROQ_TRANSCRIPTION_URL,
                headers=headers,
                files=files,
                data=data,
                timeout=chosen_timeout,
            )
        except requests.exceptions.Timeout:
            _safe_log(f"provider=groq failed reason=timeout attempt={attempt}")
            if attempt < max_attempts:
                continue
            return _demo_transcript()
        except requests.exceptions.RequestException as e:
            _safe_log(f"provider=groq failed reason={type(e).__name__} attempt={attempt}")
            if attempt < max_attempts:
                continue
            return _demo_transcript()
        except Exception as e:
            _safe_log(f"provider=groq failed reason={type(e).__name__} attempt={attempt}")
            if attempt < max_attempts:
                continue
            return _demo_transcript()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        _safe_log(f"upload_ms={elapsed_ms}")
        _safe_log(f"transcribe_ms={elapsed_ms}")

        if resp.status_code != 200:
            _safe_log(f"provider=groq failed status={resp.status_code} attempt={attempt}")
            if attempt < max_attempts:
                continue
            return _demo_transcript()

        try:
            payload = resp.json()
        except ValueError:
            _safe_log(f"provider=groq failed reason=invalid_json attempt={attempt}")
            if attempt < max_attempts:
                continue
            return _demo_transcript()

        text = (payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        preview = text[:80].replace("\n", " ").replace('"', "'")
        _safe_log(f'text="{preview}"')
        _safe_log(f"provider=groq success chars={len(text)}")

        if not text:
            _safe_log(f"provider=groq empty_response_full={str(payload)[:200]} attempt={attempt}")
            if attempt < max_attempts:
                _safe_log(f"provider=groq retrying attempt={attempt + 1}")
                continue
            return _demo_transcript()

        return text
    return ""
    
