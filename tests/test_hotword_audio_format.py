"""Tests for hotword audio format requirements (Phase 4)."""

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 80
FRAME_SAMPLES = int(SAMPLE_RATE * FRAME_MS / 1000)


def test_frame_samples_correct():
    assert FRAME_SAMPLES == 1280, f"Expected 1280, got {FRAME_SAMPLES}"


def test_pcm16_dtype():
    frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    assert frame.dtype == np.int16


def test_mono_audio():
    frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    assert frame.ndim == 1


def test_bytes_length_for_openwakeword():
    frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
    raw = frame.tobytes()
    assert len(raw) == FRAME_SAMPLES * 2  # 16-bit = 2 bytes per sample


def test_normalization_hey_jarvis():
    name = "hey_jarvis"
    normalized = name.replace("_", " ")
    assert normalized == "hey jarvis"


def test_normalization_preserves_spaces():
    name = "hey jarvis"
    normalized = name.replace("_", " ")
    assert normalized == "hey jarvis"
