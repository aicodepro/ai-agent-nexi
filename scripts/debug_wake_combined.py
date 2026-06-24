#!/usr/bin/env python3
"""Combined hotword + clap wake test.

Test sequence:
1. silence 30 seconds
2. say "Hey Jarvis" 5 times
3. say "Jarvis" 5 times
4. single clap 5 times
5. double clap 5 times
6. random speech without wake word 30 seconds
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from engine.hotword_engine_manager import HotwordEngineManager
from engine.clap_backend_manager import ClapBackendManager
from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult

SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * 80 / 1000)


def record_stream(duration_sec: float, device: int | None):
    import sounddevice as sd
    frames = int(SAMPLE_RATE * duration_sec / FRAME_SAMPLES)
    audio = []
    stream = sd.InputStream(device=device, channels=1, samplerate=SAMPLE_RATE, dtype=np.int16)
    with stream:
        for _ in range(frames):
            chunk, _ = stream.read(FRAME_SAMPLES)
            audio.append(chunk.copy())
    return np.concatenate(audio) if audio else np.array([], dtype=np.int16)


def process_chunk(chunk: np.ndarray,
                  hotword: HotwordEngineManager,
                  clap: ClapBackendManager,
                  orch: WakeOrchestrator) -> tuple[bool, str]:
    bytes_data = chunk.tobytes()
    hw_result = hotword.process_frame(bytes_data) if hotword else None
    clap_result = None
    if clap and clap.primary_ready:
        clap_result = clap.process_frame(chunk)

    for result, src_name in [(hw_result, "hotword"), (clap_result, "double_clap")]:
        if result:
            detected = result.get("detected", False) or result.get("wake", False)
            confidence = result.get("confidence", 0) or result.get("score", 0)
            ws = WakeSourceResult(
                source=src_name,
                detected=detected,
                confidence=float(confidence),
                timestamp=time.time(),
            )
            decision = orch.evaluate(ws)
            if decision.should_wake:
                orch.mark_listening_started()
                return True, decision.source
    return False, ""


def main():
    parser = argparse.ArgumentParser(description="Combined hotword + clap wake test")
    parser.add_argument("--device", type=int, default=None)
    args = parser.parse_args()

    os.environ.setdefault("JARVIS_HOTWORD_ENABLED", "true")
    os.environ.setdefault("JARVIS_CLAP_ENABLED", "true")
    os.environ.setdefault("JARVIS_WAKE_DEBUG", "true")
    os.environ.setdefault("JARVIS_CLAP_DEBUG", "true")
    os.environ.setdefault("OPENWAKEWORD_DEBUG", "true")

    hotword = HotwordEngineManager()
    clap = ClapBackendManager()
    clap_ready = clap.primary_ready
    if not clap_ready:
        status = clap.get_status()
        print(f"[WARN] Clap backend not ready: primary={status['primary']} ready={status['primary_ready']}")
        print("[WARN] Clap wake will be skipped. Install/train CLAP_NN model to enable.")
        print()

    orch = WakeOrchestrator({"debug": True})

    results = {
        "silence_false_wakes": 0,
        "hey_jarvis_detected": 0,
        "jarvis_detected": 0,
        "single_clap_false_wakes": 0,
        "double_clap_detected": 0,
        "duplicate_wakes": 0,
    }

    print("=" * 60)
    print("COMBINED WAKE TEST")
    print("=" * 60)
    print()

    # 1. Silence 30 s
    print("[1] Silence 30 seconds...")
    audio = record_stream(30.0, args.device)
    for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        chunk = audio[offset:offset + FRAME_SAMPLES]
        woke, src = process_chunk(chunk, hotword, clap, orch)
        if woke:
            results["silence_false_wakes"] += 1
            orch.mark_listening_finished()
    print(f"  silence_false_wakes={results['silence_false_wakes']}")
    print()

    # 2. "Hey Jarvis" x5
    print("[2] Say 'Hey Jarvis' 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, say 'Hey Jarvis'...")
        time.sleep(0.5)
        audio = record_stream(2.5, args.device)
        woke = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            w, src = process_chunk(chunk, hotword, clap, orch)
            if w:
                if woke:
                    results["duplicate_wakes"] += 1
                woke = True
                orch.mark_listening_finished()
        if woke:
            results["hey_jarvis_detected"] += 1
        print(f"  {'DETECTED' if woke else 'missed'}")
    print()

    # 3. "Jarvis" x5
    print("[3] Say 'Jarvis' 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, say 'Jarvis'...")
        time.sleep(0.5)
        audio = record_stream(2.5, args.device)
        woke = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            w, src = process_chunk(chunk, hotword, clap, orch)
            if w:
                if woke:
                    results["duplicate_wakes"] += 1
                woke = True
                orch.mark_listening_finished()
        if woke:
            results["jarvis_detected"] += 1
        print(f"  {'DETECTED' if woke else 'missed'}")
    print()

    # 4. Single clap x5
    print("[4] Single clap 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, single clap...")
        time.sleep(0.3)
        audio = record_stream(2.0, args.device)
        woke = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            w, src = process_chunk(chunk, hotword, clap, orch)
            if w:
                woke = True
                orch.mark_listening_finished()
        if woke:
            results["single_clap_false_wakes"] += 1
        print(f"  {'WAKE (bad)' if woke else 'no wake (good)'}")
    print()

    # 5. Double clap x5
    print("[5] Double clap 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, double clap...")
        time.sleep(0.3)
        audio = record_stream(2.0, args.device)
        woke = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            w, src = process_chunk(chunk, hotword, clap, orch)
            if w:
                if woke:
                    results["duplicate_wakes"] += 1
                woke = True
                orch.mark_listening_finished()
        if woke:
            results["double_clap_detected"] += 1
        print(f"  {'DETECTED' if woke else 'missed'}")
    print()

    # 6. Random speech 30 s
    print("[6] Random speech (no wake words) 30 seconds...")
    input("  Press Enter, then speak freely about any topic for 30 seconds...")
    audio = record_stream(30.0, args.device)
    for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        chunk = audio[offset:offset + FRAME_SAMPLES]
        woke, src = process_chunk(chunk, hotword, clap, orch)
        if woke:
            results["silence_false_wakes"] += 1  # count as false wake
            orch.mark_listening_finished()

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    for key, val in results.items():
        print(f"[RESULT] {key}={val}")

    print()
    print("PASS targets:")
    print("  Hey Jarvis:      4/5 minimum")
    print("  Jarvis:          4/5 minimum")
    print("  double clap:     4/5 minimum")
    print("  single clap:     0/5")
    print("  silence:         0")
    print("  duplicate wake:  0")

    passes = 0
    if results["hey_jarvis_detected"] >= 4:
        passes += 1
    if results["jarvis_detected"] >= 4:
        passes += 1
    if results["double_clap_detected"] >= 4:
        passes += 1
    if results["single_clap_false_wakes"] == 0:
        passes += 1
    if results["silence_false_wakes"] == 0:
        passes += 1
    if results["duplicate_wakes"] == 0:
        passes += 1

    if passes == 6:
        print("VERDICT: ALL PASS")
    elif passes >= 3:
        print(f"VERDICT: PARTIAL ({passes}/6 criteria met)")
        if results["hey_jarvis_detected"] < 4:
            print("  Blocker: hotword detection failed for 'Hey Jarvis'")
        if results["jarvis_detected"] < 4:
            print("  Blocker: hotword detection failed for 'Jarvis'")
        if results["double_clap_detected"] < 4:
            print("  Blocker: double clap detection failed")
    else:
        print(f"VERDICT: FAIL ({passes}/6 criteria met)")


if __name__ == "__main__":
    main()
