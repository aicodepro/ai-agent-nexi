from __future__ import annotations

import argparse
import wave
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Record short clap dataset WAV clips.")
    parser.add_argument("--label", choices=["clap", "double_clap", "negative"], required=True)
    parser.add_argument("--out", default="data/clap_dataset")
    parser.add_argument("--seconds", type=float, default=2.0)
    args = parser.parse_args()

    import sounddevice as sd
    import numpy as np

    sample_rate = 16000
    frames = int(sample_rate * args.seconds)
    print(f"Recording {args.label} for {args.seconds}s...")
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="int16")
    sd.wait()

    out_dir = Path(args.out) / args.label
    out_dir.mkdir(parents=True, exist_ok=True)
    index = len(list(out_dir.glob("*.wav"))) + 1
    target = out_dir / f"{args.label}_{index:04d}.wav"
    with wave.open(str(target), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(np.asarray(audio).tobytes())
    print(f"Saved {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
