#!/usr/bin/env python3
"""Live double-clap calibration test.

Sequence:
1. Silence 30 seconds — measure false positives
2. 10 single claps — ensure 0/10 wake
3. 10 double claps — ensure >= 8/10 wake

Required result:
- single clap wakes: 0/10
- double clap wakes: at least 8/10
- silence false wakes: 0
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.clap_backend_manager import ClapBackendManager

SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * 80 / 1000)


def main():
    parser = argparse.ArgumentParser(description="Live double-clap calibration")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument("--gap-ms", type=int, default=180, help="Min gap ms")
    parser.add_argument("--window-ms", type=int, default=900, help="Max gap ms")
    args = parser.parse_args()

    os.environ.setdefault("JARVIS_CLAP_ENABLED", "true")
    os.environ.setdefault("JARVIS_HOTWORD_ENABLED", "false")
    os.environ.setdefault("JARVIS_WAKE_DEBUG", "true")
    os.environ.setdefault("JARVIS_CLAP_DEBUG", "true")
    os.environ.setdefault("JARVIS_CLAP_MIN_GAP_MS", str(args.gap_ms))
    os.environ.setdefault("JARVIS_CLAP_MAX_GAP_MS", str(args.window_ms))
    os.environ.setdefault("JARVIS_CLAP_COOLDOWN_MS", "1800")

    manager = ClapBackendManager()
    import sounddevice as sd

    def callback(frame: np.ndarray) -> dict | None:
        return manager.process_frame(frame)

    print("=" * 60)
    print("CLAP LIVE CALIBRATION")
    print("=" * 60)
    print(f"Min gap: {args.gap_ms} ms, Max window: {args.window_ms} ms")
    print()

    warnings = []
    print("Recommendation: test with 180-250 ms minimum gap and 700-900 ms window.")
    print()

    # --- Phase 1: Silence ---
    print("[PHASE 1] Recording silence 30 seconds")
    silence_wakes = 0
    frames_silence = int(SAMPLE_RATE * 30 / FRAME_SAMPLES)
    stream = sd.InputStream(device=args.device, channels=1, samplerate=SAMPLE_RATE, dtype=np.int16)
    with stream:
        for _ in range(frames_silence):
            chunk, _ = stream.read(FRAME_SAMPLES)
            result = callback(chunk)
            if result and result.get("wake", False):
                silence_wakes += 1
    print(f"[RESULT] Silence false wakes: {silence_wakes}")
    print()

    # --- Phase 2: Single claps x10 ---
    print("[PHASE 2] Single clap 10 times (no wake expected)")
    single_wakes = 0
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, single clap...")
        time.sleep(0.3)
        frames_single = int(SAMPLE_RATE * 2 / FRAME_SAMPLES)
        stream = sd.InputStream(device=args.device, channels=1, samplerate=SAMPLE_RATE, dtype=np.int16)
        with stream:
            woke = False
            for _ in range(frames_single):
                chunk, _ = stream.read(FRAME_SAMPLES)
                result = callback(chunk)
                if result and result.get("wake", False):
                    woke = True
                    single_wakes += 1
                    break
        print(f"  {'WAKE' if woke else 'no wake'}")
    print(f"[RESULT] Single clap wakes: {single_wakes}/10")
    if single_wakes > 0:
        warnings.append(f"Single clap caused {single_wakes} false wakes")
    print()

    # --- Phase 3: Double claps x10 ---
    print("[PHASE 3] Double clap 10 times (wake expected)")
    double_wakes = 0
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, double clap...")
        time.sleep(0.3)
        frames_double = int(SAMPLE_RATE * 2 / FRAME_SAMPLES)
        stream = sd.InputStream(device=args.device, channels=1, samplerate=SAMPLE_RATE, dtype=np.int16)
        with stream:
            woke = False
            for _ in range(frames_double):
                chunk, _ = stream.read(FRAME_SAMPLES)
                result = callback(chunk)
                if result and result.get("wake", False):
                    woke = True
                    double_wakes += 1
                    break
        print(f"  {'WAKE' if woke else 'no wake'}")
    print(f"[RESULT] Double clap wakes: {double_wakes}/10")
    print()

    # --- Summary ---
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Silence false wakes: {silence_wakes}")
    print(f"Single clap wakes:   {single_wakes}/10 (target: 0/10)")
    print(f"Double clap wakes:   {double_wakes}/10 (target: >= 8/10)")
    verdict = "PASS" if double_wakes >= 8 and single_wakes == 0 and silence_wakes == 0 else "FAIL"
    print(f"Verdict: {verdict}")
    if warnings:
        for w in warnings:
            print(f"  Warning: {w}")
    print()
    if verdict == "FAIL":
        print("Tuning suggestions:")
        if double_wakes < 8:
            print("  - Increase JARVIS_CLAP_MAX_GAP_MS (try 1000, 1100)")
            print("  - Decrease JARVIS_CLAP_MIN_GAP_MS (try 150, 120)")
            print("  - Check CLAP_MIN_RMS / CLAP_PEAK_THRESHOLD")
        if single_wakes > 0:
            print("  - Increase JARVIS_CLAP_MIN_GAP_MS (try 250, 300)")
            print("  - Check CLAP_MIN_RMS / CLAP_PEAK_THRESHOLD")


if __name__ == "__main__":
    main()
