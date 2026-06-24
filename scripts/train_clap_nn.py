#!/usr/bin/env python3
"""Train the CLAP_NN AudioClassifier model from dataset.

Uses manual mel spectrogram computation (matching the inference backend)
so no torchaudio or torchvision is required.

Training data layout (datasets/clap_nn/):
  train/clap/         — clap samples (label=1)
  train/not_clap/     — not-clap samples (label=0)
  val/clap/
  val/not_clap/

Output:
  external/CLAP_NN/ASSETS/CLAP_DETECTS/MODELS/Clap_Detect_Model.pth
"""

import argparse
import math
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _load_model_class():
    """Import AudioClassifier from the CLAP_NN extracted source."""
    model_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "external", "CLAP_NN_INSPECT", "CLAP_NN"
    )
    if model_dir not in sys.path:
        sys.path.insert(0, model_dir)
    from cnn_sound_model import AudioClassifier
    return AudioClassifier


def _load_wav(filepath: str, target_sr: int = 44100) -> np.ndarray:
    """Load a WAV file and resample to target_sr if needed.
    Uses scipy (no torchaudio dependency).
    """
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
    """Mel filterbank matrix: (n_mels, n_fft//2+1)."""
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


def _audio_to_mel_spec(waveform: np.ndarray, sr: int, n_fft: int,
                       hop_length: int, n_mels: int, target_size: int) -> np.ndarray:
    """Convert waveform to normalized mel spectrogram (1, 256, 256)."""
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


def load_dataset(train_dir: str, val_dir: str = "", sr: int = 44100,
                 n_fft: int = 400, hop_length: int = 200,
                 n_mels: int = 128, target_size: int = 256) -> tuple:
    """Load WAV files from datasets/clap_nn structure.
    
    Args:
        train_dir: base directory with train/clap/ and train/not_clap/
        val_dir: base directory with val/clap/ and val/not_clap/
    
    Returns (train_specs, train_labels, val_specs, val_labels) as numpy arrays.
    """
    def get_wav_files(directory: str) -> list:
        if not os.path.isdir(directory):
            return []
        return sorted([
            os.path.join(directory, f) for f in os.listdir(directory)
            if f.endswith(".wav")
        ])

    def load_and_spec(fpath, label):
        try:
            wf = _load_wav(fpath, sr)
            spec = _audio_to_mel_spec(wf, sr, n_fft, hop_length, n_mels, target_size)
            return spec, label
        except Exception as e:
            print(f"[WARN] skipping {fpath}: {type(e).__name__}: {e}")
            return None

    def build_dataset(base_dir, name):
        clap_files = get_wav_files(os.path.join(base_dir, "clap"))
        not_clap_files = get_wav_files(os.path.join(base_dir, "not_clap"))
        specs = []
        labels = []
        for fpath in clap_files:
            r = load_and_spec(fpath, 1)
            if r: specs.append(r[0]); labels.append(r[1])
        for fpath in not_clap_files:
            r = load_and_spec(fpath, 0)
            if r: specs.append(r[0]); labels.append(r[1])
        print(f"[DATA] {name}: clap={len(clap_files)} not_clap={len(not_clap_files)} total_valid={len(specs)}")
        if not specs:
            return np.empty((0, 1, target_size, target_size), dtype=np.float32), np.empty(0, dtype=np.int64)
        return np.array(specs, dtype=np.float32), np.array(labels, dtype=np.int64)

    train_specs, train_labels = build_dataset(train_dir, "train")
    val_specs, val_labels = np.empty((0, 1, target_size, target_size), dtype=np.float32), np.empty(0, dtype=np.int64)
    if val_dir:
        val_specs, val_labels = build_dataset(val_dir, "val")

    if len(train_specs) == 0:
        print("[ERROR] No valid training samples.")
        sys.exit(1)
    return train_specs, train_labels, val_specs, val_labels


