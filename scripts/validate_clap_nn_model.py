#!/usr/bin/env python3
"""Validate a trained CLAP_NN model against test data with comprehensive metrics.

Required PASS thresholds:
  clap recall >= 90%
  not_clap precision >= 95%
  Hey Nexi false clap = 0/20
  Nexi false clap = 0/20
  random speech false clap <= 1/50
  silence false clap = 0
  keyboard/table tap false clap <= 1/30

Usage:
  python scripts/validate_clap_nn_model.py --test-dir datasets/clap_nn/test
"""

import argparse
import glob
import math
import os
import sys

import numpy as np

# Windows consoles default to cp1252 and crash on the summary's arrow glyphs; force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_model_class():
    model_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "external", "CLAP_NN_INSPECT", "CLAP_NN"
    )
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)
    from cnn_sound_model import AudioClassifier
    return AudioClassifier


def _load_wav(filepath: str, target_sr: int = 44100) -> np.ndarray:
    from scipy.io import wavfile
    sr, data = wavfile.read(filepath)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    if sr != target_sr:
        ratio = target_sr / sr
        target_len = int(len(data) * ratio)
        indices = np.linspace(0, len(data) - 1, target_len)
        data = np.interp(indices, np.arange(len(data)), data)
    return data


def _create_mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    low_freq_mel = 0.0
    high_freq_mel = 2595.0 * math.log10(1.0 + (sr / 2.0) / 700.0)
    mel_points = np.linspace(low_freq_mel, high_freq_mel, n_mels + 2)
    hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
    bin = np.floor((n_fft + 1) * hz_points / sr).astype(int)
    bin = np.clip(bin, 0, n_fft // 2)
    fbank = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        f_m_minus = int(bin[m - 1])
        f_m = int(bin[m])
        f_m_plus = int(bin[m + 1])
        for k in range(f_m_minus, f_m):
            fbank[m - 1, k] = (k - bin[m - 1]) / (bin[m] - bin[m - 1])
        for k in range(f_m, f_m_plus):
            fbank[m - 1, k] = (bin[m + 1] - k) / (bin[m + 1] - bin[m])
    return fbank


def _compute_mel_spec(waveform: np.ndarray, sr: int, n_fft: int,
                      hop_length: int, n_mels: int, target_size: int) -> np.ndarray:
    import torch
    import torch.nn.functional as F

    window = torch.hann_window(n_fft)
    wf_t = torch.from_numpy(waveform).unsqueeze(0)
    stft = torch.stft(wf_t, n_fft=n_fft, hop_length=hop_length,
                      win_length=n_fft, window=window, return_complex=True)
    mag = stft.abs().numpy().squeeze()

    mel_basis = _create_mel_filterbank(sr, n_fft, n_mels)
    mel_spec = mel_basis @ mag
    mel_spec = np.maximum(mel_spec, 1e-10)
    mel_spec = np.log(mel_spec)

    mel_t = torch.from_numpy(mel_spec).unsqueeze(0).unsqueeze(0)
    mel_t = F.interpolate(mel_t, size=(target_size, target_size),
                          mode="bilinear", align_corners=False)
    mel_spec = mel_t.squeeze().numpy()

    mean = mel_spec.mean()
    std = mel_spec.std()
    if std > 1e-10:
        mel_spec = (mel_spec - mean) / std
    else:
        mel_spec = mel_spec - mean

    return mel_spec[np.newaxis, :, :]


def get_wav_files(directory: str) -> list:
    if not os.path.isdir(directory):
        return []
    return sorted([os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(".wav")])


def _classify_file(model, fpath: str, args) -> tuple[int, float]:
    """Return (predicted_label, clap_probability)."""
    wf = _load_wav(fpath, args.sample_rate)
    spec = _compute_mel_spec(wf, args.sample_rate, args.n_fft,
                             args.hop_length, args.n_mels, args.target_size)
    import torch
    inp = torch.from_numpy(spec).unsqueeze(0).float()
    output = model(inp)
    probs = torch.exp(output)
    clap_prob = float(probs[0, 1].item())
    predicted = 1 if clap_prob >= args.threshold else 0
    return predicted, clap_prob


def resolve_model_path(path: str) -> str:
    if path:
        return path
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "external", "CLAP_NN",
                         "ASSETS", "CLAP_DETECTS", "MODELS", "Clap_Detect_Model.pth")


