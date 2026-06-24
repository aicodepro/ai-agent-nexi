from __future__ import annotations

import statistics
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LOCAL_ONLY_NOTICE = "Local-only wake calibration: no Groq, Gemini, cloud ASR, or cloud TTS is used."
PHRASE_ATTEMPTS = {"hey nexi": 10, "nexi": 10}
SILENCE_SECONDS = 60
ATTEMPT_SECONDS = 2.2
OUTPUT_DIR = ROOT / "data" / "wake_calibration" / time.strftime("%Y%m%d-%H%M%S")


def _write_wav(path: Path, pcm16: bytes, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16)


def _read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1 or wf.getsampwidth() != 2:
            raise ValueError(f"expected mono PCM16 WAV: {path}")
        return wf.readframes(wf.getnframes()), int(wf.getframerate())


def _record_wav(path: Path, seconds: float, sample_rate: int) -> None:
    import numpy as np
    import sounddevice as sd

    audio = sd.rec(int(seconds * sample_rate), samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    pcm16 = (audio[:, 0] * 32767.0).clip(-32768, 32767).astype(np.int16).tobytes()
    _write_wav(path, pcm16, sample_rate)


def replay_wav(path: Path, manager, frame_samples: int) -> dict:
    pcm16, sample_rate = _read_wav(path)
    scores: list[float] = []
    detected_at_ms = None
    start = time.perf_counter()
    manager.reset()
    frame_bytes = frame_samples * 2
    for offset in range(0, len(pcm16), frame_bytes):
        frame = pcm16[offset:offset + frame_bytes]
        if len(frame) < frame_bytes:
            frame = frame + (b"\x00" * (frame_bytes - len(frame)))
        result = manager.process_audio_chunk(frame, sample_rate)
        scores.append(result.score)
        if result.detected and detected_at_ms is None:
            detected_at_ms = int((offset / 2 / sample_rate) * 1000)
    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return {
        "path": str(path),
        "detected": detected_at_ms is not None,
        "detected_at_ms": detected_at_ms,
        "max_score": max(scores) if scores else 0.0,
        "avg_score": statistics.mean(scores) if scores else 0.0,
        "replay_ms": elapsed_ms,
    }


def recommend_threshold(scores: list[float]) -> dict:
    meaningful = [score for score in scores if score >= 0.05]
    if not meaningful:
        return {
            "recommended_threshold": None,
            "reason": "max score below 0.05; diagnose model/phrase mismatch, audio preprocessing, mic level, or custom model need",
        }
    max_score = max(meaningful)
    return {
        "recommended_threshold": max(0.15, min(0.75, round(max_score * 0.65, 2))),
        "reason": "score is meaningful; threshold recommendation is safe to consider",
    }


def main() -> int:
    print("Nexi hotword calibration")
    print(LOCAL_ONLY_NOTICE)
    try:
        from engine.hotword_engine_manager import HotwordEngineManager
    except Exception as exc:
        print(f"[HOTWORD_CAL] import_failed reason={type(exc).__name__}")
        return 1

    manager = HotwordEngineManager({"debug": True})
    status = manager.get_status()
    sample_rate = int(status["sample_rate"])
    frame_ms = int(status["frame_ms"])
    frame_samples = max(1, int(sample_rate * frame_ms / 1000))
    print(f"[HOTWORD_CAL] output_dir={OUTPUT_DIR}")
    print(f"[HOTWORD_CAL] sample_rate={sample_rate} frame_ms={frame_ms} frame_samples={frame_samples}")
    print(f"[HOTWORD_CAL] model={status['model_name']} phrase={status['phrase']} threshold={status['threshold']}")

    recordings: list[tuple[str, Path]] = []
    try:
        for phrase, attempts in PHRASE_ATTEMPTS.items():
            safe_phrase = phrase.replace(" ", "_")
            for index in range(1, attempts + 1):
                path = OUTPUT_DIR / safe_phrase / f"{safe_phrase}_{index:02d}.wav"
                input(f"Press Enter, then say '{phrase}' attempt {index}/{attempts}...")
                _record_wav(path, ATTEMPT_SECONDS, sample_rate)
                recordings.append((phrase, path))
                print(f"[HOTWORD_CAL] saved={path}")

        silence_path = OUTPUT_DIR / "silence" / "silence_60s.wav"
        input("Press Enter, then stay silent for 60 seconds...")
        _record_wav(silence_path, SILENCE_SECONDS, sample_rate)
        recordings.append(("silence", silence_path))
    except KeyboardInterrupt:
        print("[HOTWORD_CAL] stopped_by_user")
        return 2
    except Exception as exc:
        print(f"[HOTWORD_CAL] record_failed reason={type(exc).__name__}")
        return 1

    by_phrase: dict[str, list[dict]] = {}
    for phrase, path in recordings:
        try:
            result = replay_wav(path, manager, frame_samples)
        except Exception as exc:
            result = {"path": str(path), "detected": False, "max_score": 0.0, "avg_score": 0.0, "replay_ms": 0, "error": type(exc).__name__}
        by_phrase.setdefault(phrase, []).append(result)
        print(
            f"[HOTWORD_REPLAY] phrase={phrase} detected={result['detected']} "
            f"max={result['max_score']:.4f} avg={result['avg_score']:.4f} replay_ms={result['replay_ms']} path={path.name}"
        )

    all_wake_scores = [item["max_score"] for phrase, items in by_phrase.items() if phrase != "silence" for item in items]
    rec = recommend_threshold(all_wake_scores)
    print("\nCalibration report")
    exit_code = 0
    for phrase, items in by_phrase.items():
        detections = sum(1 for item in items if item.get("detected"))
        max_score = max((item.get("max_score", 0.0) for item in items), default=0.0)
        avg_score = statistics.mean([item.get("max_score", 0.0) for item in items]) if items else 0.0
        print(f"phrase={phrase} detections={detections}/{len(items)} max_score={max_score:.4f} avg_max_score={avg_score:.4f}")
        if phrase == "silence" and detections != 0:
            exit_code = 2
        if phrase != "silence" and detections < 8:
            exit_code = 2
    print(f"recommendation={rec}")
    if rec["recommended_threshold"] is not None:
        print(f"recommended_OPENWAKEWORD_SCORE_THRESHOLD={rec['recommended_threshold']}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
