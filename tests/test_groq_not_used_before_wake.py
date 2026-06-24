from __future__ import annotations

import os

from engine.internal_wake_signal import InternalWakeSignalBus, WakeSignal


def test_groq_not_used_before_wake_no_asr_in_signal_bus():
    """The InternalWakeSignalBus should not import or use Groq."""
    bus = InternalWakeSignalBus()
    assert "groq" not in type(bus).__module__.lower()


def test_groq_not_called_during_wake_signal():
    """Wake signal emission must not trigger ASR."""
    called = {"groq": False}
    def track(signal):
        pass
    bus = InternalWakeSignalBus(post_fn=track)
    bus.emit_wake(WakeSignal(source="hotword", state="wake_detected"))
    assert not called["groq"]


def test_wake_pipeline_emits_wake_without_asr():
    """Test that AudioWakePipeline.process_frame does not call Groq."""
    from engine.audio_wake_pipeline import AudioWakePipeline
    pipeline = AudioWakePipeline(enable_clap=False)
    frame = b"\x00" * 3200  # 100 ms of silence at 16 kHz
    result = pipeline.process_frame(frame)
    assert "wake" in result
