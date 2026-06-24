#!/usr/bin/env python3
"""Import clap and not-clap samples from public datasets + hotword negatives.

Supports fast mode (ESC-50 only), missing dataset warnings, local hotword
negatives, and augmentation.

Flags:
  --use-esc50-only               Skip all non-ESC-50 datasets instead of failing
  --allow-missing <name>         Don't fail if a specific dataset is missing
  --include-local-hotword-negatives  Import Hey Nexi/Nexi as NOT_CLAP
  --augment                      Enable augmentation
  --no-augment                   Disable augmentation
  --augment-multiplier N         Augmentation copies per sample (default: 3)

Positive labels: clap (ESC-50 class 12)
Negative labels: ESC-50 non-clap + hotword positives/negatives

Output: datasets/clap_nn/{train,val,test}/{clap,not_clap}/ + manifest
"""

import argparse
import csv
import glob
import hashlib
import math
import os
import random
import shutil
import sys
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TARGET_SR = 44100
WINDOW_SEC = 0.5
WINDOW_SAMPLES = int(TARGET_SR * WINDOW_SEC)
MAX_FILES_PER_LABEL = 5000
VAL_RATIO = 0.15
TEST_RATIO = 0.15

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUBLIC_DIR = os.path.join(BASE_DIR, "datasets", "public")
HOTWORD_POS_DIR = os.path.join(BASE_DIR, "datasets", "hotword", "positive")
HOTWORD_NEG_DIR = os.path.join(BASE_DIR, "datasets", "hotword", "negative")
LOCAL_NOISE_DIR = os.path.join(BASE_DIR, "datasets", "local", "noise")
LOCAL_TAPS_DIR = os.path.join(BASE_DIR, "datasets", "local", "taps")
LOCAL_SILENCE_DIR = os.path.join(BASE_DIR, "datasets", "local", "silence")
OUTPUT_DIR = os.path.join(BASE_DIR, "datasets", "clap_nn")

ESC50_CLAP_INDEX = {12}  # hand clap

MANIFEST_FIELDS = [
    "original_file", "output_file", "label", "source_dataset",
    "source_class", "augmentation_type", "duration_ms", "sample_rate", "split",
]


def _ensure_dirs():
    for split in ("train", "val", "test"):
        for label in ("clap", "not_clap"):
            d = os.path.join(OUTPUT_DIR, split, label)
            os.makedirs(d, exist_ok=True)


def _dedup_name(src_path: str) -> str:
    name = os.path.basename(src_path)
    stem, _ = os.path.splitext(name)
    # Strip any trailing garbage after .wav
    if stem.lower().endswith(".wav"):
        stem = stem[:-4]
    h = hashlib.md5(src_path.encode()).hexdigest()[:8]
    return f"{stem}_{h}.wav"


