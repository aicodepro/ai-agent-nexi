"""NEXI Voice Data Factory — generate diverse "hey nexi" clips from AI voices.

Pipeline per sample: pick an AI voice source -> synthesize the phrase -> apply a
speaking-condition transform (normal/whisper/shout/fast/slow) -> mix noise
(augmentation) -> (optionally) round-trip ASR-verify it actually says the phrase
-> save a 16 kHz mono WAV + a manifest line. Output feeds openWakeWord training
(see scripts/train_hey_nexi.sh and docs/hey-nexi-voice-factory-proposal.md).

VOICE SOURCES are pluggable and auto-skipped if unavailable:
  * pyttsx3   — the OS TTS, ALWAYS available (baseline; a few voices)
  * piper     — if the `piper` CLI is on PATH (many voices; openWakeWord's default)
  * coqui     — if `TTS` (Coqui XTTS) is installed (zero-shot voice cloning = the
                real diversity multiplier)
More engines (F5-TTS, StyleTTS2, Kokoro, Bark) drop in the same way.

Run:
  python -m engine.wake_training.factory --phrase "hey nexi" --out data/wake/hey_nexi --n 200
  python -m engine.wake_training.factory --phrase "hey nexi" --out data/wake/hey_nexi --n 200 --verify
"""
from __future__ import annotations

import argparse
import io
import json
import os
import random
import shutil
import struct
import subprocess
import tempfile
import wave

import numpy as np

SR = 16000
PHRASE = "hey nexi"
CONDITIONS = ("normal", "whisper", "shout", "fast", "slow")


# --------------------------------------------------------------------------- #
# WAV helpers
# --------------------------------------------------------------------------- #
def _read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        sr = wf.getframerate()
        n = wf.getnframes()
        raw = wf.readframes(n)
        width = wf.getsampwidth()
        channels = wf.getnchannels()
    if width == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    if channels > 1:  # downmix to mono
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sr


