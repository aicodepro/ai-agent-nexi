#!/usr/bin/env python3
"""Replay hotword WAV files for offline benchmark.

Usage:
    python scripts/debug_hotword_replay.py path/to/hey_nexi.wav
"""

import argparse
import os
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.hotword_engine_manager import HotwordEngineManager

SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * 80 / 1000)


def load_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wf:
        assert wf.getnchannels() == 1, "Mono required"
        assert wf.getframerate() == SAMPLE_RATE, f"Need {SAMPLE_RATE} Hz"
        data = wf.readframes(wf.getnframes())
    return np.frombuffer(data, dtype=np.int16).astype(np.float64)


def main():
    parser = argparse.ArgumentParser(description="Replay hotword WAV files")
    parser.add_argument("wav_paths", nargs="+", help="WAV file paths (16 kHz mono)")
    parser.add_argument("--threshold", type=float, default=0.35)
    args = parser.parse_args()

    os.environ.setdefault("OPENWAKEWORD_SCORE_THRESHOLD", str(args.threshold))
    os.environ.setdefault("NEXI_WAKE_DEBUG", "true")
    os.environ.setdefault("OPENWAKEWORD_DEBUG", "true")

    manager = HotwordEngineManager()

    for wav_path in args.wav_paths:
        audio = load_wav(wav_path)
        best = 0.0
        detections = 0
        total_frames = 0
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            frame = audio[offset:offset + FRAME_SAMPLES]
            result = manager.process_frame(frame.astype(np.int16).tobytes())
            total_frames += 1
            if result:
                best = max(best, result.get("confidence", 0))
                if result.get("detected"):
                    detections += 1
        print(f"[REPLAY] {os.path.basename(wav_path)} max_score={best:.4f} "
              f"detections={detections}/{total_frames} "
              f"{'PASS' if best >= args.threshold else 'FAIL'}")


if __name__ == "__main__":
    main()
