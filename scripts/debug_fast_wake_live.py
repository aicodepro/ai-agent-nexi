#!/usr/bin/env python3
"""Fast wake live test — hotword + DSP clap, no dataset training required.

Test sequence:
1. silence 20 sec (expect 0 false wakes)
2. random speech without wake word 20 sec (expect 0 false clap wakes)
3. say "Hey Jarvis" normally 5 times (expect >= 4 wakes via hotword)
4. say "Jarvis" normally 5 times (expect >= 4 wakes via hotword)
5. single clap 5 times (expect 0 wakes)
6. double clap 5 times (expect >= 4 wakes)

Usage:
    python scripts/debug_fast_wake_live.py [--device N]
"""

import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_RATE = 16000
FRAME_SAMPLES = int(SAMPLE_RATE * 80 / 1000)


def _env(key: str, default: str) -> str:
    return (os.getenv(key, default) or default).strip()


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


def iter_live_frames(duration_sec: float, device: int | None):
    import sounddevice as sd
    frames = max(0, int(duration_sec * SAMPLE_RATE / FRAME_SAMPLES))
    stream = sd.InputStream(device=device, channels=1, samplerate=SAMPLE_RATE, dtype=np.int16)
    with stream:
        for _ in range(frames):
            chunk, _ = stream.read(FRAME_SAMPLES)
            yield chunk.squeeze().tobytes()


class WakeEvent:
    def __init__(self, phase: str, source: str, backend: str, confidence: float,
                 score: float, event_type: str, timestamp: float, metadata: dict = None):
        self.phase = phase
        self.source = source
        self.backend = backend
        self.confidence = confidence
        self.score = score
        self.event_type = event_type
        self.timestamp = timestamp
        self.metadata = metadata or {}


class WakeTracker:
    """Tracks per-attempt wake metadata and max scores."""

    def __init__(self):
        self.all_events: list[WakeEvent] = []
        self.reset_attempt()

    def reset_attempt(self):
        self.max_hotword_score = 0.0
        self.max_hotword_frame = 0
        self.detected_score = 0.0
        self.detected_source = ""
        self.detected_backend = ""
        self.detected_confidence = 0.0
        self.frame_count = 0
        self.woke = False
        self.wake_scores = []

    def record_hotword_score(self, score: float):
        self.frame_count += 1
        if score > self.max_hotword_score:
            self.max_hotword_score = score
            self.max_hotword_frame = self.frame_count

    def record_wake(self, source: str, backend: str, confidence: float, score: float):
        self.woke = True
        self.detected_source = source
        self.detected_backend = backend
        self.detected_confidence = confidence
        self.detected_score = score
        self.wake_scores.append({
            "source": source,
            "backend": backend,
            "confidence": confidence,
            "score": score,
            "frame": self.frame_count,
        })

    def add_event(self, phase: str, source: str, backend: str, confidence: float,
                  score: float, event_type: str = "wake_detected", metadata: dict = None):
        self.all_events.append(WakeEvent(phase, source, backend, confidence,
                                         score, event_type, time.time(), metadata))

    def print_hotword_summary(self, attempt_label: str):
        if self.woke:
            print(f"  [{attempt_label}] DETECTED source={self.detected_source} "
                  f"backend={self.detected_backend} "
                  f"detected_score={self.detected_score:.4f} "
                  f"max_score={self.max_hotword_score:.4f}")
        else:
            print(f"  [{attempt_label}] missed "
                  f"max_score={self.max_hotword_score:.4f}")

    def print_event_table(self):
        print("=" * 60)
        print("[EVENT_TABLE]")
        print("  phase,source,backend,score,confidence,wake,event_type")
        for ev in self.all_events:
            print(f"  {ev.phase},{ev.source},{ev.backend},{ev.score:.4f},"
                  f"{ev.confidence:.4f},{'1' if ev.event_type == 'wake_detected' and ev.score > 0 else '0'},"
                  f"{ev.event_type}")


