from __future__ import annotations

from engine.audio_wake_pipeline import OpenWakeWordScorer, OWW_THRESHOLD, OWW_PRETRAINED


def test_hotword_calibration_threshold_reasonable():
    """The default hotword threshold must be between 0.1 and 0.6."""
    assert 0.1 <= OWW_THRESHOLD <= 0.6, f"OWW_THRESHOLD={OWW_THRESHOLD} out of range"


def test_hotword_calibration_pretrained_not_empty():
    """Pretrained model list must not be empty."""
    assert OWW_PRETRAINED, "OWW_PRETRAINED must not be empty"


def test_hotword_normal_voice_calibration_process_frame_no_wake():
    """Silence frames should not trigger wake."""
    from engine.audio_wake_pipeline import AudioWakePipeline
    pipeline = AudioWakePipeline(enable_clap=False)
    for _ in range(10):
        frame = b"\x00" * 3200
        result = pipeline.process_frame(frame)
        assert not result.get("wake"), "Silence should not trigger wake"