def _resample_wav(samples: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return samples
    ratio = target_sr / orig_sr
    target_len = max(1, int(len(samples) * ratio))
    indices = np.linspace(0, len(samples) - 1, target_len)
    return np.interp(indices, np.arange(len(samples)), samples).astype(samples.dtype)


def _safe_normalize(samples: np.ndarray) -> np.ndarray:
    peak = np.max(np.abs(samples))
    if peak > 0 and peak < 32767:
        samples = samples.astype(np.float64) * (32767.0 / peak)
    return samples.astype(np.int16)


def _load_wav(fpath: str) -> tuple[np.ndarray, int]:
    with wave.open(fpath, "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        frames = wf.readframes(wf.getnframes())
        data = np.frombuffer(frames, dtype=np.int16)
        if nch > 1:
            data = data.reshape(-1, nch).mean(axis=1).astype(np.int16)
        return data, sr


def _segment_into_windows(audio: np.ndarray, sr: int) -> list[np.ndarray]:
    audio = _resample_wav(audio, sr, TARGET_SR)
    windows = []
    i = 0
    while i + WINDOW_SAMPLES <= len(audio):
        windows.append(audio[i:i + WINDOW_SAMPLES])
        i += WINDOW_SAMPLES
    return windows


def _save_wav(dst: str, samples: np.ndarray, sr: int = TARGET_SR):
    with wave.open(dst, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.astype(np.int16).tobytes())


def _copy_windows(src_path: str, dst_dir: str, sr: int, label: str, log: list,
                  source_dataset: str = "", source_class: str = "") -> int:
    try:
        audio, file_sr = _load_wav(src_path)
    except Exception as exc:
        log.append(f"SKIP unreadable {src_path}: {exc}")
        return 0
    windows = _segment_into_windows(audio, file_sr)
    if not windows:
        return 0
    copied = 0
    for win in windows:
        dst = os.path.join(dst_dir, _dedup_name(src_path + f"_win{copied}"))
        if os.path.exists(dst):
            continue
        _save_wav(dst, win)
        copied += 1
    log.append(f"COPY {src_path} -> {dst_dir} ({copied} windows) label={label} "
               f"src_ds={source_dataset} src_cls={source_class}")
    return copied


# --- Augmentation ---

def _random_gain(samples: np.ndarray, min_g: float = 0.7, max_g: float = 1.3) -> np.ndarray:
    gain = random.uniform(min_g, max_g)
    return (samples.astype(np.float64) * gain).astype(np.int16)


def _add_background_noise(samples: np.ndarray, noise_std_range=(0.001, 0.01)) -> np.ndarray:
    noise = np.random.randn(len(samples)).astype(np.float64) * random.uniform(*noise_std_range) * 32767
    return (samples.astype(np.float64) + noise).astype(np.int16)


def _time_shift(samples: np.ndarray, max_shift_frac: float = 0.1) -> np.ndarray:
    shift = random.randint(0, max(1, int(len(samples) * max_shift_frac)))
    direction = random.choice([-1, 1])
    shifted = np.roll(samples, shift * direction)
    if direction == 1:
        shifted[:shift] = 0
    else:
        shifted[-shift:] = 0
    return shifted


def _random_crop(samples: np.ndarray, crop_frac: float = 0.15) -> np.ndarray:
    crop_len = int(len(samples) * crop_frac)
    if crop_len < 1:
        return samples
    start = random.randint(0, crop_len)
    cropped = samples[start:start + len(samples) - crop_len]
    if len(cropped) < len(samples):
        pad = len(samples) - len(cropped)
        cropped = np.pad(cropped, (0, pad), mode="constant")
    return cropped


def _silence_padding(samples: np.ndarray, pad_frac_range=(0.0, 0.2)) -> np.ndarray:
    pad_frac = random.uniform(*pad_frac_range)
    pad_len = int(len(samples) * pad_frac)
    if pad_len < 1:
        return samples
    pad_front = random.randint(0, pad_len)
    pad_back = pad_len - pad_front
    return np.pad(samples, (pad_front, pad_back), mode="constant").astype(np.int16)


def _mild_pitch(samples: np.ndarray, sr: int) -> np.ndarray:
    """Apply mild pitch/time stretch using linear interpolation (safe, no librosa)."""
    rate = random.uniform(0.93, 1.07)
    target_len = max(1, int(len(samples) / rate))
    indices = np.linspace(0, len(samples) - 1, target_len)
    stretched = np.interp(indices, np.arange(len(samples)), samples.astype(np.float64))
    if len(stretched) < len(samples):
        stretched = np.pad(stretched, (0, len(samples) - len(stretched)), mode="constant")
    else:
        stretched = stretched[:len(samples)]
    return stretched.astype(np.int16)


def augment_wav(samples: np.ndarray, sr: int, aug_types: list[str],
                is_clap: bool) -> list[tuple[np.ndarray, str]]:
    """Apply augmentations, returning list of (augmented_samples, aug_name)."""
    results = []
    for aug in aug_types:
        s = samples.copy()
        name = aug
        if aug == "gain":
            s = _random_gain(s)
        elif aug == "noise":
            s = _add_background_noise(s)
        elif aug == "shift":
            s = _time_shift(s)
        elif aug == "crop":
            s = _random_crop(s)
        elif aug == "silence_pad":
            s = _silence_padding(s)
        elif aug == "pitch":
            s = _mild_pitch(s, sr)
        else:
            continue
        results.append((s, name))
    return results


# --- Import functions ---

def _import_esc50(esc50_dir: str, log: list, augment: bool = False,
                  augment_mult: int = 3) -> dict[str, int]:
    """Import ESC-50: class 12 = hand clap -> clap, everything else -> not_clap."""
    counts = {"clap": 0, "not_clap": 0}
    meta_path = os.path.join(esc50_dir, "meta", "esc50.csv")
    if not os.path.isfile(meta_path):
        log.append("SKIP ESC-50: no meta/esc50.csv found")
        return counts

    aug_types = ["gain", "noise", "shift", "crop", "silence_pad"] if augment else []

    with open(meta_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fold = int(row["fold"])
            cls_id = int(row["target"])
            category = row["category"]
            fname = row["filename"]
            fpath = os.path.join(esc50_dir, "audio", fname)
            if not os.path.isfile(fpath):
                continue
            split = "train" if fold <= 3 else ("val" if fold == 4 else "test")
            if cls_id == 12:
                dst_dir = os.path.join(OUTPUT_DIR, split, "clap")
                lbl = "clap"
            else:
                dst_dir = os.path.join(OUTPUT_DIR, split, "not_clap")
                lbl = "not_clap"
            n = _copy_windows(fpath, dst_dir, TARGET_SR, lbl, log,
                              source_dataset="ESC-50", source_class=category)
            counts[lbl] += n

            # Augment clap positives with extra copies
            if augment and lbl == "clap" and n > 0:
                try:
                    audio, file_sr = _load_wav(fpath)
                except Exception:
                    continue
                windows = _segment_into_windows(audio, file_sr)
                for _ in range(augment_mult - 1):
                    for win_idx, win in enumerate(windows):
                        aug_results = augment_wav(win, TARGET_SR, aug_types, is_clap=True)
                        for aug_samples, aug_name in aug_results:
                            aug_name_out = _dedup_name(fpath + f"_aug_{aug_name}_win{win_idx}")
                            dst = os.path.join(dst_dir, aug_name_out)
                            if not os.path.exists(dst):
                                _save_wav(dst, aug_samples)
                                n += 1
                                counts[lbl] += 1
                                log.append(f"AUG {fpath} -> {dst} aug={aug_name} label={lbl}")
                # Augment not_clap as well with milder settings
            if augment and lbl == "not_clap" and n > 0 and random.random() < 0.3:
                try:
                    audio, file_sr = _load_wav(fpath)
                except Exception:
                    continue
                windows = _segment_into_windows(audio, file_sr)
                for win_idx, win in enumerate(windows[:1]):
                    aug_results = augment_wav(win, TARGET_SR, ["gain", "noise", "silence_pad"],
                                              is_clap=False)
                    for aug_samples, aug_name in aug_results:
                        aug_name_out = _dedup_name(fpath + f"_aug_{aug_name}_win{win_idx}")
                        dst = os.path.join(dst_dir, aug_name_out)
                        if not os.path.exists(dst):
                            _save_wav(dst, aug_samples)
                            n += 1
                            counts[lbl] += 1
                            log.append(f"AUG {fpath} -> {dst} aug={aug_name} label={lbl}")
    return counts


def _import_speech_commands(sc_dir: str, log: list) -> dict[str, int]:
    """Google Speech Commands: all words -> not_clap."""
    counts = {"not_clap": 0}
    wavs = glob.glob(os.path.join(sc_dir, "**", "*.wav"), recursive=True)
    for fpath in wavs:
        if not os.path.isfile(fpath):
            continue
        rel = os.path.relpath(fpath, sc_dir)
        parts = rel.split(os.sep)
        if len(parts) < 2:
            continue
        if parts[0] in ("_background_noise_",):
            continue
        split = "train"
        n = _copy_windows(fpath, os.path.join(OUTPUT_DIR, split, "not_clap"),
                          TARGET_SR, "not_clap", log,
                          source_dataset="SpeechCommands", source_class=parts[0])
        counts["not_clap"] += n
    return counts


def _import_hotword_positives(log: list, augment: bool = False) -> dict[str, int]:
    """Hotword positives (Hey Nexi, Nexi, variants) -> NOT_CLAP negatives."""
    counts = {"not_clap": 0}
    aug_types = ["gain", "noise", "silence_pad"] if augment else []
    for subdir in ("hey_nexi", "nexi", "variants"):
        d = os.path.join(HOTWORD_POS_DIR, subdir)
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "*.wav")):
            n = _copy_windows(f, os.path.join(OUTPUT_DIR, "train", "not_clap"),
                              TARGET_SR, f"not_clap:hw_{subdir}", log,
                              source_dataset="hotword_positive", source_class=subdir)
            counts["not_clap"] += n
            if augment and n > 0:
                try:
                    audio, file_sr = _load_wav(f)
                except Exception:
                    continue
                windows = _segment_into_windows(audio, file_sr)
                for win in windows:
                    aug_results = augment_wav(win, TARGET_SR, aug_types, is_clap=False)
                    for aug_samples, aug_name in aug_results:
                        aug_path = _dedup_name(f + f"_aug_{aug_name}")
                        dst = os.path.join(OUTPUT_DIR, "train", "not_clap", aug_path)
                        if not os.path.exists(dst):
                            _save_wav(dst, aug_samples)
                            counts["not_clap"] += 1
                            log.append(f"AUG {f} -> {dst} aug={aug_name} label=not_clap")
    return counts


def _import_hotword_negatives(log: list, augment: bool = False) -> dict[str, int]:
    """Hotword negatives (speech, noise, similar, keyboard) -> NOT_CLAP."""
    counts = {"not_clap": 0}
    aug_types = ["gain", "noise", "silence_pad"] if augment else []
    for subdir in ("speech", "noise", "similar_words", "keyboard_taps"):
        d = os.path.join(HOTWORD_NEG_DIR, subdir)
        if not os.path.isdir(d):
            continue
        for f in glob.glob(os.path.join(d, "*.wav")):
            n = _copy_windows(f, os.path.join(OUTPUT_DIR, "train", "not_clap"),
                              TARGET_SR, f"not_clap:neg_{subdir}", log,
                              source_dataset="hotword_negative", source_class=subdir)
            counts["not_clap"] += n
    return counts


def _import_local_dir(directory: str, label: str, source_dataset: str,
                      source_class: str, log: list) -> dict[str, int]:
    """Import WAV files from a local directory as not_clap."""
    counts = {"not_clap": 0}
    if not os.path.isdir(directory):
        return counts
    for f in glob.glob(os.path.join(directory, "*.wav")):
        n = _copy_windows(f, os.path.join(OUTPUT_DIR, "train", "not_clap"),
                          TARGET_SR, "not_clap", log,
                          source_dataset=source_dataset, source_class=source_class)
        counts["not_clap"] += n
    return counts


def _redistribute_splits(log: list):
    """Move a portion of train files to val/test for class balance."""
    for label in ("clap", "not_clap"):
        src_dir = os.path.join(OUTPUT_DIR, "train", label)
        if not os.path.isdir(src_dir):
            continue
        files = [f for f in glob.glob(os.path.join(src_dir, "*.wav")) if os.path.isfile(f)]
        random.shuffle(files)
        n_val = max(1, int(len(files) * VAL_RATIO))
        n_test = max(1, int(len(files) * TEST_RATIO))
        n_train = len(files) - n_val - n_test
        for i, f in enumerate(files):
            if i < n_train:
                continue
            if i < n_train + n_val:
                dst = os.path.join(OUTPUT_DIR, "val", label, os.path.basename(f))
            else:
                dst = os.path.join(OUTPUT_DIR, "test", label, os.path.basename(f))
            shutil.move(f, dst)
        log.append(f"REDISTRIBUTE {label}: train={n_train} val={n_val} test={n_test}")


def _collect_label_files(directory: str) -> list[str]:
    return sorted(glob.glob(os.path.join(directory, "**", "*.wav"), recursive=True))


def _write_manifest(log: list) -> dict:
    manifest_path = os.path.join(OUTPUT_DIR, "manifest.csv")
    rows = []
    counts = {"train_clap": 0, "train_not_clap": 0,
              "val_clap": 0, "val_not_clap": 0,
              "test_clap": 0, "test_not_clap": 0}
    for split in ("train", "val", "test"):
        for label in ("clap", "not_clap"):
            d = os.path.join(OUTPUT_DIR, split, label)
            for f in _collect_label_files(d):
                rows.append({"path": os.path.relpath(f, OUTPUT_DIR),
                             "split": split, "label": label})
                counts[f"{split}_{label}"] += 1
    with open(manifest_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "split", "label"])
        w.writeheader()
        w.writerows(rows)
    log.append(f"MANIFEST {manifest_path} ({len(rows)} rows)")
    return counts


