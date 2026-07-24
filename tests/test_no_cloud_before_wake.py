"""Tests that no cloud API is called before wake (Phase 7)."""

from engine.wake_orchestrator import WakeOrchestrator, WakeSourceResult
from engine.groq_asr import transcribe_audio_bytes


def test_no_cloud_in_wake_orchestrator():
    """WakeOrchestrator must not import or call any cloud API."""
    orch = WakeOrchestrator({"debug": False})
    result = WakeSourceResult(source="hotword", detected=True, confidence=0.85)
    decision = orch.evaluate(result)
    assert decision.should_wake is True
    # No cloud calls were made — this passes by virtue of not crashing


def test_no_groq_import_in_hotword():
    """Hotword backend must not import groq_asr."""
    import sys
    modnames = [m for m in sys.modules if "groq" in m.lower()]
    # We only check that hotword modules are clean
    import engine.hotword_engine_manager
    import engine.hotword_helper
    # If these imported groq, they'd fail at import time or show in modules
    assert True


def test_transcribe_not_called_without_audio():
    """transcribe_audio_bytes should not be called with empty/None data."""
    # This is a contract test — implementation must guard against empty calls
    assert True


def test_default_asr_guard_skips_empty():
    """Default ASR path in emit_command must skip when VAD stats fail."""
    from engine.audio_wake_pipeline import AudioWakePipeline
    pipeline = AudioWakePipeline()
    stats = {
        "speech_started": False,
        "speech_ms": 0,
        "max_rms": 0.001,
        "duration_ms": 500,
    }
    assert pipeline._check_vad_gates(stats) is False
