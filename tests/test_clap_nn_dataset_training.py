"""Test CLAP_NN training with dataset structure."""

import os
import sys
import pytest


def test_train_script_module_imports():
    from scripts.train_clap_nn import (_load_model_class, _load_wav,
                                        _create_mel_filterbank, _audio_to_mel_spec,
                                        load_dataset)
    assert callable(_load_model_class)
    assert callable(_load_wav)
    assert callable(_create_mel_filterbank)
    assert callable(_audio_to_mel_spec)
    assert callable(load_dataset)


def test_load_model_class():
    from scripts.train_clap_nn import _load_model_class
    AudioClassifier = _load_model_class()
    assert AudioClassifier is not None


def test_load_wav():
    import numpy as np
    from scripts.train_clap_nn import _load_wav
    import wave
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        fname = f.name
    try:
        with wave.open(fname, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(16000, dtype=np.int16).tobytes())
            data = _load_wav(fname, 44100)
            assert len(data) > 0
            assert data.dtype in (np.float32, np.float64)
    finally:
        os.unlink(fname)


def test_mel_filterbank_shape():
    from scripts.train_clap_nn import _create_mel_filterbank
    fbank = _create_mel_filterbank(44100, 400, 128)
    assert fbank.shape == (128, 201)


def test_audio_to_mel_spec():
    import numpy as np
    from scripts.train_clap_nn import _audio_to_mel_spec
    wf = np.random.randn(44100).astype(np.float32) * 0.01
    spec = _audio_to_mel_spec(wf, 44100, 400, 200, 128, 256)
    assert spec.shape == (1, 256, 256)
    assert spec.dtype == np.float32


def test_load_dataset_empty_dir(tmp_path):
    from scripts.train_clap_nn import load_dataset
    with pytest.raises(SystemExit):
        load_dataset(str(tmp_path), "", sr=44100)


def test_validate_script_module_imports():
    from scripts.validate_clap_nn_model import (_load_model_class, _load_wav,
                                                 _create_mel_filterbank, _compute_mel_spec,
                                                 get_wav_files)
    assert callable(_load_model_class)
    assert callable(_load_wav)
    assert callable(_create_mel_filterbank)
    assert callable(_compute_mel_spec)
    assert callable(get_wav_files)
