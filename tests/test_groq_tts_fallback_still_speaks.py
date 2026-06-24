from __future__ import annotations


def test_groq_tts_fallback_still_speaks(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("TTS_PRIMARY_PROVIDER", "groq")
    monkeypatch.setenv("TTS_PROVIDER_ORDER", "groq,pyttsx3")

    from engine.tts_provider_manager import speak_with_provider

    spoken = []
    result = speak_with_provider("hello", fallback_speaker=spoken.append)

    assert result.ok
    assert result.provider == "pyttsx3"
    assert result.fallback_used
    assert spoken == ["hello"]

