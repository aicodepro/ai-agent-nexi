"""Train a custom "hey nexi" OpenWakeWord model.

Self-contained pipeline (no reliance on openwakeword.train's __main__, whose
piper integration expects an older piper-sample-generator API):

  1. Synthesize positive ("hey nexi") and negative clips with piper-sample-generator.
  2. Pad/time-shift each clip to a fixed 2.0s window (32000 samples @ 16 kHz),
     which OpenWakeWord's feature extractor turns into exactly one (16, 96) example.
  3. Compute embedding features via openwakeword.utils.AudioFeatures.
  4. Train OpenWakeWord's FCN classifier head (so the exported ONNX is loadable
     by openwakeword.model.Model at inference time).
  5. Export hey_nexi.onnx and report a suggested detection threshold.

Usage (from the nexi project root, using the project venv):
  .venv/Scripts/python.exe training/train_hey_nexi.py \
      --n-positive 400 --n-negative 600 --epochs 120

Outputs:
  models/hey_nexi.onnx          (the trained wake model)
  training/_work/                (intermediate clips + features; safe to delete)
"""

import argparse
import os
import sys
import math
import random
from pathlib import Path

import numpy as np

THIS_DIR = Path(__file__).resolve().parent
NEXI_ROOT = THIS_DIR.parent
PIPER_REPO = THIS_DIR / "piper-sample-generator"
PIPER_MODEL = PIPER_REPO / "models" / "en_US-libritts_r-medium.pt"

SAMPLE_RATE = 16000
CLIP_SAMPLES = 32000          # 2.0s -> exactly one (16, 96) feature window
TEST_CLIP_SAMPLES = 48000     # 3.0s clips for sliding-window recall checks

# A diverse negative phrase set: common words, sentences, and phonetic
# near-misses to "hey nexi" so the model learns to reject similar sounds.
NEGATIVE_PHRASES = [
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
    "hey", "nexi pizza no thanks", "next time", "necks", "knicks", "essex",
    "complexity", "reflexes", "vortex", "context", "index", "annex",
    "she sells sea shells", "the quick brown fox", "thank you very much",
    "i would like a coffee", "open my email", "stop the alarm",
]


def log(msg):
    print(f"[TRAIN] {msg}", flush=True)


def build_net(input_shape=(16, 96), layer_dim=128, n_blocks=1):
    """Replica of OpenWakeWord's reference FCN head (openwakeword.train.Model,
    model_type='dnn'). Defined locally to avoid importing openwakeword.train,
    whose import chain (openwakeword.data -> acoustics) is broken against
    current scipy. The exported ONNX is identical in shape/semantics, so
    openwakeword.model.Model loads it normally at inference time.
    """
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
    """Export exactly as openwakeword.train.Model.export_to_onnx does."""
    import torch
    net = net.to("cpu")
    net.eval()
    # dynamo=False uses the legacy TorchScript exporter (no onnxscript dep) and
    # produces the classic ONNX format that openwakeword.model.Model expects.
    try:
        torch.onnx.export(net, torch.rand(input_shape)[None, ], str(out_path),
                          output_names=[class_mapping], dynamo=False)
    except TypeError:
        # older torch without the dynamo kwarg
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
    """Synthesize `n` clips of `text` into out_dir using piper-sample-generator."""
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
        noise_scales=(0.667,),
        noise_scale_ws=(0.8,),
        slerp_weights=(0.3, 0.5, 0.7),
        verbose=False,
    )
    log(f"  generated {len(list(out_dir.glob('*.wav')))} clips in {out_dir.name}/")


def load_wav_16k(path):
    """Load a wav as float32 mono @ 16 kHz."""
    import librosa
    y, _ = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    return y.astype(np.float32)


def to_int16_window(y, total_samples, offset=None, rng=None):
    """Place `y` into a zero-padded window of `total_samples` and return int16."""
    y = y[:total_samples]
    win = np.zeros(total_samples, dtype=np.float32)
    pad = total_samples - len(y)
    if offset is None:
        offset = (rng.randint(0, pad) if (rng and pad > 0) else max(pad, 0))
    offset = max(0, min(offset, max(pad, 0)))
    win[offset:offset + len(y)] = y
    return (np.clip(win, -1.0, 1.0) * 32767).astype(np.int16)


