"""Train a custom "hey nexi" OpenWakeWord model with enhanced data.

DATA SOURCES (all three feed into training):
  1. TTS (Piper)    — unlimited synthetic positives via piper-sample-generator
  2. Real recording — record YOUR voice saying "hey nexi" via --record
  3. SpeechCommands — Google Speech Commands v2 for rich negatives (--download-sc)

AUGMENTATION (applied to ALL positive samples):
  - Background noise mixing (white/pink/brown) — numpy-only, fast

Usage:
  # Minimal (TTS only, 5000 positives)
  python training/train_hey_nexi.py

  # Record your voice + TTS
  python training/train_hey_nexi.py --record --record-count 50

  # Record + TTS + Speech Commands negatives + augmentation (recommended)
  python training/train_hey_nexi.py --record --record-count 50 --download-sc --augment

  # Full production pipeline
  python training/train_hey_nexi.py ^
      --record --record-count 100 ^
      --download-sc --augment --fp-val ^
      --n-positive 20000 --epochs 100

Outputs:
  models/hey_nexi.onnx          (the trained wake model)
  training/_work/                (all data; safe to delete)
"""

import logging

logging.getLogger('numba').setLevel(logging.WARNING)
logging.getLogger('numba.core').setLevel(logging.WARNING)
logging.getLogger('librosa').setLevel(logging.WARNING)

import argparse
import os
import sys
import math
import random
import urllib.request
import tarfile
import time
from pathlib import Path

import numpy as np

import subprocess

REPO_ROOT = Path(__file__).resolve().parent.parent

_HERE = Path(__file__).resolve().parent
_WORK = _HERE / "_work"

SAMPLE_RATE = 16000
CLIP_SAMPLES = 32000          # 2.0s -> exactly one (16, 96) feature window
TEST_CLIP_SAMPLES = 48000     # 3.0s clips for sliding-window recall checks

FP_VALIDATION_URL = (
    "https://huggingface.co/datasets/dscripka/openWakeWord/resolve/main/"
    "negative_validation_features.npy"
)

SC_URL = (
    "https://storage.googleapis.com/download.tensorflow.org/data/"
    "speech_commands_v0.02.tar.gz"
)

THIS_DIR = Path(__file__).resolve().parent
NEXI_ROOT = THIS_DIR.parent
PIPER_REPO = THIS_DIR / "piper-sample-generator"
PIPER_MODEL = PIPER_REPO / "models" / "en_US-libritts_r-medium.pt"

_BASE_NEGATIVE_PHRASES = [
    "hey there", "hey google", "hey siri", "okay computer", "good morning",
    "what time is it", "turn on the lights", "play some music", "open the door",
    "next please", "the next one", "nexus", "galaxy", "hexagon", "next exit",
    "hey next", "hey nexus", "annexed", "connects", "perplexity", "lexi",
    "hey lexi", "hey maxi", "hey nessie", "hey neddy", "hey betty", "nifty",
    "the weather today is sunny", "set a timer for five minutes",
    "how are you doing today", "tell me a joke", "send a message",
    "i need to buy groceries", "remind me tomorrow", "call my mother",
    "search the internet", "close the window", "volume up", "volume down",
    "take a screenshot", "lock the screen", "what is the news",
    "hey", "next time", "necks", "knicks", "essex",
    "complexity", "reflexes", "vortex", "context", "index", "annex",
    "she sells sea shells", "the quick brown fox", "thank you very much",
    "i would like a coffee", "open my email", "stop the alarm",
]

_PHONETIC_NEARMISS_WORDS = [
    "next", "nexus", "necks", "knicks", "nex", "nix", "nixie",
    "nekko", "necklace", "necro", "negotiate", "negative", "neighbor",
    "neon", "nepal", "nerve", "nest", "netflix", "network",
    "vex", "vax", "lex", "flex", "hex", "dex",
    "sex", "sects", "cex", "tex", "rex", "trex",
    "nifty", "neph", "nebula", "nickel", "nick", "nissan",
]

