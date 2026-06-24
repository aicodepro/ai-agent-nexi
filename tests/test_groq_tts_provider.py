import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_groq_tts_missing_key_uses_fallback(monkeypatch):
    from engine.tts_provider_manager import speak_with_provider

    monkeypatch.setenv("TTS_PROVIDER_ORDER", "groq,pyttsx3")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    spoken = []
    result = speak_with_provider("hello", fallback_speaker=lambda text: spoken.append(text))
    assert result.provider == "pyttsx3"
    assert result.fallback_used is True
    assert spoken == ["hello"]


def test_groq_tts_configured_uses_groq(monkeypatch):
    from engine.tts_provider_manager import speak_with_provider
    from engine.groq_tts import GroqTTSResult, reset_soft_disable

    reset_soft_disable()
    monkeypatch.setenv("TTS_PROVIDER_ORDER", "groq,pyttsx3")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    with patch("engine.groq_tts.speak_text", return_value=GroqTTSResult(ok=True)) as speak_text:
        result = speak_with_provider("hello", fallback_speaker=lambda text: None)
    assert result.provider == "groq"
    assert result.fallback_used is False
    speak_text.assert_called_once_with("hello")


def test_groq_tts_failure_falls_back(monkeypatch):
    from engine.tts_provider_manager import speak_with_provider
    from engine.groq_tts import GroqTTSResult

    monkeypatch.setenv("TTS_PROVIDER_ORDER", "groq,pyttsx3")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    spoken = []
    with patch("engine.groq_tts.speak_text", return_value=GroqTTSResult(ok=False, fallback_used=True, error="boom")):
        result = speak_with_provider("hello", fallback_speaker=lambda text: spoken.append(text))
    assert result.provider == "pyttsx3"
    assert result.fallback_used is True
    assert spoken == ["hello"]
