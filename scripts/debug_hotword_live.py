#!/usr/bin/env python3
"""Live hotword calibration test.

Sequence:
1. Record silence (30 s) — measure false positives
2. Say "Hey Nexi" 10 times — measure detection rate
3. Say "Nexi" 10 times — measure detection rate

Saves WAV clips for replay analysis.
"""

import argparse
import os
import sys
import time
import tempfile
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.hotword_engine_manager import HotwordEngineManager

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16
FRAME_MS = 80
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)


def record_audio(duration_sec: float, device: int | None = None) -> np.ndarray:
    import sounddevice as sd
    frames = int(SAMPLE_RATE * duration_sec)
    recording = sd.rec(frames, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, device=device)
    sd.wait()
    return recording.squeeze()


def main():
    parser = argparse.ArgumentParser(description="Live hotword calibration")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument("--threshold", type=float, default=0.25, help="Score threshold")
    parser.add_argument("--silence-duration", type=float, default=30.0, help="Silence recording seconds")
    args = parser.parse_args()

    os.environ.setdefault("NEXI_HOTWORD_ENABLED", "true")
    os.environ.setdefault("NEXI_CLAP_ENABLED", "false")
    os.environ.setdefault("NEXI_WAKE_DEBUG", "true")
    os.environ.setdefault("OPENWAKEWORD_DEBUG", "true")
    os.environ.setdefault("OPENWAKEWORD_SCORE_THRESHOLD", str(args.threshold))
    os.environ.setdefault("OPENWAKEWORD_CONSECUTIVE_HITS", "1")
    os.environ.setdefault("NEXI_HOTWORD_MIN_RMS", "0.003")
    os.environ.setdefault("NEXI_HOTWORD_RISING_EDGE_DELTA", "0.02")
    os.environ.setdefault("NEXI_HOTWORD_COOLDOWN_MS", "1500")
    os.environ.setdefault("NEXI_HOTWORD_PHRASES", "hey nexi,nexi")

    manager = HotwordEngineManager()
    openwakeword_available = "openwakeword" in [b.strip().lower() for b in (os.getenv("NEXI_HOTWORD_BACKEND_ORDER", "openwakeword,hotkey").split(","))]
    if not openwakeword_available:
        print("[HOTWORD] No openwakeword backend configured. Enable openwakeword in NEXI_HOTWORD_BACKEND_ORDER.")
        sys.exit(1)

    print("=" * 60)
    print("HOTWORD LIVE CALIBRATION")
    print("=" * 60)
    print(f"Threshold: {args.threshold}")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Frame: {FRAME_MS} ms ({FRAME_SAMPLES} samples)")
    print(f"Hotword status: {manager.get_status()}")
    print("audio seen: pending")
    print("scores seen: pending")
    print("wake emitted or blocked reason: pending")
    print()

    # --- Phase 1: Silence ---
    print("[PHASE 1] Recording silence for false-positives check")
    print(f"[PHASE 1] Duration: {args.silence_duration:.0f} seconds. Stay quiet.")
    for i in range(int(args.silence_duration / 5)):
        print(f"  ... {i*5}s")
        time.sleep(5)

    silence_audio = record_audio(args.silence_duration, args.device)
    scores_silence = []
    silence_detected_scores = []
    for offset in range(0, len(silence_audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        frame = silence_audio[offset:offset + FRAME_SAMPLES]
        result = manager.process_audio_chunk(frame.tobytes(), SAMPLE_RATE)
        scores_silence.append(result.score)
        if result.detected:
            silence_detected_scores.append(result.score)

    false_positives = len(silence_detected_scores)
    print(f"[RESULT] Silence false positives: {false_positives}")
    print(f"[RESULT] Max false positive score: {max(scores_silence) if scores_silence else 0:.4f}")
    print()

    # --- Phase 2: "Hey Nexi" x10 ---
    print("[PHASE 2] Say 'Hey Nexi' 10 times (one per prompt)")
    hey_nexi_scores = []
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, say 'Hey Nexi'...")
        time.sleep(0.5)
        audio = record_audio(2.0, args.device)
        best = 0.0
        detected = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            frame = audio[offset:offset + FRAME_SAMPLES]
            result = manager.process_audio_chunk(frame.tobytes(), SAMPLE_RATE)
            if result.score > best:
                best = result.score
            if result.detected:
                detected = True
        hey_nexi_scores.append(best)
        print(f"  max score = {best:.4f} {'DETECTED' if detected else ''}")
    print()

    # --- Phase 3: "Nexi" x10 ---
    print("[PHASE 3] Say 'Nexi' 10 times (one per prompt)")
    nexi_scores = []
    for i in range(10):
        input(f"  [{i+1}/10] Press Enter, pause 1s, say 'Nexi'...")
        time.sleep(0.5)
        audio = record_audio(2.0, args.device)
        best = 0.0
        detected = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            frame = audio[offset:offset + FRAME_SAMPLES]
            result = manager.process_audio_chunk(frame.tobytes(), SAMPLE_RATE)
            if result.score > best:
                best = result.score
            if result.detected:
                detected = True
        nexi_scores.append(best)
        print(f"  max score = {best:.4f} {'DETECTED' if detected else ''}")
    print()

    # --- Results ---
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"False positives (silence): {false_positives}")
    print()

    print("Hey Nexi:")
    for i, s in enumerate(hey_nexi_scores):
        print(f"  [{i+1}] {s:.4f} {'PASS' if s >= args.threshold else 'FAIL'}")
    hey_detected = sum(1 for s in hey_nexi_scores if s >= args.threshold)
    hey_max = max(hey_nexi_scores) if hey_nexi_scores else 0.0
    print(f"  Detection rate: {hey_detected}/10")
    print(f"  Max score: {hey_max:.4f}")
    print(f"  Max score across all attempts < {args.threshold}"
          if hey_max < args.threshold else "")

    print()
    print("Nexi:")
    for i, s in enumerate(nexi_scores):
        print(f"  [{i+1}] {s:.4f} {'PASS' if s >= args.threshold else 'FAIL'}")
    j_detected = sum(1 for s in nexi_scores if s >= args.threshold)
    j_max = max(nexi_scores) if nexi_scores else 0.0
    print(f"  Detection rate: {j_detected}/10")
    print(f"  Max score: {j_max:.4f}")

    print()
    valid_path = hey_max > 0.60 or j_max > 0.60
    if valid_path:
        print("HOTWORD_PATH_VALID=true")
    if len(hey_nexi_scores) >= 5 and hey_max < 0.05 and j_max < 0.05:
        print("CUSTOM_HOTWORD_REQUIRED=true")
    if hey_max < 0.05 and j_max < 0.05:
        print("VERDICT: Current openWakeWord model does not match this voice/phrase/audio path.")
        print("Need custom model or alternate local keyword backend.")
        print("Do NOT report PASS.")
        sys.exit(1)
    elif hey_detected >= 8:
        print("VERDICT: 'Hey Nexi' PASS (8/10 minimum)")
    else:
        print("VERDICT: 'Hey Nexi' FAIL (below 8/10)")

    if j_detected >= 8:
        print("VERDICT: 'Nexi' PASS (8/10 minimum)")
    else:
        print("VERDICT: 'Nexi' FAIL (below 8/10)")

    print()
    print(f"Recommended threshold: max(0.35, {min(hey_max, j_max) * 0.7:.2f})")


if __name__ == "__main__":
    main()