_HEY_PREFIXED = [
    f"hey {w}" for w in [
        "next", "nexus", "necks", "nix", "nick", "nifty",
        "nessie", "neddy", "nepal", "neon", "netflix",
        "nex", "knicks", "nekko", "negative", "neighbor",
        "nurse", "north", "never", "nothing", "nobody",
        "nacho", "noodle", "nifty", "nervous", "neat",
        "label", "stable", "able", "cable", "table", "fable",
        "kiwi", "easy", "busy", "crazy", "lazy", "dizzy",
        "nexi um", "nexi a", "nexi the", "nexi please",
    ]
]

NEGATIVE_PHRASES = _BASE_NEGATIVE_PHRASES + _HEY_PREFIXED + [
    f"say {w}" for w in _PHONETIC_NEARMISS_WORDS[:20]
] + [
    f"what {w}" for w in _PHONETIC_NEARMISS_WORDS[:15]
] + [
    f"{w} is good" for w in _PHONETIC_NEARMISS_WORDS[:10]
]

# Subset used for TTS generation (first 30 phrases only) to avoid
# loading the piper model 120+ times (takes forever on CPU).
TTS_NEGATIVE_PHRASES = NEGATIVE_PHRASES[:30]


def _ensure_submodule():
    submodule_path = REPO_ROOT / "training" / "piper-sample-generator"
    if not submodule_path.exists():
        print("[TRAIN] piper-sample-generator submodule missing. Run: git submodule update --init --recursive")
        return False
    return True


def log(msg):
    print(f"[TRAIN] {msg}", flush=True)


def build_net(input_shape=(16, 96), layer_dim=128, n_blocks=1):
    import torch.nn as nn

    class FCNBlock(nn.Module):
        def __init__(self, d):
            super().__init__()
            self.fcn_layer = nn.Linear(d, d)
            self.relu = nn.ReLU()
            self.layer_norm = nn.LayerNorm(d)

        def forward(self, x):
            return self.relu(self.layer_norm(self.fcn_layer(x)))

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.flatten = nn.Flatten()
            self.layer1 = nn.Linear(input_shape[0] * input_shape[1], layer_dim)
            self.relu1 = nn.ReLU()
            self.layernorm1 = nn.LayerNorm(layer_dim)
            self.blocks = nn.ModuleList([FCNBlock(layer_dim) for _ in range(n_blocks)])
            self.last_layer = nn.Linear(layer_dim, 1)
            self.last_act = nn.Sigmoid()

        def forward(self, x):
            x = self.relu1(self.layernorm1(self.layer1(self.flatten(x))))
            for block in self.blocks:
                x = block(x)
            return self.last_act(self.last_layer(x))

    return Net()


def export_onnx(net, input_shape, out_path, class_mapping="hey_nexi"):
    import torch
    net = net.to("cpu")
    net.eval()
    try:
        torch.onnx.export(net, torch.rand(input_shape)[None, ], str(out_path),
                          output_names=[class_mapping], dynamo=False)
    except TypeError:
        torch.onnx.export(net, torch.rand(input_shape)[None, ], str(out_path),
                          output_names=[class_mapping])


def ensure_piper():
    if not PIPER_MODEL.is_file():
        log(f"ERROR: piper generator model not found at {PIPER_MODEL}")
        log("Download it with:")
        log("  curl -L -o training/piper-sample-generator/models/en_US-libritts_r-medium.pt \\")
        log("    https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt")
        sys.exit(1)
    sys.path.insert(0, str(PIPER_REPO))


def generate_clips(text, out_dir, n, batch_size, length_scales):
    from piper_sample_generator.__main__ import generate_samples
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("*.wav"))
    if len(existing) >= int(0.95 * n):
        log(f"  reuse {len(existing)} existing clips in {out_dir.name}/ (skip generation)")
        return
    generate_samples(
        text=text,
        output_dir=str(out_dir),
        model=str(PIPER_MODEL),
        max_samples=n,
        batch_size=batch_size,
        length_scales=length_scales,
        noise_scales=(0.667, 0.8),
        noise_scale_ws=(0.8,),
        slerp_weights=(0.3, 0.5, 0.7),
        verbose=False,
    )
    log(f"  generated {len(list(out_dir.glob('*.wav')))} clips in {out_dir.name}/")


def load_wav_16k(path):
    import librosa
    y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    return y.astype(np.float32)


def save_wav_16k(path, y_int16):
    import scipy.io.wavfile as wav
    wav.write(str(path), SAMPLE_RATE, y_int16)


