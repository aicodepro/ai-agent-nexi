"""Test CLAP_NN correctly rejects hotword speech as NOT_CLAP."""

import struct
import numpy as np
import pytest


def test_clap_nn_rejects_silence():
    """Without model, silence must not be clap."""
    from engine.clap_nn_backend import ClapNNBackend
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    silence = struct.pack("<16000h", *([0] * 16000))
    result = backend.process_pcm16(silence, 0.0)
    assert not result.is_clap
    assert result.reason != "clap_detected"


def test_clap_nn_rejects_hey_nexi_like_frame():
    """Random speech-like noise must not be clap without model."""
    from engine.clap_nn_backend import ClapNNBackend
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    speech_like = (np.random.randn(16000) * 5000).astype(np.int16).tobytes()
    result = backend.process_pcm16(speech_like, 0.0)
    assert not result.is_clap


def test_clap_nn_rejects_nexi_like_frame():
    from engine.clap_nn_backend import ClapNNBackend
    backend = ClapNNBackend(model_path="/nonexistent/model.pth")
    for _ in range(3):
        frame = (np.random.randn(16000) * 8000).astype(np.int16).tobytes()
        result = backend.process_pcm16(frame, 0.0)
        assert not result.is_clap


def test_clap_nn_backend_manager_rejects_random_speech():
    """ClapBackendManager must not wake on random speech."""
    from engine.clap_backend_manager import ClapBackendManager
    m = ClapBackendManager(cooldown_ms=0)
    for _ in range(10):
        frame = (np.random.randn(1280) * 3000).astype(np.int16).tobytes()
        r = m.process_audio_chunk(frame)
        assert not r["wake"], f"Wake on speech chunk: {r}"


def test_backend_manager_rejects_silence():
    from engine.clap_backend_manager import ClapBackendManager
    m = ClapBackendManager(cooldown_ms=0)
    silence = struct.pack("<1280h", *([0] * 1280))
    for _ in range(5):
        r = m.process_audio_chunk(silence)
        assert not r["wake"]
