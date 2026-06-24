#!/usr/bin/env python3
"""Train custom openWakeWord hotword model from user-collected voice samples.

Trains a small DNN classifier on openWakeWord embeddings computed from
collected positive (Hey Nexi, Nexi) and negative (speech, noise,
similar words, keyboard taps) audio clips.

Output: datasets/hotword/custom_hotword.onnx + metadata
"""

import argparse
import os
import sys
import json
import glob
import warnings

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from tqdm import tqdm

warnings.filterwarnings("ignore", category=UserWarning, module="torch")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SAMPLE_RATE = 16000
CLIP_LENGTH_SAMPLES = 32000  # 2 seconds
N_FRAMES = 16
N_MELS = 96
INPUT_SHAPE = (N_FRAMES, N_MELS)
HIDDEN_DIM = 128
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "hotword")
OUTPUT_DIR = os.path.join(BASE_DIR, "models")


def load_wav_files(directory: str) -> list[np.ndarray]:
    """Load all WAV files from directory as 16kHz mono numpy arrays."""
    import wave
    clips = []
    files = sorted(glob.glob(os.path.join(directory, "*.wav")))
    for fpath in files:
        try:
            with wave.open(fpath, "rb") as wf:
                assert wf.getnchannels() == 1, "Not mono"
                assert wf.getframerate() == SAMPLE_RATE, "Not 16kHz"
                frames = wf.readframes(wf.getnframes())
                audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32)
                if len(audio) == 0:
                    continue
                clips.append(audio)
        except Exception as exc:
            print(f"    WARN: could not load {os.path.basename(fpath)}: {exc}")
    return clips


def pad_or_truncate(clips: list[np.ndarray], target_len: int) -> np.ndarray:
    """Pad or truncate all clips to target length."""
    out = np.zeros((len(clips), target_len), dtype=np.float32)
    for i, clip in enumerate(clips):
        if len(clip) >= target_len:
            out[i] = clip[:target_len]
        else:
            out[i, :len(clip)] = clip
    return out


def compute_features(audio_batch: np.ndarray) -> np.ndarray:
    """Compute openWakeWord embeddings for batched audio.

    Args:
        audio_batch: (N, samples) int16 array at 16kHz
    Returns:
        (N, frames, 96) float32 features
    """
    from openwakeword.utils import AudioFeatures
    af = AudioFeatures(device="cpu", ncpu=1)
    audio_int16 = audio_batch.astype(np.int16)
    features = af.embed_clips(audio_int16, batch_size=min(32, len(audio_int16)))
    return features.astype(np.float32)


def augment_clip(clip: np.ndarray) -> np.ndarray:
    """Apply random augmentation to a single audio clip."""
    import random
    if random.random() < 0.3:
        gain = random.uniform(0.5, 1.0)
        clip = clip * gain
    if random.random() < 0.3:
        noise = np.random.randn(len(clip)).astype(np.float32) * random.uniform(0.001, 0.01)
        clip = clip + noise
    return clip


def augment_batch(audio_batch: np.ndarray, n_augmented: int) -> np.ndarray:
    """Create augmented copies of audio clips."""
    augmented = []
    for _ in range(n_augmented):
        idx = np.random.randint(0, len(audio_batch))
        aug = augment_clip(audio_batch[idx].copy())
        augmented.append(aug)
    if augmented:
        return np.vstack([audio_batch, np.array(augmented)])
    return audio_batch


def build_clf(input_dim: int = N_FRAMES * N_MELS,
              hidden_dim: int = HIDDEN_DIM) -> nn.Module:
    """Build small DNN classifier matching openWakeWord architecture."""
    return nn.Sequential(
        nn.Flatten(),
        nn.Linear(input_dim, hidden_dim),
        nn.LayerNorm(hidden_dim),
        nn.ReLU(),
        nn.Linear(hidden_dim, hidden_dim),
        nn.LayerNorm(hidden_dim),
        nn.ReLU(),
        nn.Linear(hidden_dim, 1),
        nn.Sigmoid(),
    )


