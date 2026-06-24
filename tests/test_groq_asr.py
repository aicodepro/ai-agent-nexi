import io
import os
import sys
import wave

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from unittest.mock import patch, MagicMock

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "sk_test_FAKE_KEY_SHOULD_NEVER_LEAK")
    monkeypatch.setenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
    monkeypatch.setenv("GROQ_TIMEOUT_SECONDS", "5")
    yield


# ---------------------------------------------------------------------------
# WAV bytes helper
# ---------------------------------------------------------------------------

def test_wav_bytes_are_valid_for_int16_array():
    import numpy as np
    from engine.groq_asr import pcm_float32_to_wav_bytes

    pcm = np.zeros(1600, dtype=np.int16)
    wav = pcm_float32_to_wav_bytes(pcm, sample_rate=16000)

    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 1600


def test_wav_bytes_are_valid_for_float32_array():
    import numpy as np
    from engine.groq_asr import pcm_float32_to_wav_bytes

    audio = (np.sin(np.linspace(0, 1, 1600, dtype=np.float32)) * 0.5).astype(np.float32)
    wav = pcm_float32_to_wav_bytes(audio, sample_rate=16000)

    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 16000
        assert wf.getnframes() == 1600


def test_wav_bytes_are_valid_for_raw_pcm16_bytes():
    from engine.groq_asr import pcm_float32_to_wav_bytes
    raw = b"\x00\x00" * 800
    wav = pcm_float32_to_wav_bytes(raw, sample_rate=16000)
    with wave.open(io.BytesIO(wav), "rb") as wf:
        assert wf.getnframes() == 800


# ---------------------------------------------------------------------------
# transcribe_audio_bytes
# ---------------------------------------------------------------------------

def test_missing_groq_key_returns_empty(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    from engine.groq_asr import transcribe_audio_bytes
    result = transcribe_audio_bytes(b"RIFF....WAVE")
    assert result == ""


def test_empty_audio_returns_empty():
    from engine.groq_asr import transcribe_audio_bytes
    assert transcribe_audio_bytes(b"") == ""


def test_groq_success_returns_text():
    from engine import groq_asr

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"text": "  two plus two is four  "}

    with patch("engine.groq_asr.requests.post", return_value=fake_resp) as mock_post:
        result = groq_asr.transcribe_audio_bytes(b"RIFFsamplewav")
        assert result == "two plus two is four"
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        assert call_kwargs["headers"]["Authorization"].startswith("Bearer ")
        assert "file" in call_kwargs["files"]


def test_groq_error_returns_empty():
    from engine import groq_asr

    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.json.return_value = {"error": "unauthorized"}

    with patch("engine.groq_asr.requests.post", return_value=fake_resp):
        assert groq_asr.transcribe_audio_bytes(b"RIFFwav") == ""


def test_groq_timeout_returns_empty():
    import requests
    from engine import groq_asr

    with patch(
        "engine.groq_asr.requests.post",
        side_effect=requests.exceptions.Timeout("timeout"),
    ):
        assert groq_asr.transcribe_audio_bytes(b"RIFFwav") == ""


def test_groq_invalid_json_returns_empty():
    from engine import groq_asr

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.side_effect = ValueError("bad json")

    with patch("engine.groq_asr.requests.post", return_value=fake_resp):
        assert groq_asr.transcribe_audio_bytes(b"RIFFwav") == ""


def test_no_secret_logged(capsys):
    from engine import groq_asr

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"text": "ok"}

    with patch("engine.groq_asr.requests.post", return_value=fake_resp):
        groq_asr.transcribe_audio_bytes(b"RIFFwav")

    out = capsys.readouterr().out
    assert "sk_test_FAKE_KEY_SHOULD_NEVER_LEAK" not in out
    assert "Authorization" not in out
    assert "Bearer " not in out


def test_no_secret_logged_on_error(capsys):
    from engine import groq_asr

    fake_resp = MagicMock()
    fake_resp.status_code = 401
    fake_resp.json.return_value = {"error": "nope"}

    with patch("engine.groq_asr.requests.post", return_value=fake_resp):
        groq_asr.transcribe_audio_bytes(b"RIFFwav")

    out = capsys.readouterr().out
    assert "sk_test_FAKE_KEY_SHOULD_NEVER_LEAK" not in out
    assert "Bearer " not in out


def test_uses_configured_model():
    from engine import groq_asr

    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.json.return_value = {"text": "ok"}

    with patch("engine.groq_asr.requests.post", return_value=fake_resp) as mock_post:
        groq_asr.transcribe_audio_bytes(
            b"RIFFwav", model="whisper-large-v3", api_key="explicit_key"
        )
        sent_data = mock_post.call_args.kwargs["data"]
        assert sent_data["model"] == "whisper-large-v3"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
