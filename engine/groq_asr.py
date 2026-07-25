# groq_asr.py
#
# Thin wrapper around the Groq Whisper transcription API.
#
# Pure I/O module. Never logs the API key. Returns "" on any failure
# so the caller never crashes mid-pipeline.

import io
import os
import re
import struct
import time
import wave
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()


GROQ_TRANSCRIPTION_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

# Connection-pooled session for connection reuse across calls.
_session = requests.Session()
_adapter = requests.adapters.HTTPAdapter(
    pool_connections=4,
    pool_maxsize=8,
    max_retries=0,
)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


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


def _resolve_fallback_models() -> list[str]:
    # NOTE: "whisper-1" is an OpenAI model name — Groq 404s on it. Groq only
    # serves whisper-large-v3 / whisper-large-v3-turbo.
    raw = (os.getenv("GROQ_ASR_FALLBACK_MODELS", "whisper-large-v3") or "").strip()
    if not raw:
        return []
    return [m.strip() for m in raw.split(",") if m.strip()]


def _resolve_timeout() -> float:
    try:
        return float(os.getenv("GROQ_TIMEOUT_SECONDS", "5"))
    except (TypeError, ValueError):
        return 5.0


def _resolve_language() -> str:
    lang = (os.getenv("GROQ_ASR_LANGUAGE", "en") or "en").strip() or "en"
    if lang.lower() == "auto":
        return ""
    return lang


def _resolve_temperature() -> str:
    return str(os.getenv("GROQ_ASR_TEMPERATURE", "0") or "0").strip() or "0"


def _resolve_max_attempts() -> int:
    try:
        return max(1, int(os.getenv("GROQ_ASR_MAX_ATTEMPTS", "1")))
    except (TypeError, ValueError):
        return 1


def _load_asr_prompt() -> str:
    """Optional Whisper bias prompt.

    ROOT-CAUSE NOTE: a non-empty prompt is ECHOED back verbatim by Whisper on
    silence/noise (this produced the "Transcribe the English speech." phantom
    transcripts — that sentence was in the old prompt file). So we send NO prompt
    by default for short command capture. Opt back in only via GROQ_ASR_PROMPT,
    and only when you have real VAD guaranteeing speech is present.
    """
    return (os.getenv("GROQ_ASR_PROMPT", "") or "").strip()


# Common phrases Whisper invents from silence/noise (echoing its language prior).
# Filtered only when confidence is low or audio is short/quiet — "thank you" and
# "hi" are real utterances at normal energy. Ref: whisper-hallucinations dataset.
_HALLUCINATION_PHRASES = {
    "thank you", "thank you for watching", "thanks for watching",
    "thank you for watching this video", "please subscribe",
    "please subscribe to my channel", "dont forget to subscribe",
    "subtitles by the amaraorg community", "transcribe the english speech",
    "you", "bye", "bye bye", "music", "okay", "ok", "so", "thank you very much",
    "thank you so much", "im sorry",
}


def _norm_text(text: str) -> str:
    return re.sub(r"[^\w\s]", "", (text or "").lower()).strip()


