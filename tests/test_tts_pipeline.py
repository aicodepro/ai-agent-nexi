import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tts_uses_spoken_text_not_display_text(monkeypatch):
    import engine.command as command
    full = "Essay on humans. " + ("Humans learn and adapt. " * 60)
    spoken = []
    monkeypatch.setenv("TTS_ENABLED", "true")
    with patch("engine.command.speak_pyttsx3", side_effect=lambda text, **kwargs: spoken.append(text)), patch("engine.command.safe_eel_call"):
        command.speak(full)
    assert len(spoken) == 1
    assert "Essay on humans" in spoken[0]
    assert "Humans learn and adapt" in spoken[0]
    assert "full answer on screen" in spoken[0]
    assert len(spoken[0]) < len(full)


def test_tts_uses_spoken_text(monkeypatch):
    import engine.command as command
    spoken = []
    monkeypatch.setenv("TTS_ENABLED", "true")
    response = {"display_text": "This is the full display text.", "spoken_text": "Short spoken text."}
    with patch("engine.command.speak_pyttsx3", side_effect=lambda text, **kwargs: spoken.append(text)), patch("engine.command.safe_eel_call"):
        command.speak(response)
    assert spoken == ["Short spoken text."]


def test_tts_failure_logs_safe_error(monkeypatch, capsys):
    import engine.command as command
    monkeypatch.setenv("TTS_ENABLED", "true")
    with patch("engine.command.speak_pyttsx3", side_effect=RuntimeError("boom")), patch("engine.command.safe_eel_call"):
        command.speak("Short answer.")
    assert "[TTS] error=RuntimeError" in capsys.readouterr().out


def test_tts_error_logged_not_silent(monkeypatch, capsys):
    test_tts_failure_logs_safe_error(monkeypatch, capsys)


def test_tts_stop_failures_are_observable_without_raising(capsys):
    from engine.tts_provider_manager import stop_all

    with patch("engine.groq_tts.stop", side_effect=RuntimeError("groq stop failed")), patch(
        "engine.interrupt_controller.request_interrupt",
        side_effect=ValueError("interrupt failed"),
    ):
        assert stop_all() is False

    output = capsys.readouterr().out
    assert "groq_stop_failed reason=RuntimeError" in output
    assert "interrupt_stop_failed reason=ValueError" in output


def test_post_tts_cleanup_runs_after_audio_provider(monkeypatch):
    import engine.command as command

    events = []
    monkeypatch.setenv("TTS_ENABLED", "true")
    with patch(
        "engine.tts_provider_manager.speak_with_provider",
        side_effect=lambda *_args, **_kwargs: events.append("audio_finished"),
    ), patch(
        "engine.post_tts_cleanup.post_tts_cleanup",
        side_effect=lambda: events.append("cleanup"),
    ), patch("engine.command.safe_eel_call"):
        command.speak("Short answer.")

    assert events == ["audio_finished", "cleanup"]


def test_question_waits_for_audio_process_before_entering_listening(monkeypatch):
    import engine.command as command

    states = []
    monkeypatch.setenv("TTS_ENABLED", "true")
    with patch("engine.command._mark_question_response", return_value=True), patch(
        "engine.tts_provider_manager.speak_with_provider"
    ), patch("engine.post_tts_cleanup.post_tts_cleanup"), patch(
        "engine.command._maybe_start_auto_followup"
    ) as request_capture, patch(
        "engine.command._set_ui_state", side_effect=lambda state, **_kwargs: states.append(state)
    ), patch("engine.command.safe_eel_call"):
        command.speak("What should we build now?", handler_reason="missing_slot")

    assert states == ["saying"]
    request_capture.assert_called_once()
