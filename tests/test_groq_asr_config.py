import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_asr_language_english_temperature_zero(monkeypatch, capsys):
    from engine.groq_asr import pcm_float32_to_wav_bytes, transcribe_audio_bytes

    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("GROQ_ASR_LANGUAGE", "en")
    monkeypatch.setenv("GROQ_ASR_TEMPERATURE", "0")
    fake = Mock(status_code=200)
    fake.json.return_value = {"text": "chrome"}
    wav = pcm_float32_to_wav_bytes([0.0] * 1600)

    with patch("engine.groq_asr.requests.post", return_value=fake) as mock_post:
        assert transcribe_audio_bytes(wav) == "chrome"

    data = mock_post.call_args.kwargs["data"]
    assert data["language"] == "en"
    assert data["temperature"] == "0"
    assert "Output only the speech verbatim" in data["prompt"]
    out = capsys.readouterr().out
    assert "[ASR] provider=groq language=en" in out
    assert "[ASR] record_ms=" in out
    assert "[ASR] upload_ms=" in out
    assert "[ASR] transcribe_ms=" in out
    assert '[ASR] text="chrome"' in out
