#!/usr/bin/env python3
"""Record a clap / not_clap dataset for training the CLAP_NN model.

Records mono 44.1 kHz int16 clips (matching train_clap_nn.py's sample rate) and
auto-splits them 70/15/15 into the layout the trainer expects:

    datasets/clap_nn/{train,val,test}/{clap,not_clap}/*.wav

Then train + deploy + validate (model auto-deploys to the path the runtime loads):

    .venv\\Scripts\\python.exe scripts\\record_clap_dataset.py            # record (interactive)
    .venv\\Scripts\\python.exe scripts\\train_clap_nn.py                  # -> external/CLAP_NN/.../Clap_Detect_Model.pth
    .venv\\Scripts\\python.exe scripts\\validate_clap_nn_model.py --fast  # check recall/precision

Tips for a usable model: record in your real environment, vary clap distance/angle,
and make not_clap cover what actually happens near the mic (speech, typing, door,
silence, music). ~30+ per class is a sane start; re-run with --append to add more.

    --per-class N   clips per class (default 30)
    --clip-sec S    seconds per clip (default 0.7)
    --gap-sec S     pause between clips (default 1.0)
    --device IDX    input device index (default: system default)
    --list-devices  print input devices and exit
    --append        keep existing files instead of clearing the dataset first
    --selfcheck     no mic; exercise the write/split logic and exit (runnable check)
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import wave

import numpy as np

SR = 44100
CLASSES = ("clap", "not_clap")
SPLITS = ("train", "val", "test")
BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "clap_nn")


def _write_wav(path: str, samples_int16: np.ndarray, sr: int = SR) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(np.asarray(samples_int16, dtype=np.int16).tobytes())


def _split_counts(n: int) -> dict[str, int]:
    """70/15/15 with at least 1 per split when n allows."""
    n_test = max(1, round(n * 0.15)) if n >= 3 else 0
    n_val = max(1, round(n * 0.15)) if n >= 3 else 0
    n_train = n - n_val - n_test
    return {"train": n_train, "val": n_val, "test": n_test}


def _split_for_index(i: int, n: int) -> str:
    """Positional split: first train, then val, then test (recording is sequential)."""
    c = _split_counts(n)
    if i < c["train"]:
        return "train"
    if i < c["train"] + c["val"]:
        return "val"
    return "test"


def _next_index(label: str) -> int:
    """Highest existing sample index for a label across all splits, +1 (for --append)."""
    hi = -1
    for split in SPLITS:
        d = os.path.join(BASE, split, label)
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.startswith(f"{label}_") and fn.endswith(".wav"):
                try:
                    hi = max(hi, int(fn[len(label) + 1:-4]))
                except ValueError:
                    pass
    return hi + 1


def _clear_dataset() -> None:
    for split in SPLITS:
        for label in CLASSES:
            shutil.rmtree(os.path.join(BASE, split, label), ignore_errors=True)


def _record_clip(sd, device, clip_sec: float) -> np.ndarray:
    frames = int(clip_sec * SR)
    audio = sd.rec(frames, samplerate=SR, channels=1, dtype="int16", device=device)
    sd.wait()
    return audio.reshape(-1)


def _record_class(sd, device, label: str, n: int, clip_sec: float, gap_sec: float, start_idx: int) -> None:
    prompt = "CLAP ONCE" if label == "clap" else "make NOISE (talk / type / ambient / silence)"
    input(f"\n=== {label.upper()} — {n} clips. {prompt} each time. Press Enter to start... ===")
    end = start_idx + n
    for k in range(n):
        idx = start_idx + k
        for c in (3, 2, 1):
            print(f"  {label} {k + 1}/{n}  recording in {c}...", end="\r", flush=True)
            time.sleep(gap_sec / 3.0)
        print(f"  {label} {k + 1}/{n}  ** NOW **            ", flush=True)
        clip = _record_clip(sd, device, clip_sec)
        split = _split_for_index(idx, end)
        path = os.path.join(BASE, split, label, f"{label}_{idx}.wav")
        _write_wav(path, clip)
    print(f"  {label}: saved {n} clips.")


def _selfcheck() -> int:
    """No mic: write synthetic clips through the real write+split path and assert the layout."""
    import tempfile
    global BASE
    saved = BASE
    tmp = tempfile.mkdtemp(prefix="clap_ds_")
    BASE = os.path.join(tmp, "datasets", "clap_nn")
    try:
        n = 6
        for label in CLASSES:
            for i in range(n):
                clip = (np.random.randn(int(0.3 * SR)) * 1500).astype(np.int16)
                split = _split_for_index(i, n)
                _write_wav(os.path.join(BASE, split, label, f"{label}_{i}.wav"), clip)
        for split in SPLITS:
            for label in CLASSES:
                d = os.path.join(BASE, split, label)
                assert os.path.isdir(d) and os.listdir(d), f"empty split dir: {split}/{label}"
        counts = _split_counts(n)
        assert sum(counts.values()) == n, counts
        print(f"selfcheck OK -- split({n}) = {counts}, all {len(SPLITS)}x{len(CLASSES)} dirs populated")
        return 0
    finally:
        BASE = saved
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Record a clap/not_clap dataset for CLAP_NN.")
    parser.add_argument("--per-class", type=int, default=30)
    parser.add_argument("--clip-sec", type=float, default=0.7)
    parser.add_argument("--gap-sec", type=float, default=1.0)
    parser.add_argument("--device", type=int, default=None)
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--append", action="store_true")
    parser.add_argument("--selfcheck", action="store_true")
    args = parser.parse_args()

    if args.selfcheck:
        return _selfcheck()

    import sounddevice as sd

    if args.list_devices:
        print(sd.query_devices())
        return 0

    if not args.append:
        _clear_dataset()

    start = {label: (_next_index(label) if args.append else 0) for label in CLASSES}
    print(f"[REC] dataset={BASE}")
    print(f"[REC] per_class={args.per_class} clip_sec={args.clip_sec} device={args.device if args.device is not None else 'default'}")
    for label in CLASSES:
        _record_class(sd, args.device, label, args.per_class, args.clip_sec, args.gap_sec, start[label])

    total = sum(
        len(os.listdir(os.path.join(BASE, s, l)))
        for s in SPLITS for l in CLASSES
        if os.path.isdir(os.path.join(BASE, s, l))
    )
    print(f"\n[REC] done -- {total} clips under {BASE}")
    print("[REC] next: .venv\\Scripts\\python.exe scripts\\train_clap_nn.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
