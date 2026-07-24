import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_default_asr_skips_when_vad_speech_too_short():
    from engine.audio_wake_pipeline import AudioWakePipeline

    pipeline = AudioWakePipeline()
    pipeline._last_capture_stats = {"speech_ms": 0, "max_rms": 0.0, "speech_started": False}
    result = pipeline.emit_command(b"\x00\x00" * 16000, source="double_clap")
    assert result == ""


def test_custom_asr_still_dispatches_valid_transcript():
    from engine.audio_wake_pipeline import AudioWakePipeline

    calls = []
    pipeline = AudioWakePipeline(on_command_text=calls.append, asr=lambda audio, sr: "open chrome")
    pipeline._last_capture_stats = {"speech_ms": 800, "max_rms": 0.02, "speech_started": True}
    result = pipeline.emit_command(b"\x00\x00" * 16000, source="double_clap")
    assert result == "open chrome"
    assert calls == ["open chrome"]
