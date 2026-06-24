#!/usr/bin/env python3
"""Validate a trained custom openWakeWord hotword model.

Loads the exported ONNX model, runs it against held-out or fresh
positive/negative WAV files, and reports detection metrics.

Usage:
  python scripts/validate_hotword_model.py
  python scripts/validate_hotword_model.py --model datasets/hotword/models/custom_hotword.onnx
  python scripts/validate_hotword_model.py --quick
"""

import argparse
import glob
import os
import sys
import json
import time
import warnings

import numpy as np

warnings.filterwarnings("ignore", category=UserWarning, module="torch")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_RATE = 16000
N_FRAMES = 16
N_MELS = 96
FRAME_STEP = 1280

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "hotword")
MODELS_DIR = os.path.join(BASE_DIR, "models")
DEFAULT_MODEL = os.path.join(MODELS_DIR, "custom_hotword.onnx")

POSITIVE_DIRS = [
    os.path.join(BASE_DIR, "positive", "hey_jarvis"),
    os.path.join(BASE_DIR, "positive", "jarvis"),
    os.path.join(BASE_DIR, "positive", "variants"),
]
NEGATIVE_DIRS = [
    os.path.join(BASE_DIR, "negative", "speech"),
    os.path.join(BASE_DIR, "negative", "noise"),
    os.path.join(BASE_DIR, "negative", "similar_words"),
    os.path.join(BASE_DIR, "negative", "keyboard_taps"),
]


def load_wav(fpath: str) -> np.ndarray:
    import wave
    with wave.open(fpath, "rb") as wf:
        assert wf.getnchannels() == 1, f"{fpath}: not mono"
        assert wf.getframerate() == SAMPLE_RATE, f"{fpath}: not 16kHz"
        frames = wf.readframes(wf.getnframes())
        return np.frombuffer(frames, dtype=np.int16).astype(np.float32)


def compute_features(audio: np.ndarray) -> np.ndarray:
    """Compute openWakeWord streaming features for sliding window scoring."""
    from openwakeword.utils import AudioFeatures
    af = AudioFeatures(device="cpu", ncpu=1)

    features_list = []
    step = FRAME_STEP  # 80ms
    i = 0
    while i + FRAME_STEP * N_FRAMES <= len(audio):
        chunk = audio[i:i + FRAME_STEP * N_FRAMES]
        if len(chunk) < FRAME_STEP * N_FRAMES:
            break
        af.reset()
        _ = af.get_features(n_feature_frames=N_FRAMES)  # prime buffer
        _ = af.embed_clips(chunk.astype(np.int16)[None, :], batch_size=1)
        features = af.get_features(n_feature_frames=N_FRAMES)
        features_list.append(features[0])
        i += step

    if not features_list:
        return np.empty((0, N_FRAMES, N_MELS), dtype=np.float32)
    return np.array(features_list)


def compute_features_fast(audio: np.ndarray) -> np.ndarray:
    """Compute openWakeWord features for entire clip at once (batch mode).
    Returns sliding windows of N_FRAMES each.
    """
    from openwakeword.utils import AudioFeatures
    af = AudioFeatures(device="cpu", ncpu=1)
    audio_16 = (audio * 32767).astype(np.int16) if audio.max() <= 1.0 else audio.astype(np.int16)
    emb = af.embed_clips(audio_16[None, :], batch_size=1)
    emb = emb[0]
    if emb.shape[0] < N_FRAMES:
        return np.empty((0, N_FRAMES, N_MELS), dtype=np.float32)
    windows = np.array([emb[i:i + N_FRAMES] for i in range(emb.shape[0] - N_FRAMES + 1)])
    return windows.astype(np.float32)


