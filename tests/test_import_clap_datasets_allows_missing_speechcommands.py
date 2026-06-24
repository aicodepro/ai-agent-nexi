"""Test --allow-missing SpeechCommands does not crash when dataset absent."""

import os
import sys
import tempfile


def _make_minimal_esc50(base: str):
    import wave
    import numpy as np
    meta_dir = os.path.join(base, "meta")
    audio_dir = os.path.join(base, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(meta_dir, exist_ok=True)

    rows = ["filename,fold,target,category"]
    for i in range(3):
        fname = f"1-{i+1:04d}-A-0{i+1}.wav"
        data = (np.random.randn(44100).astype(np.int16) * 100).astype(np.int16)
        wpath = os.path.join(audio_dir, fname)
        with wave.open(wpath, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(44100)
            wf.writeframes(data.tobytes())
        cls = 12 if i == 0 else 0
        rows.append(f"{fname},{i+1},{cls},c{i}")
    with open(os.path.join(meta_dir, "esc50.csv"), "w") as f:
        f.write("\n".join(rows))


def test_allow_missing_speechcommands_does_not_fail():
    """--allow-missing SpeechCommands must not crash when SC is absent."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        esc50 = os.path.join(tmp, "ESC50")
        _make_minimal_esc50(esc50)
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = out

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", esc50,
                        "--allow-missing", "SpeechCommands",
                        "--speech-commands", os.path.join(tmp, "MISSING_SC"),
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out

        manifest = os.path.join(out, "manifest.csv")
        assert os.path.isfile(manifest), f"Manifest not found at {manifest}"


def test_allow_missing_all_datasets_works():
    """Allow all datasets to be missing, only ESC-50 present."""
    from scripts.import_clap_datasets import main as importer_main

    with tempfile.TemporaryDirectory() as tmp:
        esc50 = os.path.join(tmp, "ESC50")
        _make_minimal_esc50(esc50)
        out = os.path.join(tmp, "clap_nn")

        import scripts.import_clap_datasets as mod
        old_out = mod.OUTPUT_DIR
        mod.OUTPUT_DIR = out

        try:
            sys.argv = ["import_clap_datasets.py",
                        "--esc50", esc50,
                        "--allow-missing", "SpeechCommands", "FSD50K",
                        "UrbanSound8K", "Freesound",
                        "--speech-commands", os.path.join(tmp, "MISSING_SC"),
                        "--fsd50k", os.path.join(tmp, "MISSING_FSD"),
                        "--urbansound8k", os.path.join(tmp, "MISSING_US8K"),
                        "--freesound", os.path.join(tmp, "MISSING_FREESOUND"),
                        "--skip-redistribute"]
            importer_main()
        except SystemExit:
            pass
        finally:
            mod.OUTPUT_DIR = old_out

        manifest = os.path.join(out, "manifest.csv")
        assert os.path.isfile(manifest)
