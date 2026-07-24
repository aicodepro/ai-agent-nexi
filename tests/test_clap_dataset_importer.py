"""Test the CLAP dataset importer."""

import os
import sys
import tempfile
import pytest


@pytest.fixture
def importer_script():
    import scripts.import_clap_datasets as imp
    return imp


def test_importer_module_imports():
    from scripts.import_clap_datasets import _ensure_dirs, _dedup_name, _segment_into_windows
    assert callable(_ensure_dirs)
    assert callable(_dedup_name)
    assert callable(_segment_into_windows)


def test_dedup_name():
    from scripts.import_clap_datasets import _dedup_name
    name = _dedup_name("/some/path/test_file.wav")
    assert name.endswith(".wav")
    assert "test_file" in name
    assert len(name) > len("test_file.wav")


def test_resample_wav():
    import numpy as np
    from scripts.import_clap_datasets import _resample_wav
    audio = np.zeros(16000, dtype=np.int16)
    audio[:1000] = 100
    resampled = _resample_wav(audio, 16000, 44100)
    assert len(resampled) > 16000
    assert resampled.dtype == np.int16


def test_segment_into_windows():
    import numpy as np
    from scripts.import_clap_datasets import _segment_into_windows, TARGET_SR, WINDOW_SAMPLES
    audio = np.random.randn(TARGET_SR * 3).astype(np.int16) * 100
    windows = _segment_into_windows(audio, TARGET_SR)
    assert len(windows) == 6  # 3 seconds / 0.5 sec = 6
    for w in windows:
        assert len(w) == WINDOW_SAMPLES


def test_redistribute_splits():
    import tempfile, os
    from scripts.import_clap_datasets import OUTPUT_DIR, _redistribute_splits
    # Just ensure it doesn't crash when dirs are empty
    log = []
    _redistribute_splits(log)
    assert isinstance(log, list)


def test_esc50_import_skips_if_missing():
    from scripts.import_clap_datasets import _import_esc50
    log = []
    counts = _import_esc50("/nonexistent/esc50", log)
    assert counts == {"clap": 0, "not_clap": 0}
    assert any("SKIP" in l for l in log)


def test_hotword_positives_imported_as_not_clap(tmp_path):
    from scripts.import_clap_datasets import _import_hotword_positives, OUTPUT_DIR
    log = []
    counts = _import_hotword_positives(log)
    assert "not_clap" in counts


def test_manifest_csv_creation(tmp_path):
    import csv
    from scripts.import_clap_datasets import _write_manifest, OUTPUT_DIR
    os.makedirs(os.path.join(OUTPUT_DIR, "train", "clap"), exist_ok=True)
    os.makedirs(os.path.join(OUTPUT_DIR, "train", "not_clap"), exist_ok=True)
    log = []
    counts = _write_manifest(log)
    assert isinstance(counts, dict)
    assert any("MANIFEST" in l for l in log)