def _audio_rms(audio_wav_bytes: bytes) -> float:
    """RMS energy of a WAV blob in [0,1], or 0.0 on any parse failure."""
    try:
        with wave.open(io.BytesIO(audio_wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(frames)
        if sampwidth == 2:
            samples = struct.unpack(f"<{frames}h", raw)
            scale = 32768.0
        elif sampwidth == 1:
            samples = struct.unpack(f"<{frames}B", raw)
            scale = 255.0
        else:
            samples = struct.unpack(f"<{frames}i", raw)
            scale = 1.0
        if not samples:
            return 0.0
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        return rms / scale
    except Exception:
        return 0.0


def _is_hallucination(text: str, segments: list, rms: float, dur_ms: int) -> bool:
    """True if Whisper's output looks invented from silence rather than real speech.

    Layers: (1) verbose_json no-speech/low-confidence signal, (2) prompt echo,
    (3) known hallucination phrase gated behind low confidence/energy, (4) a stray
    single token on very short audio.
    """
    norm = _norm_text(text)
    if not norm:
        return True
    ns_max = None
    if isinstance(segments, list) and segments:
        segs = [s for s in segments if isinstance(s, dict)]
        if segs:
            ns = [float(s.get("no_speech_prob", 0.0) or 0.0) for s in segs]
            lp = [float(s.get("avg_logprob", 0.0) or 0.0) for s in segs]
            cr = [float(s.get("compression_ratio", 0.0) or 0.0) for s in segs]
            ns_max = max(ns)
            if ns_max > 0.6 and (sum(lp) / len(lp)) < -1.0:  # no-speech + low confidence
                return True
            if cr and max(cr) > 2.4:                          # repetition loop
                return True
    if "transcribe the english speech" in norm:               # legacy prompt echo
        return True
    if norm in _HALLUCINATION_PHRASES:
        low_conf = ns_max is not None and ns_max > 0.5
        low_energy = rms < 0.02 or dur_ms < 1500
        if low_conf or low_energy:
            return True
    if len(norm) <= 2 and dur_ms < 1500:                      # stray "you" / "."
        return True
    return False


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


def _audio_has_speech(
    audio_wav_bytes: bytes,
    min_duration_ms: int = 500,
    min_rms: float = 0.01,
) -> bool:
    """Check if WAV audio has sufficient duration and energy.

    Returns False for empty/silent audio so callers can skip the API call.
    """
    dur_ms = _wav_duration_ms(audio_wav_bytes)
    if dur_ms < min_duration_ms:
        _safe_log(f"audio_gate fail reason=duration_too_short duration_ms={dur_ms} min_ms={min_duration_ms}")
        return False
    try:
        with wave.open(io.BytesIO(audio_wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            sampwidth = wf.getsampwidth()
            raw = wf.readframes(frames)
        if sampwidth == 2:
            samples = struct.unpack(f"<{frames}h", raw)
        elif sampwidth == 1:
            samples = struct.unpack(f"<{frames}B", raw)
        else:
            samples = struct.unpack(f"<{frames}i", raw)
        sum_sq = sum(s * s for s in samples)
        rms = (sum_sq / max(1, len(samples))) ** 0.5
        if sampwidth == 2:
            rms /= 32768.0
        elif sampwidth == 1:
            rms /= 255.0
        if rms < min_rms:
            _safe_log(f"audio_gate fail reason=rms_too_low rms={rms:.5f} min_rms={min_rms}")
            return False
        _safe_log(f"audio_gate pass duration_ms={dur_ms} rms={rms:.5f}")
        return True
    except Exception as e:
        _safe_log(f"audio_gate fail reason={type(e).__name__}")
        return False


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
            clipped = np.clip(arr, -1.0, 1.0)
            int16 = (clipped * 32767.0).astype(np.int16)
        else:
            int16 = arr
        pcm_bytes = int16.tobytes()
    else:
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
        wf.setsampwidth(2)
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
    timeout, malformed body, empty audio), a single safe log line is emitted
    and "" is returned.
    """
    if not audio_wav_bytes:
        _safe_log("provider=groq failed reason=empty_audio")
        return _demo_transcript()

    # Audio quality gate: skip API call for empty/silent audio.
    min_dur = int(os.getenv("GROQ_ASR_MIN_DURATION_MS", "500"))
    min_rms = float(os.getenv("GROQ_ASR_MIN_RMS", "0.01"))
    if not _audio_has_speech(audio_wav_bytes, min_duration_ms=min_dur, min_rms=min_rms):
        _safe_log("provider=groq failed reason=audio_gate_rejected")
        return _demo_transcript()

    key = (api_key or _resolve_key()).strip()
    if not key:
        _safe_log("provider=groq failed reason=missing_key")
        return _demo_transcript()

    chosen_timeout = float(timeout_seconds) if timeout_seconds is not None else _resolve_timeout()
    language = _resolve_language()
    temperature = _resolve_temperature()
    max_attempts = _resolve_max_attempts()
    fallback_models = _resolve_fallback_models()
    primary_model = (model or _resolve_model()).strip()
    all_models = [primary_model] + [m for m in fallback_models if m != primary_model]

    _safe_log(f"provider=groq language={language or 'auto'} model={primary_model}")
    _safe_log(f"record_ms={_wav_duration_ms(audio_wav_bytes)}")
    _safe_log(f"max_attempts={max_attempts} fallback_models={all_models[1:] if len(all_models) > 1 else 'none'}")

    wav_file = (filename, audio_wav_bytes, "audio/wav")
    clip_dur_ms = _wav_duration_ms(audio_wav_bytes)
    clip_rms = _audio_rms(audio_wav_bytes)

    for model_idx, current_model in enumerate(all_models):
        for attempt in range(1, max_attempts + 1):
            _safe_log(f"provider=groq request_started attempt={attempt} model={current_model}")
            started = time.perf_counter()

            data = {
                "model": current_model,
                "response_format": "verbose_json",  # exposes no_speech_prob/avg_logprob for filtering
                "temperature": temperature,
            }
            asr_prompt = _load_asr_prompt()
            if asr_prompt:  # only send a prompt when explicitly opted in (echo risk on silence)
                data["prompt"] = asr_prompt
            if language:
                data["language"] = language

            try:
                resp = _session.post(
                    GROQ_TRANSCRIPTION_URL,
                    headers={"Authorization": f"Bearer {key}"},
                    files={"file": wav_file},
                    data=data,
                    timeout=chosen_timeout,
                )
            except requests.exceptions.Timeout:
                _safe_log(f"provider=groq failed reason=timeout attempt={attempt} model={current_model}")
                if attempt <= max_attempts - 1:
                    continue
                break
            except requests.exceptions.RequestException as e:
                _safe_log(f"provider=groq failed reason={type(e).__name__} attempt={attempt} model={current_model}")
                if attempt <= max_attempts - 1:
                    continue
                break
            except Exception as e:
                _safe_log(f"provider=groq failed reason={type(e).__name__} attempt={attempt} model={current_model}")
                if attempt <= max_attempts - 1:
                    continue
                break

            send_done = time.perf_counter()
            upload_ms = int((send_done - started) * 1000)
            _safe_log(f"upload_ms={upload_ms}")

            if resp.status_code != 200:
                _safe_log(f"provider=groq failed status={resp.status_code} attempt={attempt} model={current_model}")
                if attempt <= max_attempts - 1:
                    continue
                break

            try:
                payload = resp.json()
            except ValueError:
                _safe_log(f"provider=groq failed reason=invalid_json attempt={attempt} model={current_model}")
                if attempt <= max_attempts - 1:
                    continue
                break

            parse_done = time.perf_counter()
            transcribe_ms = int((parse_done - send_done) * 1000)
            _safe_log(f"transcribe_ms={transcribe_ms}")

            text = (payload.get("text") or "").strip() if isinstance(payload, dict) else ""
            segments = payload.get("segments") if isinstance(payload, dict) else None
            preview = text[:80].replace("\n", " ").replace('"', "'")
            _safe_log(f'text="{preview}"')

            if text and _is_hallucination(text, segments if isinstance(segments, list) else [], clip_rms, clip_dur_ms):
                _safe_log(f"rejected reason=hallucination rms={clip_rms:.5f} dur_ms={clip_dur_ms}")
                continue

            _safe_log(f"provider=groq success chars={len(text)} model={current_model}")

            if not text:
                _safe_log(f"provider=groq empty_response_full={str(payload)[:200]} attempt={attempt} model={current_model}")
                if attempt <= max_attempts - 1:
                    _safe_log(f"provider=groq retrying attempt={attempt + 1} model={current_model}")
                    continue
                break

            return text

        _safe_log(f"provider=groq exhausted_attempts model={current_model}")

    return ""


def _cleanup_session() -> None:
    _session.close()


def _demo() -> None:
    # the exact production bug: the old prompt sentence echoed on silence
    assert _is_hallucination("Transcribe the English speech.", [], rms=0.0142, dur_ms=6720) is True
    # classic Whisper silence-hallucinations at low energy
    assert _is_hallucination("Thank you.", [], rms=0.0104, dur_ms=3200) is True
    assert _is_hallucination("you", [], rms=0.008, dur_ms=800) is True
    # verbose_json no-speech + low-confidence signal
    assert _is_hallucination("okay so", [{"no_speech_prob": 0.9, "avg_logprob": -1.6}], rms=0.03, dur_ms=2000) is True
    # repetition-loop signal
    assert _is_hallucination("go go go go go", [{"no_speech_prob": 0.1, "avg_logprob": -0.2, "compression_ratio": 3.0}], rms=0.05, dur_ms=3000) is True
    # REAL speech must NOT be filtered
    assert _is_hallucination("open chrome", [{"no_speech_prob": 0.02, "avg_logprob": -0.3}], rms=0.05, dur_ms=1500) is False
    assert _is_hallucination("what time is it", [], rms=0.04, dur_ms=1800) is False
    # "thank you" at NORMAL energy/confidence is a real utterance -> keep it
    assert _is_hallucination("thank you", [{"no_speech_prob": 0.05, "avg_logprob": -0.3}], rms=0.05, dur_ms=2000) is False
    # prompt is empty by default now (no echo source)
    assert _load_asr_prompt() == ""
    print("groq_asr._demo OK")


if __name__ == "__main__":
    _demo()