def build_examples(wav_paths, total_samples, shifts, rng):
    """Turn wavs into fixed-length int16 windows (with random time shifts)."""
    clips = []
    for p in wav_paths:
        try:
            y = load_wav_16k(p)
        except Exception:
            continue
        if len(y) < 800:  # skip near-empty
            continue
        for _ in range(shifts):
            clips.append(to_int16_window(y, total_samples, rng=rng))
    return clips


def embed(clips, ncpu):
    """Compute (N, 16, 96) embedding features for a list of int16 windows."""
    from openwakeword.utils import AudioFeatures
    af = AudioFeatures(ncpu=ncpu)
    X = af.embed_clips(np.stack(clips), batch_size=128, ncpu=ncpu)
    return X.astype(np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrase", default="hey nexi")
    ap.add_argument("--n-positive", type=int, default=400)
    ap.add_argument("--n-negative", type=int, default=600)
    ap.add_argument("--pos-shifts", type=int, default=3,
                    help="time-shifted variants per positive clip")
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--batch-size", type=int, default=256)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--tts-batch", type=int, default=16)
    ap.add_argument("--ncpu", type=int, default=max(1, (os.cpu_count() or 4) - 2))
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--out", default=str(NEXI_ROOT / "models" / "hey_nexi.onnx"))
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)
    rng = random.Random(args.seed)

    ensure_piper()
    work = THIS_DIR / "_work"
    pos_dir = work / "positive"
    neg_dir = work / "negative"

    # 1. Synthesize clips
    log(f"synthesizing positives ('{args.phrase}') ...")
    generate_clips(args.phrase, pos_dir, args.n_positive, args.tts_batch,
                   length_scales=(0.7, 0.85, 1.0, 1.15, 1.3))
    log("synthesizing negatives ...")
    # spread negative phrases across the requested count
    neg_existing = list(neg_dir.glob("*.wav"))
    if len(neg_existing) < int(0.95 * args.n_negative):
        from piper_sample_generator.__main__ import generate_samples
        neg_dir.mkdir(parents=True, exist_ok=True)
        per = max(1, args.n_negative // len(NEGATIVE_PHRASES))
        idx = 0
        for phrase in NEGATIVE_PHRASES:
            generate_samples(
                text=phrase, output_dir=str(neg_dir), model=str(PIPER_MODEL),
                max_samples=per, batch_size=args.tts_batch,
                length_scales=(0.85, 1.0, 1.15), noise_scales=(0.667,),
                noise_scale_ws=(0.8,), slerp_weights=(0.4, 0.6),
                file_names=[f"neg_{idx + k:05d}.wav" for k in range(per)],
            )
            idx += per
        log(f"  generated {len(list(neg_dir.glob('*.wav')))} negative clips")
    else:
        log(f"  reuse {len(neg_existing)} negative clips")

    pos_wavs = sorted(pos_dir.glob("*.wav"))
    neg_wavs = sorted(neg_dir.glob("*.wav"))
    log(f"clips: {len(pos_wavs)} positive, {len(neg_wavs)} negative")
    if not pos_wavs or not neg_wavs:
        log("ERROR: no clips generated; aborting")
        sys.exit(1)

    # hold out some positives as full-length test clips for recall
    rng.shuffle(pos_wavs)
    n_test = max(10, len(pos_wavs) // 10)
    test_pos_wavs, train_pos_wavs = pos_wavs[:n_test], pos_wavs[n_test:]

    # 2-3. Build features
    log("building features (this is the slow part) ...")
    pos_clips = build_examples(train_pos_wavs, CLIP_SAMPLES, args.pos_shifts, rng)
    neg_clips = build_examples(neg_wavs, CLIP_SAMPLES, 1, rng)
    log(f"  embedding {len(pos_clips)} positive + {len(neg_clips)} negative windows")
    Xp = embed(pos_clips, args.ncpu)
    Xn = embed(neg_clips, args.ncpu)
    X = np.concatenate([Xp, Xn], axis=0)
    y = np.concatenate([np.ones(len(Xp)), np.zeros(len(Xn))]).astype(np.float32)
    log(f"  feature matrix: X={X.shape} y={y.shape} (pos={int(y.sum())})")

    # test clip features (3s -> multiple frames for sliding-window recall)
    test_clips = build_examples(test_pos_wavs, TEST_CLIP_SAMPLES, 1, rng)
    Xtest = embed(test_clips, args.ncpu) if test_clips else None

    # 4. Train
    import torch
    from torch.utils.data import TensorDataset, DataLoader

    # shuffle + split
    perm = np.random.permutation(len(X))
    X, y = X[perm], y[perm]
    n_val = max(1, int(0.1 * len(X)))
    Xv, yv = X[:n_val], y[:n_val]
    Xt, yt = X[n_val:], y[n_val:]

    net = build_net(input_shape=(16, 96), layer_dim=128, n_blocks=1)
    device = torch.device("cpu")
    net.to(device)

    # positive class weight to balance pos/neg imbalance
    n_pos, n_neg = int(yt.sum()), int(len(yt) - yt.sum())
    pos_weight = max(1.0, n_neg / max(1, n_pos))
    log(f"training: {len(Xt)} train / {len(Xv)} val, pos_weight={pos_weight:.2f}")

    ds = TensorDataset(torch.from_numpy(Xt), torch.from_numpy(yt))
    dl = DataLoader(ds, batch_size=args.batch_size, shuffle=True)
    opt = torch.optim.Adam(net.parameters(), lr=args.lr)

    Xv_t = torch.from_numpy(Xv).to(device)
    yv_t = torch.from_numpy(yv).to(device)

    best_state, best_score = None, -1.0
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

        if (epoch + 1) % 10 == 0 or epoch == args.epochs - 1:
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
            if score >= best_score:
                best_score = score
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
            log(f"  epoch {epoch+1:3d}/{args.epochs}  recall={recall:.3f} precision={prec:.3f}")

    if best_state is not None:
        net.load_state_dict(best_state)

    # 5. Threshold suggestion + recall on full test clips
    net.eval()
    with torch.no_grad():
        pv = net(Xv_t).squeeze(-1).cpu().numpy()
    yv_np = yv_t.cpu().numpy()
    best_thr, best_f1 = 0.5, -1.0
    for thr in np.linspace(0.1, 0.9, 17):
        pred = (pv >= thr).astype(np.float32)
        tp = float(((pred == 1) & (yv_np == 1)).sum())
        fp = float(((pred == 1) & (yv_np == 0)).sum())
        fn = float(((pred == 0) & (yv_np == 1)).sum())
        f1 = tp / max(1.0, tp + 0.5 * (fp + fn))
        if f1 > best_f1:
            best_f1, best_thr = f1, float(thr)
    log(f"suggested OPENWAKEWORD_SCORE_THRESHOLD={best_thr:.2f} (val f1={best_f1:.3f})")

    if Xtest is not None and len(Xtest):
        with torch.no_grad():
            det = 0
            for clip in Xtest:  # (frames, 96)
                wins = np.stack([clip[i:i + 16] for i in range(0, clip.shape[0] - 16 + 1)])
                preds = net(torch.from_numpy(wins.astype(np.float32))).squeeze(-1).numpy()
                if (preds >= best_thr).any():
                    det += 1
        log(f"held-out clip recall: {det}/{len(Xtest)} = {det/len(Xtest):.3f}")

    # 6. Export ONNX
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    export_onnx(net, (16, 96), out_path, class_mapping="hey_nexi")
    log(f"exported model -> {out_path}")
    log("done. Set in .env:")
    log(f"  OPENWAKEWORD_MODEL_PATH={out_path}")
    log(f"  OPENWAKEWORD_PHRASES=hey_nexi")
    log(f"  OPENWAKEWORD_SCORE_THRESHOLD={best_thr:.2f}")


if __name__ == "__main__":
    main()