def _warn_missing_dataset(name: str, path: str, allow_missing: set, use_esc50_only: bool):
    """Log warning if dataset missing. Only error if not allowed."""
    if os.path.isdir(path):
        return True
    if name in allow_missing or use_esc50_only:
        print(f"  {name}: NOT FOUND ({path}) [allowed missing - skipping]")
        return False
    print(f"  {name}: NOT FOUND ({path}) [REQUIRED - will affect training]")
    return False


def main():
    parser = argparse.ArgumentParser(description="Import clap dataset")
    parser.add_argument("--esc50", type=str,
                        default=os.path.join(PUBLIC_DIR, "ESC50"),
                        help="Path to ESC-50 dataset")
    parser.add_argument("--fsd50k", type=str,
                        default=os.path.join(PUBLIC_DIR, "FSD50K"),
                        help="Path to FSD50K dataset")
    parser.add_argument("--urbansound8k", type=str,
                        default=os.path.join(PUBLIC_DIR, "UrbanSound8K"),
                        help="Path to UrbanSound8K dataset")
    parser.add_argument("--speech-commands", type=str,
                        default=os.path.join(PUBLIC_DIR, "SpeechCommands"),
                        help="Path to Google Speech Commands")
    parser.add_argument("--freesound", type=str,
                        default=os.path.join(PUBLIC_DIR, "Freesound"),
                        help="Path to Freesound dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be done without copying")
    parser.add_argument("--skip-redistribute", action="store_true",
                        help="Skip train/val/test redistribution")

    # Fast mode flags
    parser.add_argument("--use-esc50-only", action="store_true",
                        help="Only use ESC-50 for positives, skip non-ESC-50 datasets "
                             "instead of requiring them")
    parser.add_argument("--allow-missing", type=str, nargs="*", default=[],
                        help="Dataset names that are allowed to be missing "
                             "(e.g. SpeechCommands FSD50K UrbanSound8K Freesound)")
    parser.add_argument("--include-local-hotword-negatives", action="store_true",
                        help="Import local hotword negatives (Hey Nexi/Nexi) as NOT_CLAP")
    parser.add_argument("--augment", action="store_true", default=None,
                        help="Enable data augmentation")
    parser.add_argument("--no-augment", action="store_true", default=None,
                        help="Disable data augmentation")
    parser.add_argument("--augment-multiplier", type=int, default=3,
                        help="Augmentation multiplier for clap positives (default: 3)")
    args = parser.parse_args()

    # Resolve augment flag
    augment = args.augment
    if args.no_augment and not args.augment:
        augment = False
    elif args.augment and not args.no_augment:
        augment = True
    else:
        augment = os.getenv("CLAP_AUGMENT_ENABLED", "true").lower() in ("1", "true", "yes")
        if args.no_augment:
            augment = False

    allow_missing = set(args.allow_missing)
    use_esc50_only = args.use_esc50_only

    random.seed(args.seed)
    log: list[str] = []
    total_counts: dict[str, int] = {}

    print("=" * 60)
    print("CLAP DATASET IMPORTER")
    print("=" * 60)
    print()
    if use_esc50_only:
        print("[MODE] ESC-50 only (--use-esc50-only)")
    if allow_missing:
        print(f"[MODE] Allowed missing: {', '.join(sorted(allow_missing))}")
    if augment:
        mult = args.augment_multiplier
        print(f"[MODE] Augmentation enabled (multiplier={mult})")
    else:
        print("[MODE] Augmentation disabled")
    if args.include_local_hotword_negatives:
        print("[MODE] Including local hotword negatives")
    print()

    if not args.dry_run:
        _ensure_dirs()

    print("[1] Scanning public datasets...")
    datasets_found = []

    # ESC-50
    if os.path.isdir(args.esc50):
        datasets_found.append("ESC50")
        counts = _import_esc50(args.esc50, log, augment=augment,
                               augment_mult=args.augment_multiplier)
        for k, v in counts.items():
            total_counts[k] = total_counts.get(k, 0) + v
        print(f"  ESC-50: {counts.get('clap', 0)} clap, {counts.get('not_clap', 0)} not_clap")
    else:
        print(f"  ESC-50: NOT FOUND ({args.esc50})")

    # FSD50K
    if use_esc50_only:
        print(f"  FSD50K: skipped (--use-esc50-only)")
    elif _warn_missing_dataset("FSD50K", args.fsd50k, allow_missing, use_esc50_only):
        datasets_found.append("FSD50K")
        print("  FSD50K: found (importing all as not_clap)")
        fsd50k_dev = os.path.join(args.fsd50k, "FSD50K.dev_audio")
        if os.path.isdir(fsd50k_dev):
            wavs = glob.glob(os.path.join(fsd50k_dev, "*.wav"))
            for fpath in wavs:
                n = _copy_windows(fpath, os.path.join(OUTPUT_DIR, "train", "not_clap"),
                                  TARGET_SR, "not_clap", log,
                                  source_dataset="FSD50K", source_class="unknown")
                total_counts["not_clap"] = total_counts.get("not_clap", 0) + n
            print(f"  FSD50K: imported {len(wavs)} files as not_clap")
        else:
            print("  FSD50K: no audio directory found (skipping)")

    # UrbanSound8K
    if use_esc50_only:
        print(f"  UrbanSound8K: skipped (--use-esc50-only)")
    elif _warn_missing_dataset("UrbanSound8K", args.urbansound8k, allow_missing, use_esc50_only):
        datasets_found.append("UrbanSound8K")
        us8k_audio = os.path.join(args.urbansound8k, "audio")
        if os.path.isdir(us8k_audio):
            wavs = glob.glob(os.path.join(us8k_audio, "**", "*.wav"), recursive=True)
            for fpath in wavs:
                n = _copy_windows(fpath, os.path.join(OUTPUT_DIR, "train", "not_clap"),
                                  TARGET_SR, "not_clap", log,
                                  source_dataset="UrbanSound8K", source_class="unknown")
                total_counts["not_clap"] = total_counts.get("not_clap", 0) + n
            print(f"  UrbanSound8K: imported {len(wavs)} files as not_clap")
        else:
            print("  UrbanSound8K: no audio directory found (skipping)")

    # Google Speech Commands
    if use_esc50_only:
        print(f"  SpeechCommands: skipped (--use-esc50-only)")
    elif _warn_missing_dataset("SpeechCommands", args.speech_commands, allow_missing, use_esc50_only):
        datasets_found.append("SpeechCommands")
        counts = _import_speech_commands(args.speech_commands, log)
        total_counts["not_clap"] = total_counts.get("not_clap", 0) + counts.get("not_clap", 0)
        print(f"  SpeechCommands: {counts.get('not_clap', 0)} not_clap")

    # Freesound
    if use_esc50_only:
        print(f"  Freesound: skipped (--use-esc50-only)")
    elif _warn_missing_dataset("Freesound", args.freesound, allow_missing, use_esc50_only):
        datasets_found.append("Freesound")
        wavs = glob.glob(os.path.join(args.freesound, "**", "*.wav"), recursive=True)
        for fpath in wavs:
            n = _copy_windows(fpath, os.path.join(OUTPUT_DIR, "train", "not_clap"),
                              TARGET_SR, "not_clap", log,
                              source_dataset="Freesound", source_class="unknown")
            total_counts["not_clap"] = total_counts.get("not_clap", 0) + n
        print(f"  Freesound: imported {len(wavs)} files as not_clap")

    # Local negatives
    if args.include_local_hotword_negatives:
        print()
        print("[2] Importing local hotword negatives as NOT_CLAP...")

        print("  [2a] Hotword positives (Hey Nexi/Nexi) -> NOT_CLAP...")
        counts = _import_hotword_positives(log, augment=augment)
        total_counts["not_clap"] = total_counts.get("not_clap", 0) + counts.get("not_clap", 0)
        print(f"    Hey Nexi / Nexi / variants: {counts.get('not_clap', 0)} windows")

        print("  [2b] Hotword negatives (speech, noise, similar, keyboard) -> NOT_CLAP...")
        counts = _import_hotword_negatives(log)
        total_counts["not_clap"] = total_counts.get("not_clap", 0) + counts.get("not_clap", 0)
        print(f"    Speech / noise / similar / keyboard: {counts.get('not_clap', 0)} windows")

        print("  [2c] Local noise directory -> NOT_CLAP...")
        counts = _import_local_dir(LOCAL_NOISE_DIR, "not_clap", "local", "noise", log)
        total_counts["not_clap"] = total_counts.get("not_clap", 0) + counts.get("not_clap", 0)
        print(f"    Local noise: {counts.get('not_clap', 0)} windows")

        print("  [2d] Local taps directory -> NOT_CLAP...")
        counts = _import_local_dir(LOCAL_TAPS_DIR, "not_clap", "local", "taps", log)
        total_counts["not_clap"] = total_counts.get("not_clap", 0) + counts.get("not_clap", 0)
        print(f"    Local taps: {counts.get('not_clap', 0)} windows")

        print("  [2e] Local silence directory -> NOT_CLAP...")
        counts = _import_local_dir(LOCAL_SILENCE_DIR, "not_clap", "local", "silence", log)
        total_counts["not_clap"] = total_counts.get("not_clap", 0) + counts.get("not_clap", 0)
        print(f"    Local silence: {counts.get('not_clap', 0)} windows")
    else:
        print()
        print("[2] Skipping local hotword negatives (use --include-local-hotword-negatives)")

    print()
    print("[3] Redistributing train/val/test splits...")
    if not args.dry_run and not args.skip_redistribute:
        _redistribute_splits(log)
        print("  Done")
    else:
        print("  Skipped (--dry-run or --skip-redistribute)")

    print()
    print("[4] Writing manifest...")
    if not args.dry_run:
        final_counts = _write_manifest(log)
        for k, v in final_counts.items():
            total_counts[k] = v
    else:
        final_counts = {}

    pos = final_counts.get("train_clap", 0) + final_counts.get("val_clap", 0) + final_counts.get("test_clap", 0)
    neg = final_counts.get("train_not_clap", 0) + final_counts.get("val_not_clap", 0) + final_counts.get("test_not_clap", 0)

    print()
    print("=" * 60)
    print("IMPORT SUMMARY")
    print("=" * 60)
    print(f"  Datasets found: {', '.join(datasets_found) if datasets_found else 'NONE'}")
    print(f"  Positive (clap): {pos}")
    print(f"  Negative (not_clap): {neg}")
    print(f"  Total: {pos + neg}")
    if pos > 0 or neg > 0:
        balance = pos / (pos + neg) * 100 if (pos + neg) > 0 else 0
        print(f"  Clap ratio: {balance:.1f}%")
    print(f"  Manifest: {os.path.join(OUTPUT_DIR, 'manifest.csv')}")
    print()

    if pos == 0 and neg == 0:
        print("WARNING: No samples were imported. No public datasets found.")
        print("To download ESC-50: https://github.com/karolpiczak/ESC-50")
        print()
        print("Hotword positives (Hey Nexi/Nexi) are still imported as NOT_CLAP negatives")
        print("if --include-local-hotword-negatives is passed and recordings exist.")
        sys.exit(0)

    if pos == 0:
        print("WARNING: No positive (clap) samples. ESC-50 class 12 (hand clap) was not found.")
        print("Clap training will have no positive examples.")

    print()
    print("Next step: python scripts/train_clap_nn.py --train-dir datasets/clap_nn/train")

    # Generate report
    report_lines = [
        "# CLAP Dataset Import Report",
        "",
        f"**Date:** {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Importer:** `scripts/import_clap_datasets.py`",
        "",
        "## Mode",
        f"- ESC-50 only: {use_esc50_only}",
        f"- Augmentation: {augment}",
        f"- Augment multiplier: {args.augment_multiplier}",
        f"- Local hotword negatives: {args.include_local_hotword_negatives}",
        f"- Allowed missing: {', '.join(sorted(allow_missing)) if allow_missing else 'none'}",
        "",
        "## Dataset Folders Found",
    ]
    for d in datasets_found:
        report_lines.append(f"- {d}")
    report_lines += [
        "",
        "## Import Counts",
        f"- Positive (clap) samples: {pos}",
        f"- Negative (not_clap) samples: {neg}",
        f"- Manifest path: {os.path.join(OUTPUT_DIR, 'manifest.csv')}",
        f"- Class balance: {balance:.1f}% clap" if (pos + neg) > 0 else "- Class balance: N/A",
        "",
        "## Per-Split Counts",
    ]
    for split in ("train", "val", "test"):
        for label in ("clap", "not_clap"):
            k = f"{split}_{label}"
            report_lines.append(f"- {k}: {final_counts.get(k, 0)}")
    report_lines += [
        "",
        "## Skipped Folders",
    ]
    for name, path in [("ESC-50", args.esc50), ("FSD50K", args.fsd50k),
                       ("UrbanSound8K", args.urbansound8k),
                       ("SpeechCommands", args.speech_commands),
                       ("Freesound", args.freesound)]:
        if not os.path.isdir(path):
            report_lines.append(f"- {name}: {path} (not found)")
    report_lines += [
        "",
        "## License Notes",
        "- ESC-50: CC BY-NC 4.0 (non-commercial research only)",
        "- FSD50K: CC BY 4.0",
        "- UrbanSound8K: CC BY 4.0",
        "- Google Speech Commands: CC BY 4.0",
        "- Hotword recordings: user-collected, no redistribution",
        "",
        "*This dataset is for local training only. Do not redistribute.*",
    ]
    report_path = os.path.join(OUTPUT_DIR, "CLAP_DATASET_IMPORT_REPORT.md")
    if not args.dry_run:
        with open(report_path, "w") as f:
            f.write("\n".join(report_lines))
        print(f"Report saved: {report_path}")


if __name__ == "__main__":
    main()
