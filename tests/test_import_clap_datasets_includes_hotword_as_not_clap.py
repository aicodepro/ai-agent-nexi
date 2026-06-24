"""Test hotword recordings are imported as NOT_CLAP (never clap)."""

import os
import sys
import tempfile
import wave
import numpy as np


def _make_wav(path: str, sr: int = 44100, dur_sec: float = 0.6):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = (np.random.randn(int(sr * dur_sec)) * 3000).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data.tobytes())


def _make_minimal_esc50(base: str):
    meta_dir = os.path.join(base, "meta")
    audio_dir = os.path.join(base, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)
    rows = ["filename,fold,target,category"]
    for i in range(2):
        fname = f"1-{i+1:04d}-A-0{i+1}.wav"
        _make_wav(os.path.join(audio_dir, fname))
        cls = 12 if i == 0 else 0
        rows.append(f"{fname},{i+1},{cls},c{i}")
    with open(os.path.join(meta_dir, "esc50.csv"), "w") as f:
        f.write("\n".join(rows))


def _make_hotword_positive(base: str):
    for sub in ("hey_jarvis", "jarvis", "variants"):
        d = os.path.join(base, "positive", sub)
        _make_wav(os.path.join(d, f"{sub}_001.wav"))


def test_hotword_positives_go_to_not_clap():
    """Hey Jarvis, Jarvis, and variants must land in not_clap dir."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        esc50 = os.path.join(tmp, "ESC50")
        _make_minimal_esc50(esc50)
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        old_pos = mod.HOTWORD_POS_DIR
        old_neg = mod.HOTWORD_NEG_DIR

        hw_dir = os.path.join(tmp, "hotword")
        mod.HOTWORD_POS_DIR = os.path.join(hw_dir, "positive")
        mod.HOTWORD_NEG_DIR = os.path.join(hw_dir, "negative")
        mod.OUTPUT_DIR = out

        _make_hotword_positive(hw_dir)

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", esc50,
                        "--use-esc50-only",
                        "--include-local-hotword-negatives",
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out
            mod.HOTWORD_POS_DIR = old_pos
            mod.HOTWORD_NEG_DIR = old_neg

        # Check: no hotword files in clap dir
        for split in ("train", "val", "test"):
            clap_dir = os.path.join(out, split, "clap")
            if os.path.isdir(clap_dir):
                for f in os.listdir(clap_dir):
                    assert "hey_jarvis" not in f, f"Hey Jarvis found in clap! {f}"
                    assert "jarvis" not in f, f"Jarvis found in clap! {f}"

        # Check: hotword files exist in not_clap
        not_clap_train = os.path.join(out, "train", "not_clap")
        found_hw = False
        if os.path.isdir(not_clap_train):
            for f in os.listdir(not_clap_train):
                if "hey_jarvis" in f or "jarvis" in f:
                    found_hw = True
                    break
        assert found_hw, "No Hey Jarvis/Jarvis files found in not_clap directory"


def test_hotword_negatives_go_to_not_clap():
    """Hotword negatives (speech, noise, etc.) must land in not_clap."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        esc50 = os.path.join(tmp, "ESC50")
        _make_minimal_esc50(esc50)
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        old_pos = mod.HOTWORD_POS_DIR
        old_neg = mod.HOTWORD_NEG_DIR

        hw_dir = os.path.join(tmp, "hotword")
        mod.HOTWORD_POS_DIR = os.path.join(hw_dir, "positive")
        mod.HOTWORD_NEG_DIR = os.path.join(hw_dir, "negative")
        mod.OUTPUT_DIR = out

        _make_hotword_positive(hw_dir)
        # Add a negative speech file
        _make_wav(os.path.join(hw_dir, "negative", "speech", "speech_001.wav"))

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", esc50,
                        "--use-esc50-only",
                        "--include-local-hotword-negatives",
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out
            mod.HOTWORD_POS_DIR = old_pos
            mod.HOTWORD_NEG_DIR = old_neg

        not_clap_train = os.path.join(out, "train", "not_clap")
        found_speech = False
        if os.path.isdir(not_clap_train):
            for f in os.listdir(not_clap_train):
                if "speech" in f:
                    found_speech = True
                    break
        assert found_speech, "No speech negative found in not_clap directory"


def test_no_hotword_as_clap_even_without_esc50():
    """Without ESC-50, hotword must still NOT end up in clap dir."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        old_pos = mod.HOTWORD_POS_DIR
        old_neg = mod.HOTWORD_NEG_DIR

        hw_dir = os.path.join(tmp, "hotword")
        mod.HOTWORD_POS_DIR = os.path.join(hw_dir, "positive")
        mod.HOTWORD_NEG_DIR = os.path.join(hw_dir, "negative")
        mod.OUTPUT_DIR = out

        _make_hotword_positive(hw_dir)

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", os.path.join(tmp, "MISSING_ESC50"),
                        "--use-esc50-only",
                        "--include-local-hotword-negatives",
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out
            mod.HOTWORD_POS_DIR = old_pos
            mod.HOTWORD_NEG_DIR = old_neg

        for split in ("train", "val", "test"):
            clap_dir = os.path.join(out, split, "clap")
            if os.path.isdir(clap_dir):
                assert len(os.listdir(clap_dir)) == 0, f"Clap dir {clap_dir} has files but no ESC-50"
