from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.debug_hotword_calibration import recommend_threshold, replay_wav


def _find_wavs(paths: list[str]) -> list[Path]:
    found: list[Path] = []
    for raw in paths:
        path = Path(raw)
        if path.is_dir():
            found.extend(sorted(path.rglob("*.wav")))
        elif path.suffix.lower() == ".wav":
            found.append(path)
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay WAV files through the local openWakeWord hotword model.")
    parser.add_argument("paths", nargs="+", help="WAV files or directories containing WAV files")
    args = parser.parse_args(argv)

    from engine.hotword_engine_manager import HotwordEngineManager

    manager = HotwordEngineManager({"debug": True})
    status = manager.get_status()
    sample_rate = int(status["sample_rate"])
    frame_samples = max(1, int(sample_rate * int(status["frame_ms"]) / 1000))
    wavs = _find_wavs(args.paths)
    if not wavs:
        print("[HOTWORD_REPLAY] no_wavs_found")
        return 1

    results = []
    for path in wavs:
        result = replay_wav(path, manager, frame_samples)
        results.append(result)
        print(
            f"file={path} detected={result['detected']} max_score={result['max_score']:.4f} "
            f"avg_score={result['avg_score']:.4f} detected_at_ms={result['detected_at_ms']}"
        )

    scores = [item["max_score"] for item in results]
    print("\nSummary")
    print(f"files={len(results)} detections={sum(1 for item in results if item['detected'])}/{len(results)}")
    print(f"max_score={max(scores):.4f} avg_max_score={statistics.mean(scores):.4f}")
    print(f"recommendation={recommend_threshold(scores)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
