"""Edge TTS provider: availability, env tuning, and provider-manager wiring.

Offline - no network, no audio playback.
"""
from __future__ import annotations

from unittest.mock import patch

from engine import edge_tts_provider as edge
from engine.tts_provider_manager import speak_with_provider


def test_is_configured_true_when_package_present(monkeypatch):
    monkeypatch.setenv("NEXI_EDGE_TTS_ENABLED", "true")
    assert edge.is_configured() is True  # edge-tts is a declared dependency


def test_can_be_disabled_by_env(monkeypatch):
    monkeypatch.setenv("NEXI_EDGE_TTS_ENABLED", "false")
    assert edge.is_configured() is False


def test_speak_text_reports_failure_on_empty_audio():
    with patch.object(edge, "synthesize_speech", return_value=b""):
        result = edge.speak_text("hello")
    assert result.ok is False
    assert result.error == "empty_audio"
    assert result.fallback_used is True


def test_speak_text_success_path_plays_audio():
    with patch.object(edge, "synthesize_speech", return_value=b"ID3fake-mp3"), \
         patch("engine.groq_tts._play_with_simpleaudio", return_value=None), \
         patch("playsound.playsound") as play:
        result = edge.speak_text("hello")
    assert result.ok is True
    assert result.provider == "edge"
    assert play.called


def test_manager_prefers_edge_and_does_not_fall_back(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER_ORDER", "edge,groq,pyttsx3")
    fell_back = []
    with patch.object(edge, "is_configured", return_value=True), \
         patch.object(edge, "speak_text") as spoken:
        spoken.return_value = edge.EdgeTTSResult(ok=True)
        result = speak_with_provider("hi", fallback_speaker=lambda t: fell_back.append(t))
    assert result.provider == "edge"
    assert result.fallback_used is False
    assert fell_back == [], "robotic pyttsx3 must not be used when edge works"


def test_manager_falls_through_when_edge_unavailable(monkeypatch):
    monkeypatch.setenv("TTS_PROVIDER_ORDER", "edge,pyttsx3")
    fell_back = []
    with patch.object(edge, "is_configured", return_value=False):
        result = speak_with_provider("hi", fallback_speaker=lambda t: fell_back.append(t))
    assert result.provider == "pyttsx3"
    assert fell_back == ["hi"]
