#!/usr/bin/env python3
"""Collect labeled WAV training data for CLAP_NN model.

Collects:
  - 100 single claps
  - 100 double claps
  - 100 "Hey Nexi" speech samples
  - 100 "Nexi" speech samples
  - 100 random speech/noise samples
  - 60 seconds silence
  - keyboard/mouse/tap sounds (optional)

Organizes into:
  scripts/training_data/claps/       — clap samples (label=1)
  scripts/training_data/noise/       — noise/speech/silence samples (label=0)
"""

import argparse
import os
import sys
import time
import wave
from datetime import datetime

import numpy as np

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = np.int16
RECORD_SECONDS = 2.0


def ensure_dir(path: str) -> str:
    os.makedirs(path, exist_ok=True)
    return path


def record_audio(duration_sec: float, device: int | None = None) -> np.ndarray:
    import sounddevice as sd
    frames = int(SAMPLE_RATE * duration_sec)
    recording = sd.rec(frames, samplerate=SAMPLE_RATE, channels=CHANNELS, dtype=DTYPE, device=device)
    sd.wait()
    return recording.squeeze()


def save_wav(filepath: str, audio: np.ndarray) -> None:
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    size_kb = os.path.getsize(filepath) / 1024
    print(f"    saved: {os.path.basename(filepath)} ({size_kb:.1f} KB)")


def collect_samples(category: str, count: int, clap_dirs: dict, device: int | None,
                    prompt_fn, duration: float = RECORD_SECONDS):
    clap_dir = clap_dirs["claps"]
    noise_dir = clap_dirs["noise"]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    for i in range(count):
        prompt_fn(i, count)
        time.sleep(0.3)
        audio = record_audio(duration, device)
        rms = (audio.astype(np.float64) ** 2).mean() ** 0.5
        if rms < 20:
            print(f"    WARNING: low amplitude ({rms:.1f}), re-recording...")
            audio = record_audio(duration, device)
            rms = (audio.astype(np.float64) ** 2).mean() ** 0.5
        if category == "clap" or category == "double_clap":
            fname = os.path.join(clap_dir, f"{category}_{timestamp}_{i+1:03d}.wav")
            save_wav(fname, audio)
        else:
            fname = os.path.join(noise_dir, f"{category}_{timestamp}_{i+1:03d}.wav")
            save_wav(fname, audio)


def main():
    parser = argparse.ArgumentParser(description="Collect CLAP_NN training data")
    parser.add_argument("--device", type=int, default=None, help="Input device index")
    parser.add_argument("--output", type=str, default="scripts/training_data",
                        help="Output directory (default: scripts/training_data)")
    parser.add_argument("--clap-count", type=int, default=100, help="Number of single claps (default: 100)")
    parser.add_argument("--double-clap-count", type=int, default=100, help="Number of double claps (default: 100)")
    parser.add_argument("--hey-nexi-count", type=int, default=100, help="Number of 'Hey Nexi' samples (default: 100)")
    parser.add_argument("--nexi-count", type=int, default=100, help="Number of 'Nexi' samples (default: 100)")
    parser.add_argument("--speech-count", type=int, default=100, help="Number of random speech/noise (default: 100)")
    parser.add_argument("--silence-seconds", type=float, default=60.0, help="Silence duration in seconds (default: 60)")
    args = parser.parse_args()

    clap_dir = ensure_dir(os.path.join(args.output, "claps"))
    noise_dir = ensure_dir(os.path.join(args.output, "noise"))
    clap_dirs = {"claps": clap_dir, "noise": noise_dir}

    print("=" * 60)
    print("CLAP_NN TRAINING DATA COLLECTION")
    print("=" * 60)
    print(f"Output directory: {os.path.abspath(args.output)}")
    print(f"Sample rate: {SAMPLE_RATE} Hz")
    print(f"Record duration: {RECORD_SECONDS}s per sample")
    print()

    # 1. Single claps
    print(f"[1] Collecting {args.clap_count} single claps")
    def prompt_single(i, total):
        input(f"  [{i+1}/{total}] Press Enter, then single clap...")
    collect_samples("clap", args.clap_count, clap_dirs, args.device, prompt_single)
    print()

    # 2. Double claps
    print(f"[2] Collecting {args.double_clap_count} double claps")
    def prompt_double(i, total):
        input(f"  [{i+1}/{total}] Press Enter, then double clap...")
    collect_samples("double_clap", args.double_clap_count, clap_dirs, args.device, prompt_double)
    print()

    # 3. "Hey Nexi"
    print(f"[3] Collecting {args.hey_nexi_count} 'Hey Nexi' samples")
    def prompt_hey(i, total):
        input(f"  [{i+1}/{total}] Press Enter, pause 1s, say 'Hey Nexi'...")
    collect_samples("hey_nexi", args.hey_nexi_count, clap_dirs, args.device, prompt_hey)
    print()

    # 4. "Nexi"
    print(f"[4] Collecting {args.nexi_count} 'Nexi' samples")
    def prompt_nexi(i, total):
        input(f"  [{i+1}/{total}] Press Enter, pause 1s, say 'Nexi'...")
    collect_samples("nexi", args.nexi_count, clap_dirs, args.device, prompt_nexi)
    print()

    # 5. Random speech/noise
    print(f"[5] Collecting {args.speech_count} random speech/noise samples")
    print("  Say random words, count numbers, hum, whistle, etc.")
    def prompt_speech(i, total):
        input(f"  [{i+1}/{total}] Press Enter, then make any sound for 2 seconds...")
    collect_samples("speech", args.speech_count, clap_dirs, args.device, prompt_speech)
    print()

    # 6. Silence
    print(f"[6] Collecting {args.silence_seconds:.0f} seconds of silence")
    input("  Press Enter, then stay completely quiet...")
    for remaining in range(int(args.silence_seconds), 0, -5):
        print(f"  ... {remaining}s")
        time.sleep(5)
    silence_audio = record_audio(args.silence_seconds, args.device)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    silence_path = os.path.join(noise_dir, f"silence_{timestamp}_{int(args.silence_seconds)}s.wav")
    save_wav(silence_path, silence_audio)
    print()

    # List collected files
    clap_files = [f for f in os.listdir(clap_dir) if f.endswith(".wav")]
    noise_files = [f for f in os.listdir(noise_dir) if f.endswith(".wav")]
    print("=" * 60)
    print("COLLECTION SUMMARY")
    print("=" * 60)
    print(f"  Clap samples (label=1):   {len(clap_files)} files in {clap_dir}")
    print(f"  Noise samples (label=0):  {len(noise_files)} files in {noise_dir}")
    print(f"  Total:                    {len(clap_files) + len(noise_files)} files")
    print()
    print("Next step: python scripts/train_clap_nn.py")


if __name__ == "__main__":
    main()
