from __future__ import annotations

import argparse
import wave
from pathlib import Path


def _read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as wf:
        return wf.readframes(wf.getnframes())


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate current RMS clap detector over WAV folders.")
    parser.add_argument("--dataset", default="data/clap_dataset")
    args = parser.parse_args()

    from engine.clap_detector import ClapStateMachine

    root = Path(args.dataset)
    positives = list((root / "clap").glob("*.wav")) + list((root / "double_clap").glob("*.wav"))
    negatives = list((root / "negative").glob("*.wav"))
    tp = fp = fn = tn = 0
    for path in positives:
        sm = ClapStateMachine()
        hit = sm.process_frame(_read_wav(path)).get("clap", False)
        tp += int(hit)
        fn += int(not hit)
    for path in negatives:
        sm = ClapStateMachine()
        hit = sm.process_frame(_read_wav(path)).get("clap", False)
        fp += int(hit)
        tn += int(not hit)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)
    print(f"precision={precision:.3f} recall={recall:.3f} tp={tp} fp={fp} fn={fn} tn={tn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