def main():
    parser = argparse.ArgumentParser(description="Fast wake live test (no training required)")
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--hotword-threshold", type=float, default=0.25,
                        help="openWakeWord score threshold (default 0.25)")
    parser.add_argument("--clap-rms", type=float, default=0.030,
                        help="DSP clap RMS threshold (default 0.030)")
    parser.add_argument("--clap-peak", type=float, default=0.10,
                        help="DSP clap peak threshold (default 0.10)")
    parser.add_argument("--clap-peak-ratio", type=float, default=4.0,
                        help="DSP clap peak-to-average ratio (default 4.0)")
    parser.add_argument("--clap-hf-ratio", type=float, default=0.30,
                        help="DSP clap high-freq ratio (default 0.30)")
    parser.add_argument("--passive-timeout-minutes", type=float, default=0.0,
                        help="Run non-interactive passive false-wake check for N minutes")
    args = parser.parse_args()

    os.environ["JARVIS_HOTWORD_ENABLED"] = "true"
    os.environ["JARVIS_CLAP_ENABLED"] = "true"
    os.environ["JARVIS_CLAP_BACKEND_ORDER"] = "dsp_clap" if args.passive_timeout_minutes > 0 else "dsp_clap,clap_nn"
    os.environ["JARVIS_CLAP_PRIMARY"] = "dsp_clap"
    os.environ["JARVIS_HOTKEY_WAKE_ENABLED"] = "false"
    debug_value = "false" if args.passive_timeout_minutes > 0 else "true"
    os.environ["JARVIS_WAKE_DEBUG"] = debug_value
    os.environ["JARVIS_CLAP_DEBUG"] = debug_value
    os.environ["OPENWAKEWORD_DEBUG"] = debug_value
    os.environ["OPENWAKEWORD_SCORE_THRESHOLD"] = str(args.hotword_threshold)
    os.environ.setdefault("OPENWAKEWORD_CONSECUTIVE_HITS", "1")
    os.environ.setdefault("JARVIS_HOTWORD_MIN_RMS", "0.003")
    os.environ.setdefault("JARVIS_HOTWORD_RISING_EDGE_DELTA", "0.02")
    os.environ.setdefault("JARVIS_HOTWORD_COOLDOWN_MS", "1500")
    os.environ.setdefault("JARVIS_HOTWORD_PHRASES", "hey jarvis,jarvis")
    os.environ["JARVIS_DSP_CLAP_RMS_THRESHOLD"] = str(args.clap_rms)
    os.environ["JARVIS_DSP_CLAP_PEAK_THRESHOLD"] = str(args.clap_peak)
    os.environ["JARVIS_DSP_CLAP_PEAK_RATIO"] = str(args.clap_peak_ratio)
    os.environ["JARVIS_DSP_CLAP_HF_RATIO"] = str(args.clap_hf_ratio)
    os.environ.setdefault("JARVIS_DSP_CLAP_EVENT_COOLDOWN_MS", "80")
    os.environ.setdefault("JARVIS_DSP_CLAP_SPEECH_REJECT_MS", "250")
    os.environ.setdefault("JARVIS_CLAP_MIN_GAP_MS", "100")
    os.environ.setdefault("JARVIS_CLAP_MAX_GAP_MS", "3500")

    from engine.hotword_engine_manager import HotwordEngineManager
    from engine.clap_backend_manager import ClapBackendManager
    from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult

    hotword = HotwordEngineManager()
    clap = ClapBackendManager(cooldown_ms=1500)
    orch = WakeOrchestrator({"cooldown_ms": 1500, "debug": True})

    tracker = WakeTracker()

    clap_ready = clap.primary_ready
    if not clap_ready:
        print(f"[WARN] Clap backend not ready: primary={clap.primary_name} ready={clap.primary_ready}")
    else:
        print(f"[INFO] Clap backend ready: primary={clap.primary_name}")
    print(f"[INFO] Hotword backend: {hotword.get_status()['engine']} phrase={hotword.get_status()['phrase']}")
    print(f"[INFO] Hotword threshold={args.hotword_threshold}")
    print()

    results = {
        "silence_false_wakes": 0,
        "silence_false_hotword_wakes": 0,
        "silence_false_clap_wakes": 0,
        "silence_false_unknown_wakes": 0,
        "silence_false_wake_source": "none",
        "silence_false_wake_backend": "",
        "silence_false_wake_confidence": 0.0,
        "silence_false_wake_score": 0.0,
        "hey_jarvis_detected": 0,
        "jarvis_detected": 0,
        "single_clap_wakes": 0,
        "double_clap_detected": 0,
        "speech_false_clap_wakes": 0,
    }

    if args.passive_timeout_minutes > 0:
        duration_sec = max(1.0, args.passive_timeout_minutes * 60.0)
        print("=" * 60)
        print("PASSIVE WAKE CHECK")
        print("=" * 60)
        print(f"[PASSIVE] duration_sec={duration_sec:.0f}")
        print(f"[PASSIVE] backend={clap.primary_name} ready={clap.primary_ready}")
        false_wakes = 0
        for chunk_bytes in iter_live_frames(duration_sec, args.device):
            hw_r = hotword.process_audio_chunk(chunk_bytes, SAMPLE_RATE)
            tracker.record_hotword_score(hw_r.score)
            if hw_r.detected:
                dec = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=hw_r.score, timestamp=time.time()))
                if dec.should_wake:
                    false_wakes += 1
                    tracker.add_event("passive", "hotword", "openwakeword", hw_r.score, hw_r.score, "false_wake")
                    print(f"[PASSIVE_WAKE] source=hotword score={hw_r.score:.4f} reason={hw_r.reason}")
                    orch.mark_listening_finished()
            if clap_ready:
                clap_r = clap.process_audio_chunk(chunk_bytes)
                if clap_r.get("wake"):
                    false_wakes += 1
                    tracker.add_event("passive", "double_clap", clap_r.get("backend_used", "unknown"), clap_r.get("amplitude", 0.0), 0.0, "false_wake", {"reason": clap_r.get("reason", "")})
                    print(f"[PASSIVE_WAKE] source=double_clap backend={clap_r.get('backend_used', 'unknown')} reason={clap_r.get('reason', '')}")
                    orch.mark_listening_finished()
        tracker.print_event_table()
        print(f"[PASSIVE_RESULT] false_wakes={false_wakes}")
        print(f"[PASSIVE_RESULT] max_hotword_score={tracker.max_hotword_score:.4f}")
        if false_wakes == 0:
            print("VERDICT: PASS_PASSIVE_NO_FALSE_WAKES")
            return
        print("VERDICT: PASSIVE_FALSE_WAKE_FOUND")
        return

    print("=" * 60)
    print("FAST WAKE LIVE TEST (no training required)")
    print("=" * 60)
    print()

    # Phase 1: Silence 20 seconds
    print("[1] Silence 20 seconds...")
    time.sleep(1)
    audio = record_stream(20.0, args.device)
    for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        chunk = audio[offset:offset + FRAME_SAMPLES]
        chunk_bytes = chunk.tobytes()

        hw_r = hotword.process_audio_chunk(chunk_bytes, SAMPLE_RATE)
        if hw_r.detected:
            dec = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=hw_r.score, timestamp=time.time()))
            if dec.should_wake:
                results["silence_false_wakes"] += 1
                results["silence_false_hotword_wakes"] += 1
                results["silence_false_wake_source"] = "hotword"
                results["silence_false_wake_backend"] = "openwakeword"
                results["silence_false_wake_confidence"] = hw_r.score
                results["silence_false_wake_score"] = hw_r.score
                tracker.add_event("silence", "hotword", "openwakeword",
                                  hw_r.score, hw_r.score, "wake_detected",
                                  {"threshold": args.hotword_threshold})
                print(f"[SILENCE_WAKE] source=hotword backend=openwakeword "
                      f"confidence={hw_r.score:.4f} score={hw_r.score:.4f} "
                      f"event_type=wake_detected phase=silence")
                orch.mark_listening_finished()

        if clap_ready:
            clap_r = clap.process_audio_chunk(chunk_bytes)
            if clap_r.get("wake"):
                results["silence_false_wakes"] += 1
                results["silence_false_clap_wakes"] += 1
                results["silence_false_wake_source"] = "double_clap"
                backend = clap_r.get("backend_used", "unknown")
                results["silence_false_wake_backend"] = backend
                amp = clap_r.get("amplitude", 0.0)
                results["silence_false_wake_confidence"] = amp
                results["silence_false_wake_score"] = 0.0
                tracker.add_event("silence", "double_clap", backend,
                                  amp, 0.0, "wake_detected")
                print(f"[SILENCE_WAKE] source=double_clap backend={backend} "
                      f"confidence={amp:.4f} score=0.0 "
                      f"event_type=wake_detected phase=silence")
                orch.mark_listening_finished()

    print(f"  silence_false_wakes={results['silence_false_wakes']} (target: 0)")
    if results["silence_false_wakes"] > 0:
        print(f"  false_wake_source={results['silence_false_wake_source']}")
        print(f"  false_wake_backend={results['silence_false_wake_backend']}")
        print(f"  - hotword_wakes={results['silence_false_hotword_wakes']}")
        print(f"  - clap_wakes={results['silence_false_clap_wakes']}")
        print(f"  - unknown_wakes={results['silence_false_unknown_wakes']}")
    print()

    # Phase 2: "Hey Jarvis" x5
    print("[2] Say 'Hey Jarvis' 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, say 'Hey Jarvis'...")
        time.sleep(0.5)
        audio = record_stream(3.0, args.device)
        tracker.reset_attempt()
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            chunk_bytes = chunk.tobytes()
            hw_r = hotword.process_audio_chunk(chunk_bytes, SAMPLE_RATE)
            tracker.record_hotword_score(hw_r.score)
            if hw_r.detected:
                dec = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=hw_r.score, timestamp=time.time()))
                if dec.should_wake:
                    tracker.record_wake("hotword", "openwakeword", hw_r.score, hw_r.score)
                    orch.mark_listening_finished()
        if tracker.woke:
            results["hey_jarvis_detected"] += 1
        tracker.print_hotword_summary("Hey Jarvis")
    print()

    # Phase 3: "Jarvis" x5
    print("[3] Say 'Jarvis' 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, say 'Jarvis'...")
        time.sleep(0.5)
        audio = record_stream(3.0, args.device)
        tracker.reset_attempt()
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            chunk_bytes = chunk.tobytes()
            hw_r = hotword.process_audio_chunk(chunk_bytes, SAMPLE_RATE)
            tracker.record_hotword_score(hw_r.score)
            if hw_r.detected:
                dec = orch.evaluate(WakeSourceResult(source="hotword", detected=True, confidence=hw_r.score, timestamp=time.time()))
                if dec.should_wake:
                    tracker.record_wake("hotword", "openwakeword", hw_r.score, hw_r.score)
                    orch.mark_listening_finished()
        if tracker.woke:
            results["jarvis_detected"] += 1
        tracker.print_hotword_summary("Jarvis")
    print()

    # Phase 4: Single clap x5
    print("[4] Single clap 5 times (press Enter between each)")
    print("    (expect 0 wake events)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, single clap...")
        time.sleep(0.3)
        audio = record_stream(2.0, args.device)
        woke = False
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            chunk_bytes = chunk.tobytes()
            if clap_ready:
                clap_r = clap.process_audio_chunk(chunk_bytes)
                if clap_r.get("wake"):
                    woke = True
                    tracker.add_event("single_clap", "double_clap",
                                      clap_r.get("backend_used", "unknown"),
                                      clap_r.get("amplitude", 0.0), 0.0, "false_wake")
                    orch.mark_listening_finished()
        if woke:
            results["single_clap_wakes"] += 1
            print(f"    -> WAKE (bad - single clap should not wake)")
        else:
            print(f"    -> no wake (good)")
    print()

    # Phase 5: Double clap x5
    print("[5] Double clap 5 times (press Enter between each)")
    for i in range(5):
        input(f"  [{i+1}/5] Press Enter, pause 1s, double clap...")
        time.sleep(0.3)
        audio = record_stream(2.0, args.device)
        woke = False
        last_source = ""
        for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
            chunk = audio[offset:offset + FRAME_SAMPLES]
            chunk_bytes = chunk.tobytes()
            if clap_ready:
                clap_r = clap.process_audio_chunk(chunk_bytes)
                if clap_r.get("wake"):
                    woke = True
                    last_source = clap_r.get("source", "unknown")
                    tracker.add_event("double_clap", "double_clap",
                                      clap_r.get("backend_used", "unknown"),
                                      clap_r.get("amplitude", 0.0), 0.0, "wake_detected")
                    orch.mark_listening_finished()
        if woke:
            results["double_clap_detected"] += 1
            print(f"    -> DETECTED source={last_source}")
        else:
            print(f"    -> missed (check DSP thresholds)")
    print()

    # Phase 6: Random speech 20 sec (no wake words)
    print("[6] Random speech (no wake words) 20 seconds...")
    input("  Press Enter, then speak freely about any topic for 20 seconds...")
    audio = record_stream(20.0, args.device)
    for offset in range(0, len(audio) - FRAME_SAMPLES + 1, FRAME_SAMPLES):
        chunk = audio[offset:offset + FRAME_SAMPLES]
        chunk_bytes = chunk.tobytes()

        hw_r = hotword.process_audio_chunk(chunk_bytes, SAMPLE_RATE)
        if hw_r.detected:
            results["speech_false_clap_wakes"] += 1
            tracker.add_event("speech", "hotword", "openwakeword",
                              hw_r.score, hw_r.score, "false_wake")
            print(f"[SPEECH_FALSE_WAKE] source=hotword score={hw_r.score:.4f}")
            orch.mark_listening_finished()

        if clap_ready:
            clap_r = clap.process_audio_chunk(chunk_bytes)
            if clap_r.get("wake"):
                results["speech_false_clap_wakes"] += 1
                tracker.add_event("speech", "double_clap",
                                  clap_r.get("backend_used", "unknown"),
                                  clap_r.get("amplitude", 0.0), 0.0, "false_wake")
                print(f"[SPEECH_FALSE_WAKE] source=double_clap "
                      f"backend={clap_r.get('backend_used', 'unknown')}")
                orch.mark_listening_finished()

    print(f"  speech_false_clap_wakes={results['speech_false_clap_wakes']} (target: 0)")
    print()

    # Event table
    tracker.print_event_table()
    print()

    # Results summary
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    for key, val in results.items():
        if val != "" and val != 0.0:
            print(f"[RESULT] {key}={val}")
    print()

    targets = {
        "Hey Jarvis >= 4/5": results["hey_jarvis_detected"] >= 4,
        "Jarvis >= 4/5": results["jarvis_detected"] >= 4,
        "Double clap >= 4/5": results["double_clap_detected"] >= 4,
        "Single clap == 0": results["single_clap_wakes"] == 0,
        "Silence == 0": results["silence_false_wakes"] == 0,
        "Speech false clap == 0": results["speech_false_clap_wakes"] == 0,
    }

    passes = sum(1 for v in targets.values() if v)
    for label, ok in targets.items():
        print(f"  {'PASS' if ok else 'FAIL'} {label}")

    # Check for unknown source
    if results["silence_false_unknown_wakes"] > 0:
        print()
        print("FAIL: silence false wake source unknown")

    print()
    if passes == len(targets):
        print("VERDICT: ALL PASS — live wake validation successful")
    elif passes >= 3:
        print(f"VERDICT: PARTIAL ({passes}/{len(targets)} criteria met)")
        for label, ok in targets.items():
            if not ok:
                print(f"  Blocker: {label}")
    else:
        print(f"VERDICT: FAIL ({passes}/{len(targets)} criteria met)")


if __name__ == "__main__":
    main()
