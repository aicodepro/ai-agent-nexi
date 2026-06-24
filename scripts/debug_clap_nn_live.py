#!/usr/bin/env python3
"""Live CLAP_NN clap detection test.

Tests all clap backends with live microphone input.
Exits with clear FAIL if model file is missing.

Test sequence:
1. Check model exists (FAIL fast if missing)
2. Silence 10 s — measure false wake
3. "Hey Jarvis" x10 — must NOT trigger clap
4. "Jarvis" x10 — must NOT trigger clap
5. Single clap x10 — must NOT wake
6. Double clap x10 — must wake >= 8/10
7. Random speech 30 s — measure false wake
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.clap_nn_backend import ClapNNBackend
from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal

SAMPLE_RATE = 16000
FRAME_MS = 80
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)


def resolve_model_path() -> str:
    path = os.getenv("JARVIS_CLAP_NN_MODEL_PATH", "")
    if not path:
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(base, "external", "CLAP_NN_INSPECT", "CLAP_NN",
                             "ASSETS", "CLAP_DETECTS", "MODELS", "Clap_Detect_Model.pth")
    return os.path.normpath(path)


def check_model_exists(model_path: str) -> None:
    print("=" * 60)
    print("CLAP_NN LIVE TEST")
    print("=" * 60)
    print(f"Expected model path: {model_path}")
    if os.path.isfile(model_path):
        size_kb = os.path.getsize(model_path) / 1024
        print(f"Model found: {size_kb:.1f} KB")
    else:
        print(f"[FAIL] Model file NOT FOUND at: {model_path}")
        print()
        print("To fix:")
        print(f"  1. Collect training data:  python scripts/collect_clap_training_data.py")
        print(f"  2. Train model:            python scripts/train_clap_nn.py")
        print(f"  3. Validate model:         python scripts/validate_clap_nn_model.py")
        print(f"  4. Or copy a trained model to: {model_path}")
        print()
        sys.exit(1)


def record_stream(duration_sec: float, device: int | None) -> np.ndarray:
    import sounddevice as sd
    frames = int(SAMPLE_RATE * duration_sec)
    recording = sd.rec(frames, samplerate=SAMPLE_RATE, channels=1, dtype=np.int16, device=device)
    sd.wait()
    return recording.squeeze()


def process_clap_frames(audio: np.ndarray, backend: ClapNNBackend, threshold: float = 0.85) -> list:
    results = []
    for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        frame = audio[offset:offset + FRAME_SAMPLES].tobytes()
        result = backend.process_pcm16(frame, time.time())
        results.append(result)
    return results


def main():
    parser = argparse.ArgumentParser(description="Live CLAP_NN test")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument("--threshold", type=float, default=0.85, help="CLAP_NN confidence threshold")
    args = parser.parse_args()

    model_path = resolve_model_path()
    check_model_exists(model_path)

    backend = ClapNNBackend(model_path=model_path, threshold=args.threshold)
    status = backend.get_status()
    if not status["ready"]:
        print(f"[FAIL] CLAP_NN backend not ready: {status['last_error']}")
        sys.exit(1)
    print(f"[OK] CLAP_NN backend ready threshold={args.threshold}")
    print()

    results = {
        "silence_false_wakes": 0,
        "hey_jarvis_false_clap": 0,
        "jarvis_false_clap": 0,
        "single_clap_false_wake": 0,
        "double_clap_detected": 0,
    }

    # --- Phase 1: Silence ---
    print("[1] Silence 10 seconds...")
    input("  Press Enter, then stay quiet for 10 seconds...")
    audio = record_stream(10.0, args.device)
    clap_results = process_clap_frames(audio, backend)
    results["silence_false_wakes"] = sum(1 for r in clap_results if r.is_clap)
    print(f"  silence false wake = {results['silence_false_wakes']}")
    print()

    # --- Phase 2: "Hey Jarvis" x10 ---
    print("[2] Say 'Hey Jarvis' 10 times (must NOT trigger clap)")
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, say 'Hey Jarvis'...")
        time.sleep(0.5)
        audio = record_stream(2.0, args.device)
        clap_results = process_clap_frames(audio, backend)
        any_clap = any(r.is_clap for r in clap_results)
        if any_clap:
            results["hey_jarvis_false_clap"] += 1
        print(f"  {'FALSE CLAP (bad)' if any_clap else 'no clap (good)'}")
    print()

    # --- Phase 3: "Jarvis" x10 ---
    print("[3] Say 'Jarvis' 10 times (must NOT trigger clap)")
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, say 'Jarvis'...")
        time.sleep(0.5)
        audio = record_stream(2.0, args.device)
        clap_results = process_clap_frames(audio, backend)
        any_clap = any(r.is_clap for r in clap_results)
        if any_clap:
            results["jarvis_false_clap"] += 1
        print(f"  {'FALSE CLAP (bad)' if any_clap else 'no clap (good)'}")
    print()

    # --- Phase 4: Single clap x10 ---
    print("[4] Single clap 10 times (must NOT wake)")
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, single clap...")
        time.sleep(0.3)
        audio = record_stream(1.5, args.device)
        clap_results = process_clap_frames(audio, backend)
        any_clap = any(r.is_clap for r in clap_results)
        if any_clap:
            results["single_clap_false_wake"] += 1
        print(f"  {'WAKE (bad)' if any_clap else 'no wake (good)'}")
    print()

    # --- Phase 5: Double clap x10 ---
    print("[5] Double clap 10 times (must wake >= 8/10)")
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, double clap...")
        time.sleep(0.3)
        audio = record_stream(2.0, args.device)
        clap_results = process_clap_frames(audio, backend)
        any_clap = any(r.is_clap for r in clap_results)
        if any_clap:
            results["double_clap_detected"] += 1
        print(f"  {'DETECTED' if any_clap else 'missed'}")
    print()

    # --- Phase 6: Random speech 30 s ---
    print("[6] Random speech (no claps) 30 seconds...")
    input("  Press Enter, then speak freely about any topic for 30 seconds...")
    audio = record_stream(30.0, args.device)
    clap_results = process_clap_frames(audio, backend)
    speech_false = sum(1 for r in clap_results if r.is_clap)
    print(f"  speech false clap = {speech_false}")
    print()

    # --- Results ---
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  silence false wake:      {results['silence_false_wakes']}   (target: 0)")
    print(f"  'Hey Jarvis' false clap: {results['hey_jarvis_false_clap']}/10   (target: 0/10)")
    print(f"  'Jarvis' false clap:     {results['jarvis_false_clap']}/10   (target: 0/10)")
    print(f"  single clap false wake:  {results['single_clap_false_wake']}/10   (target: 0/10)")
    print(f"  double clap detected:    {results['double_clap_detected']}/10   (target: >=8/10)")
    print(f"  speech false clap:       {speech_false}   (target: 0)")
    print()

    passes = 0
    if results["silence_false_wakes"] == 0:
        passes += 1
    if results["hey_jarvis_false_clap"] == 0:
        passes += 1
    if results["jarvis_false_clap"] == 0:
        passes += 1
    if results["single_clap_false_wake"] == 0:
        passes += 1
    if results["double_clap_detected"] >= 8:
        passes += 1
    if speech_false == 0:
        passes += 1

    if passes == 6:
        print("VERDICT: ALL PASS")
        sys.exit(0)
    else:
        print(f"VERDICT: PARTIAL ({passes}/6 criteria met)")
        if results["double_clap_detected"] < 8:
            print("  Blocker: double clap detection rate < 8/10")
        if results["hey_jarvis_false_clap"] > 0:
            print("  Blocker: 'Hey Jarvis' triggers false clap")
        if results["jarvis_false_clap"] > 0:
            print("  Blocker: 'Jarvis' triggers false clap")
        if results["silence_false_wakes"] > 0:
            print("  Blocker: silence triggers false wake")
        if results["single_clap_false_wake"] > 0:
            print("  Blocker: single clap triggers wake (must be double)")
        sys.exit(2 if passes < 3 else 1)


if __name__ == "__main__":
    main()
