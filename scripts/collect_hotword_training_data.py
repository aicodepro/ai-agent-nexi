#!/usr/bin/env python3
"""Collect custom hotword training data from user's microphone.

Collects positives (Hey Nexi, Nexi) and negatives (speech, noise,
similar words, keyboard taps) for openWakeWord custom model training.

Output: 16 kHz mono WAV files under datasets/hotword/
"""

import argparse
import os
import sys
import time
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "hotword")

POSITIVE_DIRS = {
    "hey_nexi": os.path.join(BASE_DIR, "positive", "hey_nexi"),
    "nexi": os.path.join(BASE_DIR, "positive", "nexi"),
    "variants": os.path.join(BASE_DIR, "positive", "variants"),
}

NEGATIVE_DIRS = {
    "speech": os.path.join(BASE_DIR, "negative", "speech"),
    "noise": os.path.join(BASE_DIR, "negative", "noise"),
    "similar_words": os.path.join(BASE_DIR, "negative", "similar_words"),
    "keyboard_taps": os.path.join(BASE_DIR, "negative", "keyboard_taps"),
}


def ensure_dirs():
    for d in list(POSITIVE_DIRS.values()) + list(NEGATIVE_DIRS.values()):
        os.makedirs(d, exist_ok=True)


def count_existing() -> dict:
    counts = {}
    for name, d in {**POSITIVE_DIRS, **NEGATIVE_DIRS}.items():
        if os.path.isdir(d):
            counts[name] = len([f for f in os.listdir(d) if f.endswith(".wav")])
        else:
            counts[name] = 0
    return counts


def record_clip(duration_sec: float, device: int | None) -> np.ndarray:
    import sounddevice as sd
    frames = int(SAMPLE_RATE * duration_sec)
    recording = sd.rec(frames, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, device=device)
    sd.wait()
    return recording.squeeze()


def save_wav(filepath: str, audio: np.ndarray):
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())


def calc_rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))


def collect_samples(label: str, directory: str, count: int, duration: float,
                    prompt: str, device: int | None, existing_count: int) -> list[float]:
    """Collect `count` audio clips, prompting user each time.
    Returns list of RMS values for quality checking.
    """
    rms_values = []
    start_idx = existing_count + 1
    for i in range(count):
        idx = start_idx + i
        input(f"  [{idx}/{existing_count + count}] {prompt}")
        time.sleep(0.3)
        audio = record_clip(duration, device)
        rms = calc_rms(audio)
        rms_values.append(rms)
        filepath = os.path.join(directory, f"{label}_{idx:03d}.wav")
        save_wav(filepath, audio)
        status = "OK" if rms > 0.005 else "QUIET"
        print(f"    saved ({len(audio) / SAMPLE_RATE:.1f}s, rms={rms:.5f}) [{status}]")
    return rms_values


def summarize_rms(rms_values: list[float], label: str) -> tuple[int, int]:
    if not rms_values:
        return 0, 0
    avg_rms = np.mean(rms_values)
    quiet_count = sum(1 for r in rms_values if r < 0.005)
    print(f"  [{label}] avg_rms={avg_rms:.5f} quiet={quiet_count}/{len(rms_values)}")
    return quiet_count, len(rms_values)