def export_to_onnx(model: nn.Module, output_path: str):
    """Export PyTorch model to ONNX format compatible with openWakeWord."""
    model.eval()
    dummy = torch.randn(1, N_FRAMES, N_MELS)
    model.to("cpu")
    with torch.no_grad():
        torch.onnx.export(
            model,
            dummy,
            output_path,
            input_names=["x.1"],
            output_names=["score"],
            dynamic_axes={"x.1": {0: "batch"}, "score": {0: "batch"}},
            opset_version=18,
        )


def main():
    parser = argparse.ArgumentParser(description="Train custom hotword model")
    parser.add_argument("--positive-dirs", nargs="*", default=[],
                        help="Override positive WAV directories")
    parser.add_argument("--negative-dirs", nargs="*", default=[],
                        help="Override negative WAV directories")
    parser.add_argument("--epochs", type=int, default=200,
                        help="Training epochs (default: 200)")
    parser.add_argument("--lr", type=float, default=0.001,
                        help="Learning rate (default: 0.001)")
    parser.add_argument("--weight-decay", type=float, default=0.01,
                        help="Weight decay (default: 0.01)")
    parser.add_argument("--val-split", type=float, default=0.2,
                        help="Validation split ratio (default: 0.2)")
    parser.add_argument("--augment-multiplier", type=int, default=3,
                        help="Data augmentation multiplier (default: 3)")
    parser.add_argument("--threshold-search", action="store_true",
                        help="Search for optimal threshold on validation set")
    parser.add_argument("--model-name", type=str, default="custom_hotword",
                        help="Output model name (default: custom_hotword)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: 5 epochs, no aug, minimal data")
    args = parser.parse_args()

    # Build directories to scan
    positive_dirs = args.positive_dirs or [
        os.path.join(BASE_DIR, "positive", d)
        for d in ["hey_nexi", "nexi", "variants"]
    ]
    negative_dirs = args.negative_dirs or [
        os.path.join(BASE_DIR, "negative", d)
        for d in ["speech", "noise", "similar_words", "keyboard_taps"]
    ]

    print("=" * 60)
    print("HOTWORD MODEL TRAINING")
    print("=" * 60)
    print(f"Device: {DEVICE}")
    print()

    # --- Load audio ---
    print("[1/5] Loading audio clips...")
    positive_clips = []
    for d in positive_dirs:
        if os.path.isdir(d):
            clips = load_wav_files(d)
            positive_clips.extend(clips)
            print(f"  {os.path.basename(d)}: {len(clips)} clips")
    negative_clips = []
    for d in negative_dirs:
        if os.path.isdir(d):
            clips = load_wav_files(d)
            negative_clips.extend(clips)
            print(f"  {os.path.basename(d)}: {len(clips)} clips")

    if not positive_clips:
        print("ERROR: No positive clips found. Run collect_hotword_training_data.py first.")
        sys.exit(1)
    if not negative_clips:
        print("WARNING: No negative clips found. Training without negatives.")

    print(f"\n  Positive: {len(positive_clips)}, Negative: {len(negative_clips)}")
    print()

    # --- Data augmentation ---
    print("[2/5] Augmenting data...")
    if args.quick:
        aug_mult = 1
    else:
        aug_mult = args.augment_multiplier

    pos_padded = pad_or_truncate(positive_clips, CLIP_LENGTH_SAMPLES)
    neg_padded = pad_or_truncate(negative_clips, CLIP_LENGTH_SAMPLES) if negative_clips else np.empty((0, CLIP_LENGTH_SAMPLES))

    pos_aug = augment_batch(pos_padded, len(pos_padded) * (aug_mult - 1))
    neg_aug = augment_batch(neg_padded, len(neg_padded) * (aug_mult - 1)) if len(neg_padded) > 0 else neg_padded

    print(f"  After augmentation: {len(pos_aug)} positive, {len(neg_aug)} negative")
    print()

    # --- Compute features ---
    print("[3/5] Computing openWakeWord features...")
    all_audio = np.vstack([pos_aug, neg_aug]) if len(neg_aug) > 0 else pos_aug
    all_labels = np.hstack([
        np.ones(len(pos_aug)),
        np.zeros(len(neg_aug)),
    ])

    features = compute_features(all_audio)
    print(f"  Features shape: {features.shape}")
    print()

    # Slice features into N_FRAMES sliding windows
    n_windows = features.shape[1] - N_FRAMES + 1
    if n_windows < 1:
        print(f"ERROR: Features have {features.shape[1]} frames, need >= {N_FRAMES}")
        sys.exit(1)

    X_list, y_list = [], []
    for i in range(len(features)):
        for j in range(n_windows):
            X_list.append(features[i, j:j + N_FRAMES])
            y_list.append(all_labels[i])

    X = np.array(X_list)
    y = np.array(y_list)

    print(f"  Windowed: {X.shape[0]} examples (from {n_windows} windows each)")
    print(f"  Positive: {int(y.sum())}, Negative: {int(len(y) - y.sum())}")
    print()

    # --- Train/val split ---
    print("[4/5] Training classifier...")
    perm = np.random.RandomState(42).permutation(len(X))
    X, y = X[perm], y[perm]
    split = max(1, int(len(X) * (1 - args.val_split)))
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    print(f"  Train: {len(X_train)}, Val: {len(X_val)}")

    # Convert to tensors
    X_train_t = torch.from_numpy(X_train).float()
    y_train_t = torch.from_numpy(y_train).float().unsqueeze(1)
    X_val_t = torch.from_numpy(X_val).float()
    y_val_t = torch.from_numpy(y_val).float().unsqueeze(1)

    train_loader = DataLoader(
        TensorDataset(X_train_t, y_train_t),
        batch_size=64, shuffle=True
    )
    val_loader = DataLoader(
        TensorDataset(X_val_t, y_val_t),
        batch_size=256, shuffle=False
    )

    # Build model
    model = build_clf().to(DEVICE)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    loss_fn = nn.BCELoss()

    epochs = 5 if args.quick else args.epochs
    best_val_loss = float("inf")
    patience = 20
    no_improve = 0

    for epoch in range(epochs):
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        for Xb, yb in train_loader:
            Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
            optimizer.zero_grad()
            preds = model(Xb)
            loss = loss_fn(preds, yb)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            train_loss += loss.item() * len(Xb)
            train_correct += ((preds >= 0.5) == yb).sum().item()
            train_total += len(Xb)
        scheduler.step()

        # Validation
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0
        val_pos_correct = 0
        val_pos_total = 0
        val_neg_correct = 0
        val_neg_total = 0
        val_preds_list = []
        val_labels_list = []
        with torch.no_grad():
            for Xb, yb in val_loader:
                Xb, yb = Xb.to(DEVICE), yb.to(DEVICE)
                preds = model(Xb)
                loss = loss_fn(preds, yb)
                val_loss += loss.item() * len(Xb)
                correct = ((preds >= 0.5) == yb).sum().item()
                val_correct += correct
                val_total += len(Xb)
                val_preds_list.append(preds.cpu())
                val_labels_list.append(yb.cpu())
                for i in range(len(yb)):
                    if yb[i].item() == 1:
                        val_pos_total += 1
                        val_pos_correct += 1 if preds[i].item() >= 0.5 else 0
                    else:
                        val_neg_total += 1
                        val_neg_correct += 1 if preds[i].item() < 0.5 else 0

        train_acc = train_correct / train_total if train_total > 0 else 0
        val_acc = val_correct / val_total if val_total > 0 else 0
        val_pos_acc = val_pos_correct / val_pos_total if val_pos_total > 0 else 0
        val_neg_acc = val_neg_correct / val_neg_total if val_neg_total > 0 else 0

        if (epoch + 1) % 20 == 0 or epoch == 0 or epoch == epochs - 1:
            print(f"  Epoch {epoch + 1:3d}/{epochs} | "
                  f"Train loss: {train_loss / train_total:.4f} acc: {train_acc:.3f} | "
                  f"Val loss: {val_loss / val_total:.4f} acc: {val_acc:.3f} "
                  f"(pos: {val_pos_acc:.3f} neg: {val_neg_acc:.3f})")

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            no_improve = 0
            torch.save(model.state_dict(), os.path.join(BASE_DIR, "best_model.pt"))
        else:
            no_improve += 1
            if no_improve >= patience:
                print(f"  Early stopping at epoch {epoch + 1}")
                model.load_state_dict(torch.load(os.path.join(BASE_DIR, "best_model.pt")))
                break

    print(f"\n  Best val loss: {best_val_loss:.4f}")
    print()

    # Threshold search
    if args.threshold_search:
        print("  Searching optimal threshold...")
        all_preds = torch.cat(val_preds_list).numpy().flatten()
        all_labels_np = torch.cat(val_labels_list).numpy().flatten()
        best_thresh = 0.5
        best_f1 = 0
        for thresh in np.linspace(0.05, 0.95, 19):
            tp = ((all_preds >= thresh) & (all_labels_np == 1)).sum()
            fp = ((all_preds >= thresh) & (all_labels_np == 0)).sum()
            fn = ((all_preds < thresh) & (all_labels_np == 1)).sum()
            precision = tp / (tp + fp) if (tp + fp) > 0 else 0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0
            f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
            if f1 > best_f1:
                best_f1 = f1
                best_thresh = thresh
        print(f"  Optimal threshold: {best_thresh:.2f} (F1: {best_f1:.3f})")
        print()

    # --- Export to ONNX ---
    print("[5/5] Exporting model...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    onnx_path = os.path.join(OUTPUT_DIR, f"{args.model_name}.onnx")
    export_to_onnx(model, onnx_path)
    print(f"  ONNX model saved: {onnx_path}")
    print()

    # --- Summary ---
    model.eval()
    with torch.no_grad():
        val_preds_all = torch.cat(val_preds_list).numpy().flatten()
        val_labels_all = torch.cat(val_labels_list).numpy().flatten()

    thresh = 0.35  # default openWakeWord threshold
    tp = ((val_preds_all >= thresh) & (val_labels_all == 1)).sum()
    fp = ((val_preds_all >= thresh) & (val_labels_all == 0)).sum()
    fn = ((val_preds_all < thresh) & (val_labels_all == 1)).sum()
    tn = ((val_preds_all < thresh) & (val_labels_all == 0)).sum()

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    accuracy = (tp + tn) / (tp + tn + fp + fn) if (tp + tn + fp + fn) > 0 else 0

    print("=" * 60)
    print("TRAINING SUMMARY")
    print("=" * 60)
    print(f"  Model: {args.model_name}")
    print(f"  Training samples: {len(X_train)} (pos: {int(y_train.sum())}, neg: {int(len(y_train) - y_train.sum())})")
    print(f"  Validation samples: {len(X_val)} (pos: {int(y_val.sum())}, neg: {int(len(y_val) - y_val.sum())})")
    print(f"  Epochs: {epochs}")
    print(f"  Best val loss: {best_val_loss:.4f}")
    print()
    print(f"  Validation at threshold={thresh}:")
    print(f"    Accuracy:  {accuracy:.3f}")
    print(f"    Precision: {precision:.3f}")
    print(f"    Recall:    {recall:.3f}")
    print(f"    F1 Score:  {f1:.3f}")
    print(f"    TP: {int(tp)}  FP: {int(fp)}  TN: {int(tn)}  FN: {int(fn)}")
    print()
    print(f"  Model path: {onnx_path}")
    print(f"  Recommended OPENWAKEWORD_MODEL_PATH={onnx_path}")
    print()
    print("  Next step: python scripts/validate_hotword_model.py")

    # Save metadata
    metadata = {
        "model_name": args.model_name,
        "input_shape": list(INPUT_SHAPE),
        "sample_rate": SAMPLE_RATE,
        "recommended_threshold": thresh,
        "val_accuracy": float(accuracy),
        "val_precision": float(precision),
        "val_recall": float(recall),
        "val_f1": float(f1),
        "n_train": len(X_train),
        "n_val": len(X_val),
        "n_pos_train": int(y_train.sum()),
        "n_neg_train": int(len(y_train) - y_train.sum()),
        "n_pos_val": int(y_val.sum()),
        "n_neg_val": int(len(y_val) - y_val.sum()),
    }
    with open(os.path.join(OUTPUT_DIR, f"{args.model_name}_metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"  Metadata: {os.path.join(OUTPUT_DIR, f'{args.model_name}_metadata.json')}")


if __name__ == "__main__":
    main()
