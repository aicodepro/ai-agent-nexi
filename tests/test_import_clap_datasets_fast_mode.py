"""Test fast dataset mode: --use-esc50-only imports ESC-50 without other datasets."""

import os
import sys
import tempfile
import wave
import numpy as np


def _make_dummy_wav(path: str, sr: int = 44100, dur_sec: float = 2.0):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (np.random.randn(int(sr * dur_sec)) * 1000).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


def _make_fake_esc50(base: str):
    meta_dir = os.path.join(base, "meta")
    audio_dir = os.path.join(base, "audio")
    os.makedirs(audio_dir, exist_ok=True)

    rows = ["filename,fold,target,category"]
    for i in range(5):
        fname = f"1-{i+1:04d}-A-{i+1:02d}.wav"
        _make_dummy_wav(os.path.join(audio_dir, fname), 44100, 2.0)
        cls = 12 if i == 0 else 0  # one clap, four non-clap
        rows.append(f"{fname},{i+1},{cls},test_class_{i}")
    os.makedirs(meta_dir, exist_ok=True)
    with open(os.path.join(meta_dir, "esc50.csv"), "w") as f:
        f.write("\n".join(rows))


def test_use_esc50_only_flag_does_not_crash():
    """--use-esc50-only must not crash when other datasets are absent."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        esc50 = os.path.join(tmp, "ESC50")
        _make_fake_esc50(esc50)

        out = os.path.join(tmp, "clap_nn")
        orig_out = "datasets.clap_nn"
        # Monkey-patch OUTPUT_DIR
        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = out

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", esc50,
                        "--use-esc50-only",
                        "--speech-commands", os.path.join(tmp, "NOT_THERE"),
                        "--fsd50k", os.path.join(tmp, "NOT_THERE"),
                        "--urbansound8k", os.path.join(tmp, "NOT_THERE"),
                        "--freesound", os.path.join(tmp, "NOT_THERE"),
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out

        # Verify output was created
        manifest = os.path.join(out, "manifest.csv")
        assert os.path.isfile(manifest), f"Manifest not found at {manifest}"


def test_use_esc50_only_creates_clap_and_not_clap():
    """ESC-50 only mode must produce both clap and not_clap samples."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        esc50 = os.path.join(tmp, "ESC50")
        _make_fake_esc50(esc50)
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = out

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", esc50,
                        "--use-esc50-only",
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out

        train_clap = os.path.join(out, "train", "clap")
        train_not = os.path.join(out, "train", "not_clap")
        assert os.path.isdir(train_clap), f"No train/clap dir at {train_clap}"
        assert os.path.isdir(train_not), f"No train/not_clap dir at {train_not}"
        assert len(os.listdir(train_clap)) >= 3, "Not enough clap windows from 1 file"


def test_use_esc50_only_without_esc50_still_creates_dirs():
    """Using --use-esc50-only with no ESC-50 should still create output dirs."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = out

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", os.path.join(tmp, "MISSING_ESC50"),
                        "--use-esc50-only",
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out

        assert os.path.isdir(out)