def to_int16_window(y, total_samples, offset=None, rng=None):
    y = y[:total_samples]
    win = np.zeros(total_samples, dtype=np.float32)
    pad = total_samples - len(y)
    if offset is None:
        offset = (rng.randint(0, pad) if (rng and pad > 0) else max(pad, 0))
    offset = max(0, min(offset, max(pad, 0)))
    win[offset:offset + len(y)] = y
    return (np.clip(win, -1.0, 1.0) * 32767).astype(np.int16)


def build_examples(wav_paths, total_samples, shifts, rng, augment_fn=None):
    clips = []
    for p in wav_paths:
        try:
            y = load_wav_16k(p)
        except Exception:
            continue
        if len(y) < 800:
            continue
        for _ in range(shifts):
            win = to_int16_window(y, total_samples, rng=rng)
            if augment_fn:
                win_f = win.astype(np.float32) / 32767.0
                win_f = augment_fn(win_f)
                win = (np.clip(win_f, -1.0, 1.0) * 32767).astype(np.int16)
            clips.append(win)
    return clips


def embed(clips, ncpu):
    from openwakeword.utils import AudioFeatures
    af = AudioFeatures(ncpu=ncpu)
    n = len(clips)
    B = 2048
    n_batches = math.ceil(n / B)
    log(f"  embedding {n} clips in {n_batches} batches of {B} ...")
    t0 = time.time()
    all_X = []
    for b in range(n_batches):
        batch = np.stack(clips[b * B:(b + 1) * B])
        Xb = af.embed_clips(batch, batch_size=128, ncpu=ncpu).astype(np.float32)
        all_X.append(Xb)
        elapsed = time.time() - t0
        pct = 100.0 * (b + 1) / n_batches
        rate = (b + 1) * B / elapsed if elapsed > 0 else 0
        log(f"    embed [{b+1}/{n_batches}] {pct:.0f}%  {elapsed:.0f}s  ~{rate:.0f} clips/s")
    X = np.concatenate(all_X, axis=0)
    log(f"    embed done: {time.time()-t0:.0f}s total, X={X.shape}")
    return X


def _build_noise_augment_fn(rng):
    def _apply(y_f32):
        noise_type = rng.choice(["white", "pink", "brown"])
        n = len(y_f32)
        if noise_type == "white":
            noise = np.random.randn(n).astype(np.float32) * 0.02
        elif noise_type == "pink":
            noise = _pink_noise(n) * 0.03
        else:
            noise = _brown_noise(n) * 0.04
        snr_db = rng.uniform(8, 20)
        signal_power = np.mean(y_f32 ** 2)
        noise_power = np.mean(noise ** 2)
        if noise_power > 0:
            scale = np.sqrt(signal_power / noise_power) * 10 ** (-snr_db / 20)
            noise *= scale
        mix = y_f32 + noise
        peak = max(np.max(np.abs(mix)), 1e-10)
        return mix / peak
    return _apply


def _pink_noise(n):
    white = np.random.randn(n).astype(np.float32)
    for i in range(1, n):
        white[i] += 0.99 * white[i - 1]
    return white / max(np.std(white), 1e-10)


def _brown_noise(n):
    cum = np.cumsum(np.random.randn(n).astype(np.float32) * 0.1)
    return cum / max(np.std(cum), 1e-10)


def _build_composite_augment_fn(rng):
    """Noise-only augmentation (fast, numpy-only)."""
    return _build_noise_augment_fn(rng)


