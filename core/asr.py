"""Automatic Speech Recognition — Groq Whisper."""

import io
import os
import wave
import time
import struct
from core.config import cfg


def _load_asr_prompt() -> str:
    try:
        from pathlib import Path
        p = Path(__file__).resolve().parent.parent / "prompts" / "asr_prompt.txt"
        if p.exists():
            return p.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return "Transcribe the following audio accurately."


def pcm_float32_to_wav_bytes(audio, sample_rate: int = 16000) -> bytes:
    """Convert audio (numpy array, list, or raw PCM16 bytes) to WAV bytes."""
    try:
        import numpy as np
        if isinstance(audio, np.ndarray):
            if audio.dtype == np.float32 or audio.dtype == np.float64:
                audio = (audio * 32767).clip(-32768, 32767).astype(np.int16)
            pcm = audio.tobytes()
        elif isinstance(audio, (list, tuple)):
            arr = np.array(audio, dtype=np.float32)
            arr = (arr * 32767).clip(-32768, 32767).astype(np.int16)
            pcm = arr.tobytes()
        elif isinstance(audio, (bytes, bytearray)):
            pcm = bytes(audio)
        else:
            return b""
    except ImportError:
        if isinstance(audio, (bytes, bytearray)):
            pcm = bytes(audio)
        else:
            return b""

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def wav_duration_ms(wav_bytes: bytes) -> int:
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            frames = wf.getnframes()
            rate = wf.getframerate()
            return int(frames / rate * 1000) if rate else 0
    except Exception:
        return 0


def transcribe(audio_wav_bytes: bytes, filename: str = "audio.wav") -> str:
    """Transcribe WAV audio via Groq Whisper. Returns text or empty string."""
    api_key = cfg.groq_api_key
    if not api_key:
        print("[ASR] no_api_key", flush=True)
        return ""

    try:
        import requests
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        files = {"file": (filename, audio_wav_bytes, "audio/wav")}
        data = {
            "model": cfg.groq_whisper_model,
            "language": cfg.groq_asr_language,
            "temperature": os.getenv("GROQ_ASR_TEMPERATURE", "0"),
            "prompt": _load_asr_prompt(),
        }
        headers = {"Authorization": f"Bearer {api_key}"}
        t0 = time.time()
        resp = requests.post(url, headers=headers, files=files, data=data,
                             timeout=cfg.groq_asr_timeout)
        elapsed = int((time.time() - t0) * 1000)
        resp.raise_for_status()
        text = resp.json().get("text", "").strip()
        print(f"[ASR] ok length={len(text)} ms={elapsed}", flush=True)
        return text
    except Exception as e:
        print(f"[ASR] failed reason={type(e).__name__}", flush=True)
        return ""