def main():
    parser = argparse.ArgumentParser(description="Train CLAP_NN model from dataset")
    parser.add_argument("--train-dir", type=str, default="",
                        help="Training base dir (default: datasets/clap_nn/train)")
    parser.add_argument("--val-dir", type=str, default="",
                        help="Validation base dir (default: datasets/clap_nn/val)")
    parser.add_argument("--output", type=str, default="",
                        help="Output model path (default: external/CLAP_NN/.../Clap_Detect_Model.pth)")
    parser.add_argument("--epochs", type=int, default=20, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size")
    parser.add_argument("--lr", type=float, default=1e-5, help="Learning rate")
    parser.add_argument("--weight-decay", type=float, default=0.02, help="Weight decay")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--n-mels", type=int, default=128, help="Number of mel bands")
    parser.add_argument("--n-fft", type=int, default=400, help="FFT size")
    parser.add_argument("--hop-length", type=int, default=200, help="Hop length")
    parser.add_argument("--target-size", type=int, default=256, help="Target spectrogram size")
    parser.add_argument("--sample-rate", type=int, default=44100, help="Model sample rate")
    args = parser.parse_args()

    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    torch.manual_seed(args.seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[TRAIN] device={device}")

    # Resolve paths
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    train_dir = args.train_dir or os.path.join(base, "datasets", "clap_nn", "train")
    val_dir = args.val_dir or os.path.join(base, "datasets", "clap_nn", "val")

    # Resolve output path
    output_path = args.output
    if not output_path:
        output_path = os.path.join(base, "external", "CLAP_NN",
                                    "ASSETS", "CLAP_DETECTS", "MODELS", "Clap_Detect_Model.pth")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    print(f"[TRAIN] output={output_path}")

    # Load dataset
    print("[TRAIN] Loading dataset...")
    train_specs, train_labels, val_specs, val_labels = load_dataset(
        train_dir, val_dir,
        sr=args.sample_rate,
        n_fft=args.n_fft,
        hop_length=args.hop_length,
        n_mels=args.n_mels,
        target_size=args.target_size,
    )

    # Create datasets
    train_ds = TensorDataset(torch.from_numpy(train_specs), torch.from_numpy(train_labels))
    train_loader = DataLoader(train_ds, batch_size=args.batch_size, shuffle=True)
    print(f"[TRAIN] train={len(train_ds)}")
    val_loader = None
    if len(val_specs) > 0:
        val_ds = TensorDataset(torch.from_numpy(val_specs), torch.from_numpy(val_labels))
        val_loader = DataLoader(val_ds, batch_size=args.batch_size, shuffle=False)
        print(f"[TRAIN] val={len(val_ds)}")

    # Create model
    AudioClassifier = _load_model_class()
    model = AudioClassifier().to(device)
    print(f"[TRAIN] model params={sum(p.numel() for p in model.parameters())}")

    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)

    # Training loop
    print(f"[TRAIN] Training for {args.epochs} epochs...")
    start_time = time.time()
    best_val_acc = 0.0

    for epoch in range(args.epochs):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        for inputs, lbls in train_loader:
            inputs, lbls = inputs.to(device), lbls.to(device)
            optimizer.zero_grad()
            outputs = model(inputs)
            loss = criterion(outputs, lbls)
            loss.backward()
            optimizer.step()
            train_loss += loss.item()
            _, predicted = torch.max(outputs, 1)
            train_total += lbls.size(0)
            train_correct += (predicted == lbls).sum().item()
        train_acc = train_correct / train_total
        train_loss_avg = train_loss / len(train_loader)

        # Validate
        val_loss_avg = 0.0
        val_acc = 0.0
        if val_loader is not None:
            model.eval()
            val_loss = 0.0
            val_correct = 0
            val_total = 0
            with torch.no_grad():
                for inputs, lbls in val_loader:
                    inputs, lbls = inputs.to(device), lbls.to(device)
                    outputs = model(inputs)
                    loss = criterion(outputs, lbls)
                    val_loss += loss.item()
                    _, predicted = torch.max(outputs, 1)
                    val_total += lbls.size(0)
                    val_correct += (predicted == lbls).sum().item()
            val_acc = val_correct / val_total
            val_loss_avg = val_loss / len(val_loader)
            if val_acc > best_val_acc:
                best_val_acc = val_acc

        elapsed = time.time() - start_time
        val_str = f"val_loss={val_loss_avg:.4f} val_acc={val_acc:.4f} best_val_acc={best_val_acc:.4f}" if val_loader else "no_val"
        print(f"  Epoch {epoch+1:3d}/{args.epochs} | "
              f"train_loss={train_loss_avg:.4f} train_acc={train_acc:.4f} | "
              f"{val_str} | {elapsed:.0f}s")

    # Save model
    torch.save(model.state_dict(), output_path)
    size_kb = os.path.getsize(output_path) / 1024
    print(f"\n[TRAIN] Model saved to: {output_path}")
    print(f"[TRAIN] Size: {size_kb:.1f} KB")
    print(f"[TRAIN] Best validation accuracy: {best_val_acc:.4f}")

    if best_val_acc >= 0.95:
        print("[TRAIN] Quality: EXCELLENT")
    elif best_val_acc >= 0.90:
        print("[TRAIN] Quality: GOOD (consider more data)")
    elif best_val_acc >= 0.80:
        print("[TRAIN] Quality: ACCEPTABLE (needs more data)")
    else:
        print("[TRAIN] Quality: POOR (collect more data and re-train)")

    print()
    print("Next step: python scripts/validate_clap_nn_model.py --test-dir datasets/clap_nn/test")


if __name__ == "__main__":
    main()