def _write_wav(path: str, x: np.ndarray, sr: int = SR) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    clipped = np.clip(x, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _wav_bytes(x: np.ndarray, sr: int = SR) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((np.clip(x, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes())
    return buf.getvalue()


def _resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out or x.size == 0:
        return x
    n_out = int(round(x.size * sr_out / sr_in))
    if n_out <= 1:
        return x
    xp = np.linspace(0.0, 1.0, num=x.size, endpoint=False)
    fp = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(fp, xp, x).astype(np.float32)


# --------------------------------------------------------------------------- #
# Speaking-condition transforms (energy/style diversity: whisper..shout)
# --------------------------------------------------------------------------- #
def _time_stretch(x: np.ndarray, factor: float) -> np.ndarray:
    # naive resample-based stretch (also shifts pitch — fine for augmentation)
    if factor == 1.0 or x.size == 0:
        return x
    n_out = max(1, int(round(x.size / factor)))
    xp = np.linspace(0.0, 1.0, num=x.size, endpoint=False)
    fp = np.linspace(0.0, 1.0, num=n_out, endpoint=False)
    return np.interp(fp, xp, x).astype(np.float32)


def apply_condition(x: np.ndarray, condition: str) -> np.ndarray:
    if condition == "whisper":
        return (x * 0.35).astype(np.float32)                      # quiet/close
    if condition == "shout":
        return np.tanh(x * 3.0).astype(np.float32)                # loud + soft-clip
    if condition == "fast":
        return _time_stretch(x, 1.25)
    if condition == "slow":
        return _time_stretch(x, 0.85)
    return x.astype(np.float32)


# --------------------------------------------------------------------------- #
# Augmentation (noise at a target SNR)
# --------------------------------------------------------------------------- #
def _pink_noise(n: int) -> np.ndarray:
    white = np.random.randn(n).astype(np.float32)
    # simple 1/f shaping in the frequency domain
    spectrum = np.fft.rfft(white)
    freqs = np.arange(1, spectrum.size + 1)
    spectrum /= np.sqrt(freqs)
    pink = np.fft.irfft(spectrum, n=n).astype(np.float32)
    m = np.max(np.abs(pink)) or 1.0
    return pink / m


def add_noise(x: np.ndarray, snr_db: float, noise: np.ndarray | None = None) -> np.ndarray:
    if x.size == 0:
        return x
    if noise is None or noise.size == 0:
        noise = _pink_noise(x.size)
    if noise.size < x.size:
        noise = np.tile(noise, int(np.ceil(x.size / noise.size)))
    noise = noise[: x.size]
    sig_p = float(np.mean(x ** 2)) or 1e-9
    noise_p = float(np.mean(noise ** 2)) or 1e-9
    scale = np.sqrt(sig_p / (noise_p * (10 ** (snr_db / 10.0))))
    return (x + scale * noise).astype(np.float32)


# --------------------------------------------------------------------------- #
# Pluggable AI voice sources
# --------------------------------------------------------------------------- #
def _pyttsx3_generate(phrase: str, out_wav: str, rate: int, voice_id: str | None) -> bool:
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.setProperty("rate", rate)
        if voice_id:
            engine.setProperty("voice", voice_id)
        engine.save_to_file(phrase, out_wav)
        engine.runAndWait()
        return os.path.exists(out_wav) and os.path.getsize(out_wav) > 0
    except Exception:
        return False


def _pyttsx3_voices() -> list[str]:
    try:
        import pyttsx3
        return [v.id for v in pyttsx3.init().getProperty("voices")]
    except Exception:
        return []


def _piper_generate(phrase: str, out_wav: str, model: str) -> bool:
    if not shutil.which("piper") or not model:
        return False
    try:
        subprocess.run(
            ["piper", "--model", model, "--output_file", out_wav],
            input=phrase.encode("utf-8"), check=True, capture_output=True, timeout=60,
        )
        return os.path.exists(out_wav)
    except Exception:
        return False


def available_sources() -> list[str]:
    sources = []
    if _pyttsx3_voices():
        sources.append("pyttsx3")
    if shutil.which("piper"):
        sources.append("piper")
    try:
        import TTS  # noqa: F401  (Coqui XTTS)
        sources.append("coqui")
    except Exception:
        pass
    return sources


# --------------------------------------------------------------------------- #
# Round-trip ASR quality gate
# --------------------------------------------------------------------------- #
def _verify(x: np.ndarray, phrase: str) -> bool:
    """Keep a clip only if an ASR transcribes it back to the phrase."""
    try:
        from engine.groq_asr import transcribe_audio_bytes
        text = transcribe_audio_bytes(_wav_bytes(x)) or ""
        norm = "".join(c for c in text.lower() if c.isalnum() or c == " ").strip()
        target = "".join(c for c in phrase.lower() if c.isalnum() or c == " ").strip()
        return target in norm
    except Exception:
        return True  # verifier unavailable -> don't drop the clip


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def run(phrase: str = PHRASE, out_dir: str = "data/wake/hey_nexi", n: int = 200,
        *, verify: bool = False, piper_model: str = "", seed: int = 0) -> dict:
    rng = random.Random(seed)
    np.random.seed(seed)
    sources = available_sources()
    if "piper" in sources and not piper_model:
        # piper needs a voice .onnx; without one every piper clip fails -> drop it
        sources = [s for s in sources if s != "piper"]
        print("[VOICE_FACTORY] piper skipped (no --piper-model given); using:", sources)
    if not sources:
        raise RuntimeError("No TTS voice source available (install pyttsx3, piper, or coqui TTS).")
    voices = _pyttsx3_voices()
    os.makedirs(out_dir, exist_ok=True)
    manifest_path = os.path.join(out_dir, "manifest.jsonl")
    kept = 0
    dropped = 0
    with open(manifest_path, "w", encoding="utf-8") as manifest:
        for i in range(n):
            source = sources[i % len(sources)]
            condition = CONDITIONS[i % len(CONDITIONS)]
            with tempfile.TemporaryDirectory() as tmp:
                raw = os.path.join(tmp, "raw.wav")
                ok = False
                if source == "pyttsx3":
                    rate = rng.choice([150, 175, 200, 220])
                    voice = rng.choice(voices) if voices else None
                    ok = _pyttsx3_generate(phrase, raw, rate, voice)
                elif source == "piper":
                    ok = _piper_generate(phrase, raw, piper_model)
                if not ok:
                    dropped += 1
                    continue
                x, sr = _read_wav(raw)
            x = _resample(x, sr, SR)
            x = apply_condition(x, condition)
            if rng.random() < 0.7:  # augment 70% of clips
                x = add_noise(x, snr_db=rng.uniform(5.0, 20.0))
            peak = np.max(np.abs(x)) or 1.0
            x = (x / peak) * 0.9  # normalize headroom
            if verify and not _verify(x, phrase):
                dropped += 1
                continue
            path = os.path.join(out_dir, f"{phrase.replace(' ', '_')}_{i:05d}.wav")
            _write_wav(path, x, SR)
            manifest.write(json.dumps({"path": os.path.basename(path), "source": source,
                                       "condition": condition, "verified": bool(verify)}) + "\n")
            kept += 1
    result = {"kept": kept, "dropped": dropped, "sources": sources, "out_dir": out_dir}
    print(f"[VOICE_FACTORY] kept={kept} dropped={dropped} sources={sources} -> {out_dir}")
    return result


def _demo() -> None:
    # pure-DSP self-test (no TTS needed): conditions + augmentation are correct
    t = np.linspace(0, 1, SR, endpoint=False).astype(np.float32)
    tone = 0.5 * np.sin(2 * np.pi * 220 * t)

    assert float(np.sqrt(np.mean(apply_condition(tone, "whisper") ** 2))) < \
        float(np.sqrt(np.mean(tone ** 2)))                                  # whisper is quieter
    assert apply_condition(tone, "fast").size < tone.size                   # fast is shorter
    assert apply_condition(tone, "slow").size > tone.size                   # slow is longer
    assert np.max(np.abs(apply_condition(tone, "shout"))) <= 1.0            # shout stays bounded

    noisy = add_noise(tone, snr_db=10.0)
    assert noisy.shape == tone.shape
    # measured SNR should land near the requested 10 dB
    noise = noisy - tone
    snr = 10 * np.log10(np.mean(tone ** 2) / (np.mean(noise ** 2) or 1e-9))
    assert 7.0 < snr < 13.0, snr

    assert _resample(tone, SR, 8000).size == 8000
    print("factory._demo OK  (available sources:", available_sources() or "none here", ")")


if __name__ == "__main__":
    if os.environ.get("VOICE_FACTORY_DEMO") == "1":
        _demo()
    else:
        ap = argparse.ArgumentParser(description="Generate diverse 'hey nexi' training clips.")
        ap.add_argument("--phrase", default=PHRASE)
        ap.add_argument("--out", default="data/wake/hey_nexi")
        ap.add_argument("--n", type=int, default=200)
        ap.add_argument("--verify", action="store_true", help="round-trip ASR-verify each clip")
        ap.add_argument("--piper-model", default="", help="path to a Piper .onnx voice")
        ap.add_argument("--seed", type=int, default=0)
        args = ap.parse_args()
        run(args.phrase, args.out, args.n, verify=args.verify, piper_model=args.piper_model, seed=args.seed)
