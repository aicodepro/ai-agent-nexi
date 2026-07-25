import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_groq_wav_playback_times_out_from_elapsed_config(monkeypatch):
    from engine import groq_tts

    class Handle:
        def __init__(self):
            self.checks = 0
            self.stopped = False

        def is_playing(self):
            self.checks += 1
            return self.checks == 1

        def stop(self):
            self.stopped = True

    handle = Handle()
    simpleaudio = SimpleNamespace(
        WaveObject=SimpleNamespace(
            from_wave_file=lambda _path: SimpleNamespace(play=lambda: handle)
        )
    )
    monkeypatch.setenv("GROQ_TTS_PLAYBACK_TIMEOUT_SECONDS", "1")

    with patch.dict(sys.modules, {"simpleaudio": simpleaudio}), patch(
        "engine.interrupt_controller.should_interrupt", return_value=False
    ), patch("engine.groq_tts.time.monotonic", side_effect=[10.0, 12.0]), patch(
        "engine.groq_tts.time.sleep"
    ):
        result = groq_tts._play_with_simpleaudio("response.wav")

    assert result is not None
    assert result.ok is False
    assert result.error == "playback_timeout"
    assert handle.stopped is True


def test_groq_playback_timeout_is_returned_to_provider_manager():
    from engine import groq_tts

    timeout_result = groq_tts.GroqTTSResult(
        ok=False, fallback_used=True, error="playback_timeout"
    )
    with patch("engine.groq_tts.synthesize_speech", return_value=b"wav"), patch(
        "engine.groq_tts._play_with_simpleaudio", return_value=timeout_result
    ):
        result = groq_tts.speak_text("hello")

    assert result is timeout_result


def test_hallucinated_asr_result_falls_back_before_returning_empty(monkeypatch):
    from engine import groq_asr

    hallucination = MagicMock(status_code=200)
    hallucination.json.return_value = {
        "text": "Thank you for watching",
        "segments": [{"no_speech_prob": 0.9, "avg_logprob": -1.5}],
    }
    valid = MagicMock(status_code=200)
    valid.json.return_value = {
        "text": "open chrome",
        "segments": [{"no_speech_prob": 0.02, "avg_logprob": -0.2}],
    }
    monkeypatch.setenv("GROQ_ASR_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GROQ_ASR_FALLBACK_MODELS", "whisper-large-v3")

    with patch("engine.groq_asr._audio_has_speech", return_value=True), patch(
        "engine.groq_asr._wav_duration_ms", return_value=2000
    ), patch("engine.groq_asr._audio_rms", return_value=0.03), patch.object(
        groq_asr._session, "post", side_effect=[hallucination, valid]
    ) as post:
        result = groq_asr.transcribe_audio_bytes(
            b"valid wav", api_key="test", model="whisper-large-v3-turbo"
        )

    assert result == "open chrome"
    assert [call.kwargs["data"]["model"] for call in post.call_args_list] == [
        "whisper-large-v3-turbo",
        "whisper-large-v3",
    ]


def test_hallucinated_asr_results_never_reach_command_routing(monkeypatch):
    from engine import groq_asr

    responses = []
    for _ in range(2):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "text": "Thank you for watching",
            "segments": [{"no_speech_prob": 0.9, "avg_logprob": -1.5}],
        }
        responses.append(response)
    monkeypatch.setenv("GROQ_ASR_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("GROQ_ASR_FALLBACK_MODELS", "whisper-large-v3")

    with patch("engine.groq_asr._audio_has_speech", return_value=True), patch(
        "engine.groq_asr._wav_duration_ms", return_value=2000
    ), patch("engine.groq_asr._audio_rms", return_value=0.03), patch.object(
        groq_asr._session, "post", side_effect=responses
    ) as post:
        result = groq_asr.transcribe_audio_bytes(
            b"valid wav", api_key="test", model="whisper-large-v3-turbo"
        )

    assert result == ""
    assert post.call_count == 2


def test_unknown_intent_provider_is_explicitly_unavailable():
    from engine.providers import get_intent_provider

    provider = get_intent_provider("does-not-exist")

    assert provider is not None
    assert provider.name == "does-not-exist"
    assert provider.is_available() is False
    result = provider.route_with_schema([], {})
    assert result.ok is False
    assert result.error_code == "unknown_provider"
    assert result.provider == "does-not-exist"