def main():
    parser = argparse.ArgumentParser(description="Validate hotword model")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"Path to ONNX model (default: {DEFAULT_MODEL})")
    parser.add_argument("--positive-dirs", nargs="*", default=[],
                        help="Override positive WAV directories")
    parser.add_argument("--negative-dirs", nargs="*", default=[],
                        help="Override negative WAV directories")
    parser.add_argument("--threshold", type=float, default=0.35,
                        help="Detection threshold (default: 0.35)")
    parser.add_argument("--quick", action="store_true",
                        help="Use fewer files for quick validation")
    parser.add_argument("--live", action="store_true",
                        help="Live mic test mode")
    parser.add_argument("--list-devices", action="store_true",
                        help="List audio devices and exit")
    parser.add_argument("--duration", type=float, default=5.0,
                        help="Duration in seconds for live test (default: 5)")
    args = parser.parse_args()

    if args.list_devices:
        import sounddevice as sd
        print("Audio devices:")
        print(sd.query_devices())
        return

    if not os.path.exists(args.model):
        print(f"ERROR: Model not found: {args.model}")
        print("Run scripts/train_hotword_model.py first.")
        sys.exit(1)

    # Load ONNX session
    import onnxruntime as ort
    session = ort.InferenceSession(args.model)
    input_name = session.get_inputs()[0].name
    expected_shape = session.get_inputs()[0].shape
    print(f"Input: {input_name} {expected_shape}")
    print(f"Device: {'GPU' if ort.get_device() == 'GPU' else 'CPU'}")

    if args.live:
        print("LIVE MIC TEST MODE")
        print(f"Listening for {args.duration}s...")
        import sounddevice as sd
        audio = sd.rec(int(args.duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                       channels=1, dtype=np.float32)
        sd.wait()
        audio = audio.squeeze()
        features = compute_features_fast(audio)
        if features.shape[0] == 0:
            print("No features computed (clip too short)")
            return
        scores = session.run(None, {input_name: features})[0]
        max_score = float(scores.max())
        mean_score = float(scores.mean())
        print(f"  Max score: {max_score:.4f}")
        print(f"  Mean score: {mean_score:.4f}")
        print(f"  Detected: {'YES' if max_score >= args.threshold else 'no'}")
        return

    # File-based validation
    positive_dirs = args.positive_dirs or POSITIVE_DIRS
    negative_dirs = args.negative_dirs or NEGATIVE_DIRS

    print("HOTWORD MODEL VALIDATION")
    print("=" * 60)
    print(f"Model: {args.model}")
    print()

    max_files = 5 if args.quick else 9999

    def collect_files(dirs, label):
        files = []
        for d in dirs:
            if os.path.isdir(d):
                fs = sorted(glob.glob(os.path.join(d, "*.wav")))[:max_files]
                for f in fs:
                    files.append((f, label))
        return files

    test_files = []
    test_files.extend(collect_files(positive_dirs, 1))
    test_files.extend(collect_files(negative_dirs, 0))

    if not test_files:
        print("ERROR: No WAV files found. Run collect_hotword_training_data.py first.")
        sys.exit(1)

    print(f"Testing {len(test_files)} files:")
    pos_count = sum(1 for _, lbl in test_files if lbl == 1)
    neg_count = sum(1 for _, lbl in test_files if lbl == 0)
    print(f"  Positive: {pos_count}, Negative: {neg_count}")
    print()

    results = []
    total_start = time.time()

    for fpath, true_label in test_files:
        name = os.path.basename(fpath)
        audio = load_wav(fpath)
        features = compute_features_fast(audio)

        if features.shape[0] == 0:
            print(f"  {name}: SKIP (no features)")
            continue

        scores = session.run(None, {input_name: features})[0]
        max_score = float(scores.max())
        mean_score = float(scores.mean())
        detected = max_score >= args.threshold

        results.append({
            "file": name,
            "true_label": int(true_label),
            "max_score": max_score,
            "mean_score": mean_score,
            "detected": detected,
            "n_windows": features.shape[0],
        })

        status = "OK" if detected == bool(true_label) else "FAIL"
        print(f"  {name}: label={int(true_label)} max_score={max_score:.4f} "
              f"detected={int(detected)} [{status}]")

    elapsed = time.time() - total_start
    print()
    print("=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)

    if not results:
        print("No results.")
        return

    tp = sum(1 for r in results if r["true_label"] == 1 and r["detected"])
    fp = sum(1 for r in results if r["true_label"] == 0 and r["detected"])
    tn = sum(1 for r in results if r["true_label"] == 0 and not r["detected"])
    fn = sum(1 for r in results if r["true_label"] == 1 and not r["detected"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    print(f"  Threshold: {args.threshold}")
    print(f"  Files: {len(results)} ({elapsed:.1f}s)")
    print(f"  Accuracy:  {accuracy:.3f}")
    print(f"  Precision: {precision:.3f}")
    print(f"  Recall:    {recall:.3f}")
    print(f"  F1 Score:  {f1:.3f}")
    print(f"  TP: {tp}  FP: {fp}  TN: {tn}  FN: {fn}")
    print()

    if args.quick:
        print("  (Quick mode - results are approximate)")
    print()

    # Show per-file scores
    print("Per-file max scores:")
    pos_scores = [r["max_score"] for r in results if r["true_label"] == 1]
    neg_scores = [r["max_score"] for r in results if r["true_label"] == 0]
    if pos_scores:
        print(f"  Positive: mean={np.mean(pos_scores):.4f} "
              f"min={np.min(pos_scores):.4f} max={np.max(pos_scores):.4f}")
    if neg_scores:
        print(f"  Negative: mean={np.mean(neg_scores):.4f} "
              f"min={np.min(neg_scores):.4f} max={np.max(neg_scores):.4f}")


if __name__ == "__main__":
    main()
