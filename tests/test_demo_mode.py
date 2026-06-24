import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_demo_mode_reads_environment(monkeypatch):
    from engine.demo_mode import DemoMode

    monkeypatch.setenv("JARVIS_DEMO_MODE", "true")
    assert DemoMode.is_active() is True
    assert DemoMode.should_suppress_followup() is True
    assert DemoMode.use_local_tts() is True


def test_demo_mode_sanitizes_noisy_logs(monkeypatch):
    from engine.demo_mode import DemoMode

    monkeypatch.setenv("JARVIS_DEMO_MODE", "true")
    assert DemoMode.sanitize_log("[CONTEXT] noisy") == ""
    assert DemoMode.sanitize_log("[BRIDGE] useful") == "[BRIDGE] useful"


def test_demo_mode_suppresses_question_followup(monkeypatch):
    import engine.command as command

    monkeypatch.setenv("JARVIS_DEMO_MODE", "true")
    assert command._mark_question_response("Which app should I open?") is False


def test_demo_mode_forces_local_tts(monkeypatch):
    from engine import groq_tts

    monkeypatch.setenv("JARVIS_DEMO_MODE", "true")
    monkeypatch.setenv("GROQ_API_KEY", "demo-key")
    assert groq_tts.is_configured() is False


def test_demo_mode_router_failure_speaks_safe_response(monkeypatch):
    import engine.command as command

    monkeypatch.setenv("JARVIS_DEMO_MODE", "true")
    with patch("engine.groq_intent_router_v2.route_intent_v2", side_effect=RuntimeError("boom")), \
         patch.object(command, "speak") as mock_speak:
        handled = command._handle_product_intelligence_v2("anything", "typed")

    assert handled is True
    mock_speak.assert_called_once_with("Let me check that for you.", handler_reason="system")


def test_demo_mode_asr_missing_key_returns_canned_transcript(monkeypatch):
    from engine.groq_asr import transcribe_audio_bytes

    monkeypatch.setenv("JARVIS_DEMO_MODE", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert transcribe_audio_bytes(b"demo") == "hello"
