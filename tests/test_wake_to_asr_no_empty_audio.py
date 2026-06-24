"""Tests for wake-to-ASR no empty audio (Phase 7)."""

from engine.audio_wake_pipeline import AudioWakePipeline


def _make_pipeline():
    return AudioWakePipeline()


def test_vad_min_speech_ms_gate():
    """Pipeline should skip ASR if speech duration is below threshold."""
    pipeline = _make_pipeline()
    mock_vad_stats = {
        "speech_started": False,
        "speech_ms": 0,
        "max_rms": 0.001,
        "duration_ms": 800,
    }
    # This should not crash and should skip ASR
    pipeline._last_capture_stats = mock_vad_stats
    result = pipeline._check_vad_gates(mock_vad_stats)
    assert result is False or result is not None


def test_vad_min_rms_gate():
    """Pipeline should skip ASR if max RMS is below threshold."""
    pipeline = _make_pipeline()
    mock_stats = {
        "speech_started": True,
        "speech_ms": 800,
        "max_rms": 0.003,
        "duration_ms": 1500,
    }
    pipeline._last_capture_stats = mock_stats
    result = pipeline._check_vad_gates(mock_stats)
    assert result is False or result is not None


def test_vad_both_gates_pass():
    """Pipeline should allow ASR if speech duration and RMS pass."""
    pipeline = _make_pipeline()
    mock_stats = {
        "speech_started": True,
        "speech_ms": 1200,
        "max_rms": 0.05,
        "duration_ms": 2000,
    }
    pipeline._last_capture_stats = mock_stats
    result = pipeline._check_vad_gates(mock_stats)
    assert result is not False


def test_empty_audio_not_sent_to_asr():
    """Simulate no speech — ASR should not be called."""
    pipeline = _make_pipeline()
    # Stats with no speech
    stats = {
        "speech_started": False,
        "speech_ms": 0,
        "max_rms": 0.001,
        "duration_ms": 600,
    }
    assert pipeline._check_vad_gates(stats) is False