def main():
    parser = argparse.ArgumentParser(description="Validate CLAP_NN model against dataset")
    parser.add_argument("--model-path", type=str, default="",
                        help="Path to trained model (.pth)")
    parser.add_argument("--test-dir", type=str, default="",
                        help="Test base dir with clap/ and not_clap/ subdirs (default: datasets/clap_nn/test)")
    parser.add_argument("--threshold", type=float, default=0.85,
                        help="Classification threshold (default: 0.85)")
    parser.add_argument("--n-mels", type=int, default=128)
    parser.add_argument("--n-fft", type=int, default=400)
    parser.add_argument("--hop-length", type=int, default=200)
    parser.add_argument("--target-size", type=int, default=256)
    parser.add_argument("--sample-rate", type=int, default=44100)
    parser.add_argument("--hotword-clap-false", action="store_true",
                        help="Check Hey Nexi/Nexi false clap rate")
    parser.add_argument("--fast", action="store_true",
                        help="Fast mode thresholds (85% recall, 92% precision)")
    args = parser.parse_args()

    import torch

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    test_dir = args.test_dir or os.path.join(base, "datasets", "clap_nn", "test")

    model_path = resolve_model_path(args.model_path)
    print(f"Model: {model_path}")
    print(f"Test dir: {test_dir}")
    print()

    if not os.path.isfile(model_path):
        print(f"[FAIL] Model not found at: {model_path}")
        print("Run scripts/train_clap_nn.py first.")
        sys.exit(1)

    # Load model
    AudioClassifier = _load_model_class()
    model = AudioClassifier()
    state_dict = torch.load(model_path, map_location=torch.device("cpu"))
    model.load_state_dict(state_dict)
    model.eval()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"[OK] Model loaded ({n_params} params)")
    print()

    # Collect test files
    clap_test_files = get_wav_files(os.path.join(test_dir, "clap"))
    not_clap_test_files = get_wav_files(os.path.join(test_dir, "not_clap"))

    # Collect special negative groups
    hw_base = os.path.join(base, "datasets", "hotword")
    hey_nexi_files = get_wav_files(os.path.join(hw_base, "positive", "hey_nexi"))
    nexi_files = get_wav_files(os.path.join(hw_base, "positive", "nexi"))
    speech_files = get_wav_files(os.path.join(hw_base, "negative", "speech"))
    silence_files = get_wav_files(os.path.join(hw_base, "negative", "noise"))
    keyboard_files = get_wav_files(os.path.join(hw_base, "negative", "keyboard_taps"))

    print(f"Test clap files:      {len(clap_test_files)}")
    print(f"Test not_clap files:   {len(not_clap_test_files)}")
    print(f"Hey Nexi files:     {len(hey_nexi_files)}")
    print(f"Nexi files:         {len(nexi_files)}")
    print(f"Random speech files:  {len(speech_files)}")
    print(f"Silence/noise files:  {len(silence_files)}")
    print(f"Keyboard/tap files:   {len(keyboard_files)}")
    print()

    # Run inference
    results = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    confusion = {"clap_as_clap": 0, "clap_as_not": 0,
                 "not_as_clap": 0, "not_as_not": 0}
    per_category: dict[str, dict] = {}
    per_file_rows = []

    test_groups = [
        ("clap", clap_test_files, 1, "clap"),
        ("not_clap", not_clap_test_files, 0, "not_clap"),
        ("hey_nexi", hey_nexi_files, 0, "hey_nexi"),
        ("nexi", nexi_files, 0, "nexi"),
        ("speech", speech_files, 0, "speech"),
        ("silence", silence_files, 0, "silence"),
        ("keyboard", keyboard_files, 0, "keyboard"),
    ]

    with torch.no_grad():
        for cat_name, files, true_label, group in test_groups:
            if cat_name not in per_category:
                per_category[cat_name] = {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "count": 0}
            for fpath in files:
                try:
                    predicted, clap_prob = _classify_file(model, fpath, args)
                except Exception as e:
                    print(f"[WARN] {os.path.basename(fpath)}: {e}")
                    continue

                correct = predicted == true_label
                if group == "clap" and predicted == 1:
                    confusion["clap_as_clap"] += 1
                elif group == "clap" and predicted == 0:
                    confusion["clap_as_not"] += 1
                elif group != "clap" and predicted == 1:
                    confusion["not_as_clap"] += 1
                elif group != "clap" and predicted == 0:
                    confusion["not_as_not"] += 1

                if true_label == 1:
                    if predicted == 1:
                        results["tp"] += 1
                        per_category[cat_name]["tp"] += 1
                    else:
                        results["fn"] += 1
                        per_category[cat_name]["fn"] += 1
                else:
                    if predicted == 1:
                        results["fp"] += 1
                        per_category[cat_name]["fp"] += 1
                    else:
                        results["tn"] += 1
                        per_category[cat_name]["tn"] += 1
                per_category[cat_name]["count"] += 1

                per_file_rows.append((
                    os.path.basename(fpath),
                    group,
                    "clap" if predicted == 1 else "not_clap",
                    clap_prob,
                    "OK" if correct else "FAIL",
                ))

    # Print per-file
    print(f"{'File':<40} {'Group':<14} {'Pred':<10} {'Conf':<8} Status")
    print("-" * 80)
    for row in per_file_rows:
        print(f"{row[0]:<40} {row[1]:<14} {row[2]:<10} {row[3]:<8.4f} {row[4]}")

    # Summary
    total = results["tp"] + results["tn"] + results["fp"] + results["fn"]
    accuracy = (results["tp"] + results["tn"]) / total if total > 0 else 0.0
    precision_clap = results["tp"] / (results["tp"] + results["fp"]) if (results["tp"] + results["fp"]) > 0 else 0.0
    recall_clap = results["tp"] / (results["tp"] + results["fn"]) if (results["tp"] + results["fn"]) > 0 else 0.0
    precision_not = results["tn"] / (results["tn"] + results["fn"]) if (results["tn"] + results["fn"]) > 0 else 0.0
    recall_not = results["tn"] / (results["tn"] + results["fp"]) if (results["tn"] + results["fp"]) > 0 else 0.0
    f1 = 2 * (precision_clap * recall_clap) / (precision_clap + recall_clap) if (precision_clap + recall_clap) > 0 else 0.0

    print()
    print("=" * 60)
    print("VALIDATION RESULTS")
    print("=" * 60)
    print(f"  Total samples:          {total}")
    print(f"  TP (clap→clap):         {results['tp']}")
    print(f"  FP (not_clap→clap):     {results['fp']}")
    print(f"  TN (not_clap→not):      {results['tn']}")
    print(f"  FN (clap→not):          {results['fn']}")
    print(f"  Accuracy:               {accuracy:.4f}")
    print(f"  Clap precision:         {precision_clap:.4f}")
    print(f"  Clap recall:            {recall_clap:.4f}")
    print(f"  Not-clap precision:     {precision_not:.4f}")
    print(f"  Not-clap recall:        {recall_not:.4f}")
    print(f"  F1 (clap):              {f1:.4f}")
    print(f"  Threshold:              {args.threshold}")
    print()
    print("-- Per-Category False Clap Rate --")
    for cat_name in ["clap", "not_clap", "hey_nexi", "nexi", "speech", "silence", "keyboard"]:
        if cat_name not in per_category or per_category[cat_name]["count"] == 0:
            continue
        c = per_category[cat_name]
        fp_rate = c["fp"] / c["count"] * 100
        fn_rate = c["fn"] / c["count"] * 100 if cat_name == "clap" else 0.0
        print(f"  {cat_name:14s}: {c['count']:4d} samples, "
              f"FP={c['fp']:3d} ({fp_rate:5.1f}%)"
              + (f", FN={c['fn']:3d} ({fn_rate:5.1f}%)" if cat_name == "clap" else ""))

    print()
    print("-- Confusion Matrix --")
    print(f"                  Predicted clap    Predicted not")
    print(f"  Actual clap      {confusion['clap_as_clap']:6d}            {confusion['clap_as_not']:6d}")
    print(f"  Actual not_clap  {confusion['not_as_clap']:6d}            {confusion['not_as_not']:6d}")
    print()

    # PASS/FAIL evaluation
    hey_fp = per_category.get("hey_nexi", {}).get("fp", 0)
    nexi_fp = per_category.get("nexi", {}).get("fp", 0)
    speech_fp = per_category.get("speech", {}).get("fp", 0)
    speech_count = per_category.get("speech", {}).get("count", 0)
    silence_fp = per_category.get("silence", {}).get("fp", 0)
    keyboard_fp = per_category.get("keyboard", {}).get("fp", 0)
    keyboard_count = per_category.get("keyboard", {}).get("count", 0)

    is_fast = args.fast

    failures = []
    if is_fast:
        if recall_clap < 0.85:
            failures.append(f"[FAST] Clap recall {recall_clap:.3f} < 0.85")
        if precision_not < 0.92:
            failures.append(f"[FAST] Not-clap precision {precision_not:.3f} < 0.92")
    else:
        if recall_clap < 0.90:
            failures.append(f"Clap recall {recall_clap:.3f} < 0.90")
        if precision_not < 0.95:
            failures.append(f"Not-clap precision {precision_not:.3f} < 0.95")
    if hey_fp > 0:
        failures.append(f"Hey Nexi false clap = {hey_fp} (requires 0)")
    if nexi_fp > 0:
        failures.append(f"Nexi false clap = {nexi_fp} (requires 0)")
    if is_fast:
        if speech_fp > 0:
            failures.append(f"Random speech false clap = {speech_fp}/{speech_count} (requires 0 for fast)")
    else:
        if speech_fp > 1:
            failures.append(f"Random speech false clap = {speech_fp}/{speech_count} (requires ≤1/50)")
    if silence_fp > 0:
        failures.append(f"Silence false clap = {silence_fp} (requires 0)")
    if keyboard_fp > 1:
        failures.append(f"Keyboard/tap false clap = {keyboard_fp}/{keyboard_count} (requires ≤1/30)")

    if not failures:
        print("VERDICT: VALIDATION PASS")
        sys.exit(0)
    else:
        print("VERDICT: VALIDATION FAIL")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
