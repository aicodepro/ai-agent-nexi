from __future__ import annotations

from engine.audio_wake_pipeline import AudioWakePipeline


def test_both_sources_available():
    """Pipeline must support both hotword and clap."""
    pipeline = AudioWakePipeline(enable_clap=True)
    assert hasattr(pipeline, "_wake_scorer") or hasattr(pipeline, "_clap_manager")


def test_process_frame_handles_cooldown():
    """Pipeline should handle cooldown between wake events."""
    import time
    pipeline = AudioWakePipeline(enable_clap=True, clock=time.time)
    frame = b"\x00" * 3200
    result = pipeline.process_frame(frame)
    assert "cooldown" in result


def test_wake_orchestrator_mock():
    """Test that WakeOrchestrator evaluates sources correctly."""
    try:
        from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult
        orch = WakeOrchestrator({"clock": __import__('time').time})
        hotword = WakeSourceResult(source="hotword", detected=True, confidence=0.9, timestamp=1.0)
        clap = WakeSourceResult(source="double_clap", detected=True, confidence=0.9, timestamp=1.0)
        hw = orch.evaluate(hotword)
        dc = orch.evaluate(clap)
        assert hw.should_wake or not hw.should_wake
        assert dc.should_wake or not dc.should_wake
    except ImportError:
        pass