def main():
    parser = argparse.ArgumentParser(description="Collect hotword training data")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument("--quick", action="store_true", help="Collect fewer samples for testing")
    args = parser.parse_args()

    print("=" * 60)
    print("HOTWORD TRAINING DATA COLLECTION")
    print("=" * 60)
    print()
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Output dir: {BASE_DIR}")
    print()

    ensure_dirs()
    existing = count_existing()
    print(f"Existing samples: {existing}")
    print()

    if args.quick:
        n_hey = 3
        n_nexi = 3
        n_variants = 2
        n_speech = 3
        n_noise = 3
        n_similar = 3
        n_taps = 3
    else:
        n_hey = 30
        n_nexi = 30
        n_variants = 10
        n_speech = 30
        n_noise = 30
        n_similar = 30
        n_taps = 30

    all_rms: dict[str, list[float]] = {}
    total_quiet = 0
    total_samples = 0

    # --- Positive: "Hey Nexi" ---
    print("[POSITIVE] 'Hey Nexi' samples")
    print(f"  Collecting {n_hey} samples. Say 'Hey Nexi' in your normal voice.")
    print("  Vary distance: near, normal, slightly far.")
    rms = collect_samples("hey_nexi", POSITIVE_DIRS["hey_nexi"],
                          n_hey, 2.0, "Press Enter, pause 1s, say 'Hey Nexi'...",
                          args.device, existing["hey_nexi"])
    all_rms["hey_nexi"] = rms
    q, t = summarize_rms(rms, "hey_nexi")
    total_quiet += q
    total_samples += t
    print()

    # --- Positive: "Nexi" ---
    print("[POSITIVE] 'Nexi' samples")
    print(f"  Collecting {n_nexi} samples. Say just 'Nexi'.")
    rms = collect_samples("nexi", POSITIVE_DIRS["nexi"],
                          n_nexi, 2.0, "Press Enter, pause 1s, say 'Nexi'...",
                          args.device, existing["nexi"])
    all_rms["nexi"] = rms
    q, t = summarize_rms(rms, "nexi")
    total_quiet += q
    total_samples += t
    print()

    # --- Positive: Variants ---
    print("[POSITIVE] Variant phrases")
    print("  Say full commands like 'Hey Nexi, what is AI' or 'Nexi, open YouTube'")
    phrases = [
        "Hey Nexi, what is AI",
        "Nexi, open YouTube",
        "Hey Nexi, play music",
        "Nexi, what time is it",
        "Hey Nexi, tell me a joke",
        "Nexi, search the web",
        "Hey Nexi, set a timer",
        "Nexi, good morning",
        "Hey Nexi, how are you",
        "Nexi, thank you",
    ]
    for i in range(min(n_variants, len(phrases))):
        p = phrases[i]
        input(f"  [{i+1}/{n_variants}] Press Enter, say '{p}'...")
        time.sleep(0.3)
        audio = record_clip(3.0, args.device)
        rms_val = calc_rms(audio)
        all_rms.setdefault("variants", []).append(rms_val)
        fname = f"variant_{i+1:03d}.wav"
        save_wav(os.path.join(POSITIVE_DIRS["variants"], fname), audio)
        status = "OK" if rms_val > 0.005 else "QUIET"
        print(f"    saved ({len(audio) / SAMPLE_RATE:.1f}s, rms={rms_val:.5f}) [{status}]")
        total_samples += 1
        if rms_val < 0.005:
            total_quiet += 1
    print()

    # --- Negative: Random speech ---
    print("[NEGATIVE] Random speech (non-wake)")
    print("  Speak random sentences without saying 'Hey Nexi' or 'Nexi'.")
    rms = collect_samples("speech", NEGATIVE_DIRS["speech"],
                          n_speech, 2.0, "Press Enter, speak random words...",
                          args.device, existing["speech"])
    all_rms["speech"] = rms
    q, t = summarize_rms(rms, "speech")
    total_quiet += q
    total_samples += t
    print()

    # --- Negative: Silence / background ---
    print("[NEGATIVE] Silence / background noise")
    print(f"  Recording {n_noise} silence samples. Stay quiet.")
    rms = collect_samples("silence", NEGATIVE_DIRS["noise"],
                          n_noise, 2.0, "Press Enter, stay quiet...",
                          args.device, existing["noise"])
    all_rms["noise"] = rms
    q, t = summarize_rms(rms, "noise")
    total_quiet += q
    total_samples += t
    print()

    # --- Negative: Similar words ---
    print("[NEGATIVE] Similar-sounding phrases")
    similar_phrases = [
        "hey service", "hey jobs", "hey justice", "hey jar",
        "jar", "java", "journey", "hey journey",
        "hello nexi", "hey guardian", "hey garden", "hey jasmine",
        "hey jolly", "hey jupiter", "hey junction", "hey jersey",
        "hey jigsaw", "hey jargon", "hey genius", "hey janitor",
        "hey joker", "hey garage", "hey harmony", "hey harvest",
        "hey javelin", "hey jaguar", "hey jazz", "hey gesture",
        "hey general", "hey generous",
    ]
    print(f"  Say {n_similar} similar phrases.")
    for i in range(min(n_similar, len(similar_phrases))):
        phrase = similar_phrases[i]
        input(f"  [{i+1}/{n_similar}] Press Enter, say '{phrase}'...")
        time.sleep(0.3)
        audio = record_clip(2.0, args.device)
        rms_val = calc_rms(audio)
        all_rms.setdefault("similar_words", []).append(rms_val)
        fname = f"similar_{i+1:03d}.wav"
        save_wav(os.path.join(NEGATIVE_DIRS["similar_words"], fname), audio)
        status = "OK" if rms_val > 0.005 else "QUIET"
        print(f"    saved ({len(audio) / SAMPLE_RATE:.1f}s, rms={rms_val:.5f}) [{status}]")
        total_samples += 1
        if rms_val < 0.005:
            total_quiet += 1
    print()

    # --- Negative: Keyboard / mouse / table taps ---
    print("[NEGATIVE] Keyboard, mouse, table tap sounds")
    print(f"  Collecting {n_taps} samples. Tap on desk, keyboard, mouse near mic.")
    for i in range(n_taps):
        input(f"  [{i+1}/{n_taps}] Press Enter, then tap desk/keyboard/mouse 3-5 times...")
        time.sleep(0.2)
        audio = record_clip(1.5, args.device)
        rms_val = calc_rms(audio)
        all_rms.setdefault("keyboard_taps", []).append(rms_val)
        fname = f"tap_{i+1:03d}.wav"
        save_wav(os.path.join(NEGATIVE_DIRS["keyboard_taps"], fname), audio)
        status = "OK" if rms_val > 0.005 else "QUIET"
        print(f"    saved ({len(audio) / SAMPLE_RATE:.1f}s, rms={rms_val:.5f}) [{status}]")
        total_samples += 1
        if rms_val < 0.005:
            total_quiet += 1
    print()

    # --- Summary ---
    print("=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    final_counts = count_existing()
    total = sum(final_counts.values())
    print(f"  Total samples: {total}")
    print(f"  Quiet samples (rms < 0.005): {total_quiet}/{total_samples}")
    print()
    for name, count in final_counts.items():
        print(f"  {name}: {count}")
    print()

    # Quality check
    issues = []
    if final_counts.get("hey_nexi", 0) < 25:
        issues.append(f"Only {final_counts.get('hey_nexi', 0)}/30+ 'Hey Nexi' samples")
    if final_counts.get("nexi", 0) < 25:
        issues.append(f"Only {final_counts.get('nexi', 0)}/30+ 'Nexi' samples")
    if final_counts.get("speech", 0) < 20:
        issues.append(f"Only {final_counts.get('speech', 0)}/30 random speech samples")
    if final_counts.get("similar_words", 0) < 20:
        issues.append(f"Only {final_counts.get('similar_words', 0)}/30 similar word samples")
    if final_counts.get("noise", 0) < 20:
        issues.append(f"Only {final_counts.get('noise', 0)}/30 silence/noise samples")
    if total_quiet > total_samples * 0.3:
        issues.append(f"Too many quiet samples ({total_quiet}/{total_samples}). Speak louder or check mic.")

    if not issues:
        print("STATUS: READY for hotword training")
        print()
        print("Next step: python scripts/train_hotword_model.py")
    else:
        print("STATUS: NOT READY")
        for issue in issues:
            print(f"  - {issue}")
        print()
        print("Fix issues above, then re-run this script.")
        sys.exit(1)


if __name__ == "__main__":
    main()
