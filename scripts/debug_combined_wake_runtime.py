from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _new_counts() -> dict:
    return {"hotword": 0, "double_clap": 0, "missed": 0, "false_wake": 0, "events": 0}


def _run_phase(stream, pipeline, phase: str, duration_seconds: float, expected_source: str | None, expected_attempts: int = 0) -> dict:
    from engine.audio_wake_pipeline import FRAME_SAMPLES

    print(f"\n[COMBINED] phase={phase} duration_seconds={duration_seconds}")
    start = time.time()
    counts = _new_counts()
    seen_expected = 0
    while time.time() - start < duration_seconds:
        data, _overflow = stream.read(FRAME_SAMPLES)
        result = pipeline.process_frame(bytes(data))
        if result.get("wake"):
            source = result.get("source") or "unknown"
            counts["events"] += 1
            if source in counts:
                counts[source] += 1
            print(f"[COMBINED] wake source={source} reason={result.get('reason')} score={result.get('score', 0):.4f}")
            if expected_source and source == expected_source:
                seen_expected += 1
            if expected_source is None or source != expected_source:
                counts["false_wake"] += 1
    if expected_attempts:
        counts["missed"] = max(0, expected_attempts - seen_expected)
    return counts


def main() -> int:
    print("Jarvis combined hotword + double clap wake runtime debug")
    print("Local-only wake detection. This script does not call ASR, TTS, Groq, Gemini, or command_bus.")
    try:
        import sounddevice as sd
    except Exception as exc:
        print(f"[COMBINED] missing_audio_dependency reason={type(exc).__name__}")
        return 1

    from engine.audio_wake_pipeline import AudioWakePipeline, FRAME_SAMPLES, OpenWakeWordScorer, OWW_MODEL_PATH, OWW_PRETRAINED, SAMPLE_RATE

    try:
        scorer = OpenWakeWordScorer(model_path=OWW_MODEL_PATH, pretrained=OWW_PRETRAINED)
    except Exception as exc:
        print(f"[COMBINED] hotword_scorer_failed reason={type(exc).__name__}")
        return 1

    pipeline = AudioWakePipeline(wake_scorer=scorer, enable_clap=True)
    phases = []
    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, blocksize=FRAME_SAMPLES, dtype="int16") as stream:
            input("Press Enter, then say Hey Jarvis 5 times over the next 25 seconds...")
            phases.append(("hotword", _run_phase(stream, pipeline, "hotword", 25.0, "hotword", 5)))
            input("Press Enter, then double clap 5 times over the next 25 seconds...")
            phases.append(("double_clap", _run_phase(stream, pipeline, "double_clap", 25.0, "double_clap", 5)))
            input("Press Enter, then stay silent for 30 seconds...")
            phases.append(("silence", _run_phase(stream, pipeline, "silence", 30.0, None, 0)))
            input("Press Enter, then single clap 5 times over the next 25 seconds...")
            phases.append(("single_clap", _run_phase(stream, pipeline, "single_clap", 25.0, None, 0)))
    except KeyboardInterrupt:
        print("[COMBINED] stopped_by_user")
        return 2
    except Exception as exc:
        print(f"[COMBINED] failed reason={type(exc).__name__}")
        return 1

    print("\nConfusion matrix")
    verdict = 0
    for name, counts in phases:
        if name == "hotword":
            print(f"source_test=hotword detected_hotword={counts['hotword']} detected_clap={counts['double_clap']} missed={counts['missed']}")
            if counts["hotword"] < 4 or counts["double_clap"]:
                verdict = 2
        elif name == "double_clap":
            print(f"source_test=double_clap detected_clap={counts['double_clap']} detected_hotword={counts['hotword']} missed={counts['missed']}")
            if counts["double_clap"] < 4 or counts["hotword"]:
                verdict = 2
        elif name == "single_clap":
            print(f"source_test=single_clap false_wake={counts['false_wake']}")
            if counts["false_wake"]:
                verdict = 2
        elif name == "silence":
            print(f"source_test=silence false_wake={counts['false_wake']}")
            if counts["false_wake"]:
                verdict = 2
    print("PASS" if verdict == 0 else "PARTIAL")
    return verdict


if __name__ == "__main__":
    raise SystemExit(main())
