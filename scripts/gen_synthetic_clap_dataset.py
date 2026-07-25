#!/usr/bin/env python3
"""Generate a physically-motivated SYNTHETIC clap / not_clap dataset for CLAP_NN.

A real clap is an impulsive, broadband, fast-decaying transient -> a short vertical
broadband stripe in a mel spectrogram. not_clap covers the things that are NOT that:
steady noise (white/pink), tones/hums, speech-like AM broadband, low-freq thumps
(door slam: a stripe but only low band), key-tap trains (many weak transients), and
near-silence.

This BOOTSTRAPS a deployable model without recording. It will NOT match your real
mic's claps as well as real recordings. To improve: record real claps with
  scripts\\record_clap_dataset.py --append
and retrain. Then re-run train_clap_nn.py.

    --per-class N   samples per class (default 250)
    --seed S        RNG seed (default 7)
    --append        add to the existing dataset instead of clearing it
    --selfcheck     generate a few in-memory and assert the clap signature; no files
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from scipy.signal import butter, lfilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.record_clap_dataset import _write_wav, _split_for_index, _clear_dataset, BASE, CLASSES, SPLITS  # noqa: E402

SR = 44100


def _bandpass(x: np.ndarray, lo: float, hi: float, sr: int = SR) -> np.ndarray:
    ny = sr / 2.0
    lo = max(20.0, min(lo, ny - 200))
    hi = max(lo + 100.0, min(hi, ny - 100))
    b, a = butter(2, [lo / ny, hi / ny], btype="band")
    return lfilter(b, a, x)


def _norm_int16(x: np.ndarray, peak: float) -> np.ndarray:
    m = float(np.max(np.abs(x))) or 1.0
    return np.clip(x / m * peak, -32767, 32767).astype(np.int16)


def gen_clap(rng: np.random.Generator, dur: float = 0.6) -> np.ndarray:
    n = int(SR * dur)
    x = rng.standard_normal(n) * rng.uniform(0.005, 0.03)  # quiet background (<< burst)
    nbursts = int(rng.choice([1, 1, 1, 2]))            # mostly single, some double-clap
    # The CNN's FC layer is NOT translation-invariant, so train claps WHERE they actually land
    # at classify time: the onset gate fires with the clap in the last ~30% of the rolling
    # window. Concentrate there (with margin + truncation) so detection is robust to frame jitter.
    base = int(rng.integers(int(0.70 * n), int(0.99 * n)))
    for k in range(nbursts):
        decay = rng.uniform(0.02, 0.08)                # short, clap-like
        blen = min(n - 2, int(SR * decay * 4))
        t = np.arange(blen) / SR
        env = np.exp(-t / decay)
        atk = max(1, int(SR * 0.0005))                 # ~0.5 ms sharp attack
        env[:atk] *= np.linspace(0, 1, atk)
        burst = rng.standard_normal(blen) * env
        burst = _bandpass(burst, rng.uniform(300, 700), rng.uniform(4000, 7000))
        pos = max(0, min(base + (0 if k == 0 else int(SR * rng.uniform(0.06, 0.18))), n - 1))
        end = min(pos + blen, n)                        # truncate at window end (matches streaming)
        x[pos:end] += (burst * rng.uniform(0.6, 1.0))[: end - pos]
    return _norm_int16(x, rng.uniform(8000, 30000))


def gen_not_clap(rng: np.random.Generator, dur: float = 0.6) -> np.ndarray:
    n = int(SR * dur)
    kind = rng.choice(["noise", "tone", "speech", "thump", "keys", "silence"])
    if kind == "noise":
        x = rng.standard_normal(n)
        if rng.random() < 0.5:
            x = _bandpass(x, 50, rng.uniform(1000, 3000))   # pink-ish
        return _norm_int16(x * rng.uniform(0.3, 1.0), rng.uniform(3000, 20000))
    if kind == "tone":
        f = rng.uniform(60, 2500)
        t = np.arange(n) / SR
        x = np.sin(2 * np.pi * f * t)
        for h in (2, 3):
            if rng.random() < 0.5:
                x += (0.4 / h) * np.sin(2 * np.pi * f * h * t)
        x += rng.standard_normal(n) * 0.05
        return _norm_int16(x, rng.uniform(6000, 25000))
    if kind == "speech":                                    # slow-AM broadband + formants
        t = np.arange(n) / SR
        env = 0.5 * (1 + np.sin(2 * np.pi * rng.uniform(2, 6) * t))
        x = _bandpass(rng.standard_normal(n), 200, 3500) * env
        for f in rng.uniform(300, 2500, size=2):
            x += 0.3 * np.sin(2 * np.pi * f * t) * env
        return _norm_int16(x, rng.uniform(6000, 22000))
    if kind == "thump":                                     # low-freq slam: low-band stripe, long decay
        x = rng.standard_normal(n) * 0.02
        decay = rng.uniform(0.08, 0.25)
        blen = min(n - 2, int(SR * decay * 3))
        t = np.arange(blen) / SR
        burst = _bandpass(rng.standard_normal(blen) * np.exp(-t / decay), 30, rng.uniform(300, 600))
        pos = max(0, min(int(rng.integers(int(0.1 * n), int(0.5 * n))), n - blen - 1))
        x[pos:pos + blen] += burst * rng.uniform(0.6, 1.0)
        return _norm_int16(x, rng.uniform(8000, 28000))
    if kind == "keys":                                      # train of weak short transients
        x = rng.standard_normal(n) * 0.02
        for _ in range(int(rng.integers(3, 9))):
            blen = int(SR * rng.uniform(0.003, 0.012))
            t = np.arange(blen) / SR
            burst = _bandpass(rng.standard_normal(blen) * np.exp(-t / rng.uniform(0.002, 0.006)), 1500, 7000)
            pos = max(0, min(int(rng.integers(0, n - blen - 1)), n - blen - 1))
            x[pos:pos + blen] += burst * rng.uniform(0.3, 0.7)
        return _norm_int16(x, rng.uniform(4000, 16000))
    return _norm_int16(rng.standard_normal(n) * rng.uniform(5, 40), rng.uniform(300, 4000))  # silence


def _time_concentration(x: np.ndarray, win_ms: float = 50.0) -> float:
    """Fraction of total energy in the single most energetic time window.

    Clap energy lives in one short window (a spectrogram stripe) -> high.
    Steady noise spreads energy across all windows -> ~1/num_windows.
    This is the spectro-temporal property the CNN learns, so it's the right
    sanity signal (crest factor isn't: thump/keys are impulsive too, on purpose).
    """
    x = x.astype(np.float64) ** 2
    w = max(1, int(SR * win_ms / 1000.0))
    nwin = max(1, len(x) // w)
    energies = [x[i * w:(i + 1) * w].sum() for i in range(nwin)]
    total = sum(energies) or 1.0
    return max(energies) / total


def _selfcheck() -> int:
    rng = np.random.default_rng(0)
    claps = [gen_clap(rng) for _ in range(8)]
    steady = [_norm_int16(rng.standard_normal(int(SR * 0.6)), 12000) for _ in range(8)]  # pure steady noise
    for c in claps:
        assert c.dtype == np.int16 and len(c) == int(SR * 0.6), "bad clip shape/dtype"
    clap_conc = float(np.mean([_time_concentration(c) for c in claps]))
    steady_conc = float(np.mean([_time_concentration(c) for c in steady]))
    assert clap_conc > steady_conc * 1.5, (clap_conc, steady_conc)
    print(f"selfcheck OK -- clap time-concentration={clap_conc:.3f} >> steady noise={steady_conc:.3f} (stripe signature present)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a synthetic clap/not_clap dataset.")
    ap.add_argument("--per-class", type=int, default=250)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--append", action="store_true")
    ap.add_argument("--selfcheck", action="store_true")
    args = ap.parse_args()

    if args.selfcheck:
        return _selfcheck()

    if not args.append:
        _clear_dataset()
    rng = np.random.default_rng(args.seed)
    n = args.per_class
    gens = {"clap": gen_clap, "not_clap": gen_not_clap}
    for label in CLASSES:
        for i in range(n):
            clip = gens[label](rng)
            split = _split_for_index(i, n)
            _write_wav(os.path.join(BASE, split, label, f"syn_{label}_{i}.wav"), clip)
        print(f"[GEN] {label}: {n} clips")
    total = sum(
        len(os.listdir(os.path.join(BASE, s, l)))
        for s in SPLITS for l in CLASSES if os.path.isdir(os.path.join(BASE, s, l))
    )
    print(f"[GEN] done -- {total} clips under {BASE}")
    print("[GEN] next: .venv\\Scripts\\python.exe scripts\\train_clap_nn.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