def record_clips(text, out_dir, n, sample_rate=SAMPLE_RATE, max_duration=3.0):
    """Record `n` clips of the user saying `text` via microphone.

    Saves 16-bit mono WAVs to `out_dir`. Skips if enough exist.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    existing = list(out_dir.glob("*.wav"))
    if len(existing) >= n:
        log(f"  reuse {len(existing)} existing recorded clips in {out_dir.name}/")
        return

    try:
        import sounddevice as sd
        import scipy.io.wavfile as wav
    except ImportError:
        log("  [record] sounddevice or scipy not available; cannot record")
        log("  [record] pip install sounddevice scipy")
        return

    log(f"  === Recording {n} clips of '{text}' ===")
    log(f"  Speak clearly after each beep (simulated). Press Ctrl+C to stop.")
    for i in range(n):
        _show_recording_prompt(i + 1, n, text)
        for j in range(3, 0, -1):
            print(f"\r  {j}...", end="", flush=True)
            time.sleep(0.8)
        print(f"\r  GO! ", end="", flush=True)
        recording = sd.rec(int(max_duration * sample_rate),
                           samplerate=sample_rate, channels=1)
        sd.wait()
        print(f"\r  saved    ", end="", flush=True)
        y_int16 = (np.clip(recording.flatten(), -1.0, 1.0) * 32767).astype(np.int16)
        wav.write(str(out_dir / f"rec_{i:04d}.wav"), sample_rate, y_int16)
        time.sleep(0.3)
    log(f"\n  recorded {len(list(out_dir.glob('*.wav')))} clips")


def _show_recording_prompt(i, total, text):
    bar_len = 30
    filled = int(bar_len * i / total)
    bar = "█" * filled + "░" * (bar_len - filled)
    print(f"\n  [{bar}] {i}/{total}")
    print(f"  Say: \"{text}\"")


def download_speech_commands(out_dir):
    """Download and extract Google Speech Commands v2 to `out_dir`.

    Returns list of all .wav file paths, or empty list on failure.
    """
    out_dir = Path(out_dir)
    if out_dir.is_dir() and len(list(out_dir.rglob("*.wav"))) > 1000:
        log(f"  Speech Commands already extracted at {out_dir} "
            f"({len(list(out_dir.rglob('*.wav')))} files)")
        return sorted(out_dir.rglob("*.wav"))

    tarball = out_dir.with_name("speech_commands_v0.02.tar.gz")
    if not tarball.is_file():
        log(f"  downloading Speech Commands v2 (~2.3 GB) ...")
        try:
            urllib.request.urlretrieve(SC_URL, tarball)
        except Exception as exc:
            log(f"  ERROR downloading Speech Commands: {exc}")
            return []

    log(f"  extracting {tarball.name} ...")
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(tarball, "r:gz") as tar:
            tar.extractall(path=out_dir)
    except Exception as exc:
        log(f"  ERROR extracting: {exc}")
        return []

    wavs = sorted(out_dir.rglob("*.wav"))
    log(f"  extracted {len(wavs)} clips to {out_dir}/")
    return wavs


def _download_fp_features(dest_path):
    import numpy as np
    dest_path = Path(dest_path)
    if dest_path.is_file():
        log(f"  FP validation features already cached at {dest_path}")
        return True

    log(f"  downloading FP validation features (~11h audio embeddings) ...")
    tmp = dest_path.with_suffix(".tmp.npy")
    try:
        urllib.request.urlretrieve(FP_VALIDATION_URL, tmp)
        _ = np.load(tmp)
        tmp.rename(dest_path)
        log(f"  downloaded {dest_path.stat().st_size // 1024 // 1024} MB -> {dest_path}")
        return True
    except Exception as exc:
        log(f"  WARNING: failed to download FP validation features: {exc}")
        if tmp.exists():
            tmp.unlink()
        return False


def main():
    ap = argparse.ArgumentParser(
        description="Train hey_nexi OpenWakeWord model with enhanced data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  # TTS only (5000 positives, 10000 negatives)\n"
            "  python training/train_hey_nexi.py\n\n"
            "  # Record your voice + TTS hybrid\n"
            "  python training/train_hey_nexi.py --record --record-count 50\n\n"
            "  # Full pipeline with augmentation + external data\n"
            "  python training/train_hey_nexi.py --record --record-count 100 --download-sc --augment --fp-val\n\n"
            "  # Production-quality\n"
            "  python training/train_hey_nexi.py --record --record-count 100 --download-sc --augment --fp-val --n-positive 20000 --epochs 100"
        ),
    )
    ap.add_argument("--phrase", default="hey nexi")
    ap.add_argument("--n-positive", type=int, default=5000)
    ap.add_argument("--n-negative", type=int, default=10000)
    ap.add_argument("--pos-shifts", type=int, default=1)
    ap.add_argument("--epochs", type=int, default=80)
    ap.add_argument("--patience", type=int, default=10)
    ap.add_argument("--batch-size", type=int, default=1024)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--tts-batch", type=int, default=50)
    ap.add_argument("--augment", action="store_true",
                    help="enable RIR + noise + pitch + speed augmentation")
    ap.add_argument("--fp-val", action="store_true",
                    help="download FP validation set for threshold tuning (~200 MB)")

    # Data generation flags
    ap.add_argument("--record", action="store_true",
                    help="record your own 'hey nexi' clips (creates real voice data)")
    ap.add_argument("--record-count", type=int, default=50,
                    help="number of clips to record (default: 50, takes ~3 min)")
    ap.add_argument("--download-sc", action="store_true",
                    help="download Google Speech Commands v2 for rich negatives (~2.3 GB)")

    ap.add_argument("--ncpu", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", default=str(NEXI_ROOT / "models" / "hey_nexi.onnx"))
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    rng = random.Random(args.seed)

    # Record your own voice (BEFORE TTS so recorded clips are visible)
    if args.record:
        record_dir = _WORK / "recorded"
        record_clips(args.phrase, record_dir, args.record_count)

    ensure_piper()
    pos_dir = _WORK / "positive"
    neg_dir = _WORK / "negative"

    # 1. Synthesize TTS positives
    log(f"synthesizing TTS positives ('{args.phrase}') ...")
    generate_clips(args.phrase, pos_dir, args.n_positive, args.tts_batch,
                   length_scales=(0.7, 0.85, 1.0, 1.15, 1.3))

    # 1b. Copy recorded clips into positive dir (if any)
    recorded_dir = _WORK / "recorded"
    if recorded_dir.is_dir():
        recorded_wavs = list(recorded_dir.glob("*.wav"))
        if recorded_wavs:
            copied = 0
            for src in recorded_wavs:
                dst = pos_dir / f"rec_{src.name}"
                if not dst.exists():
                    import shutil
                    shutil.copy2(str(src), str(dst))
                    copied += 1
            log(f"  added {copied} real-recorded clips to positive set")

    # 2. Synthesize TTS negatives (skip if --download-sc provides enough)
    if args.download_sc:
        log("  skipping TTS negatives (using Speech Commands instead)")
    elif args.n_negative > 0:
        log("synthesizing TTS negatives ...")
        neg_existing = list(neg_dir.glob("*.wav"))
        if len(neg_existing) < int(0.95 * args.n_negative):
            from piper_sample_generator.__main__ import generate_samples
            neg_dir.mkdir(parents=True, exist_ok=True)
            phrases = TTS_NEGATIVE_PHRASES
            per = max(1, args.n_negative // len(phrases))
            idx = 0
            for phrase in phrases:
                generate_samples(
                    text=phrase, output_dir=str(neg_dir), model=str(PIPER_MODEL),
                    max_samples=per, batch_size=args.tts_batch,
                    length_scales=(0.85, 1.0, 1.15), noise_scales=(0.667, 0.8),
                    noise_scale_ws=(0.8,), slerp_weights=(0.4, 0.6),
                    file_names=[f"neg_{idx + k:05d}.wav" for k in range(per)],
                )
                idx += per
            log(f"  generated {len(list(neg_dir.glob('*.wav')))} negative clips")
        else:
            log(f"  reuse {len(neg_existing)} TTS negative clips")
    else:
        log("  n_negative=0, skipping TTS negatives")

    # 2b. Download Speech Commands for additional negatives
    if args.download_sc:
        sc_dir = _WORK / "speech_commands"
        sc_wavs = download_speech_commands(sc_dir)
        if sc_wavs:
            # Sample to avoid blowing up negative count
            n_sc = min(len(sc_wavs), args.n_negative * 3)
            sc_sample = rng.sample(sc_wavs, n_sc)
            # Symlink or copy into neg dir
            sc_link_dir = _WORK / "neg_sc"
            sc_link_dir.mkdir(parents=True, exist_ok=True)
            linked = 0
            for src in sc_sample:
                dst = sc_link_dir / f"sc_{src.stem}.wav"
                if not dst.exists():
                    import shutil
                    shutil.copy2(str(src), str(dst))
                    linked += 1
            log(f"  added {linked} Speech Commands clips as negatives")
            # Also log word distribution
            word_dirs = [d.name for d in sc_dir.iterdir() if d.is_dir()
                         and not d.name.startswith("_")]
            log(f"  Speech Commands word classes: {sorted(word_dirs)}")

    # Collect all WAVs
    pos_wavs = sorted(pos_dir.glob("*.wav"))
    neg_wavs = list(neg_dir.glob("*.wav"))
    sc_link_dir = _WORK / "neg_sc"
    if sc_link_dir.is_dir():
        neg_wavs.extend(sc_link_dir.glob("*.wav"))
    neg_wavs = sorted(neg_wavs)
    log(f"clips: {len(pos_wavs)} positive (TTS + recorded), {len(neg_wavs)} negative")
    if not pos_wavs or not neg_wavs:
        log("ERROR: no clips generated; aborting")
        sys.exit(1)

    rng.shuffle(pos_wavs)
    n_test = max(10, len(pos_wavs) // 10)
    test_pos_wavs, train_pos_wavs = pos_wavs[:n_test], pos_wavs[n_test:]

    # 3. Build augmentation function
    augment_fn = None
    if args.augment:
        augment_fn = _build_composite_augment_fn(rng)
        if augment_fn:
            log("  augmentation enabled: noise (white/pink/brown)")
        else:
            log("  augmentation requested but no modules available")
    else:
        log("  augmentation disabled (use --augment to enable)")

    # 4. Build features
    log("building features (this is the slow part) ...")
    pos_clips = build_examples(train_pos_wavs, CLIP_SAMPLES, args.pos_shifts, rng,
                               augment_fn=augment_fn)
    neg_clips = build_examples(neg_wavs, CLIP_SAMPLES, 1, rng)
    log(f"  embedding {len(pos_clips)} positive + {len(neg_clips)} negative windows")
    Xp = embed(pos_clips, args.ncpu)
    Xn = embed(neg_clips, args.ncpu)
    X = np.concatenate([Xp, Xn], axis=0)
    y = np.concatenate([np.ones(len(Xp)), np.zeros(len(Xn))]).astype(np.float32)
    log(f"  feature matrix: X={X.shape} y={y.shape} (pos={int(y.sum())})")

    test_clips = build_examples(test_pos_wavs, TEST_CLIP_SAMPLES, 1, rng)
    Xtest = embed(test_clips, args.ncpu) if test_clips else None

    # 5. Train
    import torch
    from torch.utils.data import TensorDataset, DataLoader

    perm = np.random.permutation(len(X))
    X, y = X[perm], y[perm]
    n_val = max(1, int(0.1 * len(X)))
    Xv, yv = X[:n_val], y[:n_val]
    Xt, yt = X[n_val:], y[n_val:]

    net = build_net(input_shape=(16, 96), layer_dim=512, n_blocks=2)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    net.to(device)

    n_pos, n_neg = int(yt.sum()), int(len(yt) - yt.sum())
    pos_weight = max(1.0, n_neg / max(1, n_pos))
    log(f"training: {len(Xt)} train / {len(Xv)} val, pos_weight={pos_weight:.2f}")

    ds = TensorDataset(torch.from_numpy(Xt), torch.from_numpy(yt))
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=True)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, mode="max", factor=0.5, patience=5, min_lr=1e-6
    )

    Xv_t = torch.from_numpy(Xv).to(device)
    yv_t = torch.from_numpy(yv).to(device)

    best_state, best_score = None, -1.0
    epochs_no_improve = 0

    for epoch in range(args.epochs):
        net.train()
        for xb, yb in dl:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            out = net(xb).squeeze(-1)
            w = torch.where(yb > 0.5, torch.tensor(pos_weight), torch.tensor(1.0))
            loss = torch.nn.functional.binary_cross_entropy(out, yb, weight=w)
            loss.backward()
            opt.step()

        if (epoch + 1) % 5 == 0 or epoch == args.epochs - 1:
            net.eval()
            with torch.no_grad():
                pv = net(Xv_t).squeeze(-1).cpu().numpy()
            pred = (pv >= 0.5).astype(np.float32)
            yv_np = yv_t.cpu().numpy()
            tp = float(((pred == 1) & (yv_np == 1)).sum())
            fp = float(((pred == 1) & (yv_np == 0)).sum())
            fn = float(((pred == 0) & (yv_np == 1)).sum())
            recall = tp / max(1.0, tp + fn)
            prec = tp / max(1.0, tp + fp)
            score = recall + prec
            sched.step(score)
            if score >= best_score:
                best_score = score
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
                epochs_no_improve = 0
            else:
                epochs_no_improve += 5
            log(f"  epoch {epoch+1:3d}/{args.epochs}  recall={recall:.3f} precision={prec:.3f}  "
                f"lr={opt.param_groups[0]['lr']:.1e}")
            if args.patience > 0 and epochs_no_improve >= args.patience:
                log(f"  early stopping at epoch {epoch+1}")
                break

    if best_state is not None:
        net.load_state_dict(best_state)

    # 6. Threshold tuning
    net.eval()
    with torch.no_grad():
        pv = net(Xv_t).squeeze(-1).cpu().numpy()
    yv_np = yv_t.cpu().numpy()
    best_thr, best_f1 = 0.5, -1.0
    for thr in np.linspace(0.05, 0.95, 19):
        pred = (pv >= thr).astype(np.float32)
        tp = float(((pred == 1) & (yv_np == 1)).sum())
        fp = float(((pred == 1) & (yv_np == 0)).sum())
        fn = float(((pred == 0) & (yv_np == 1)).sum())
        f1 = 2 * tp / max(1e-10, 2 * tp + fp + fn)
        if f1 > best_f1:
            best_f1, best_thr = f1, float(thr)
    log(f"  internal-val threshold: thr={best_thr:.2f} f1={best_f1:.3f}")

    # 7. FP validation set
    if args.fp_val:
        fp_path = _WORK / "fp_features.npy"
        if _download_fp_features(fp_path):
            log("  tuning threshold against FP validation set (~11h audio) ...")
            try:
                fp_features = np.load(str(fp_path)).astype(np.float32)
                net.eval()
                with torch.no_grad():
                    t0 = time.time()
                    fp_t = torch.from_numpy(fp_features).to(device)
                    n_fp_wins = len(fp_features) - 16 + 1
                    fp_preds = []
                    chunk = 8192
                    for start in range(0, n_fp_wins, chunk):
                        end = min(start + chunk, n_fp_wins)
                        wins = torch.stack([fp_t[i:i + 16] for i in range(start, end)])
                        fp_preds.append(net(wins).squeeze(-1))
                    fp_preds = torch.cat(fp_preds).cpu().numpy()
                    log(f"    fp-val ran {len(fp_preds)} windows in {time.time()-t0:.0f}s")
                p99 = np.percentile(fp_preds, 99)
                p95 = np.percentile(fp_preds, 95)
                p90 = np.percentile(fp_preds, 90)
                log(f"  FP dist: p90={p90:.4f} p95={p95:.4f} p99={p99:.4f}")
                fp_thr = max(best_thr, p99)
                est_fp_rate = float((fp_preds >= fp_thr).mean())
                log(f"  fp-val thr={fp_thr:.2f} (est. FP rate: {est_fp_rate:.4f})")
                if fp_thr > best_thr:
                    log(f"  using fp-val threshold: {best_thr:.2f} -> {fp_thr:.2f}")
                    best_thr = fp_thr
            except Exception as exc:
                log(f"  WARNING: FP validation failed: {exc}")

    # 8. Held-out recall
    if Xtest is not None and len(Xtest):
        with torch.no_grad():
            det = 0
            for clip in Xtest:
                wins = np.stack([clip[i:i + 16] for i in range(0, clip.shape[0] - 16 + 1)])
                preds = net(torch.from_numpy(wins.astype(np.float32)).to(device)).squeeze(-1).cpu().numpy()
                if (preds >= best_thr).any():
                    det += 1
        log(f"  held-out clip recall: {det}/{len(Xtest)} = {det/len(Xtest):.3f}")

    # 9. Export
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_onnx(net, (16, 96), out_path, class_mapping="hey_nexi")
    log(f"exported model -> {out_path}")
    log("")
    log("========== Training Complete ==========")
    log("Set in .env:")
    log(f"  OPENWAKEWORD_MODEL_PATH={out_path}")
    log(f"  OPENWAKEWORD_PHRASES=hey_nexi")
    log(f"  OPENWAKEWORD_SCORE_THRESHOLD={best_thr:.2f}")
    datasources = ["TTS"]
    if recorded_dir.is_dir() and list(recorded_dir.glob("*.wav")):
        datasources.append("real recordings")
    if args.download_sc:
        datasources.append("Speech Commands")
    if args.augment:
        datasources.append("augmented")
    log(f"  data sources: {', '.join(datasources)}")


if __name__ == "__main__":
    main()
