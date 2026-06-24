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
    assert spoken == ["Here's the short version. I've put the full answer on screen."]


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
