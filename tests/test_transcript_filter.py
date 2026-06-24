import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_groq_asr_sends_language_en():
    from engine.groq_asr import transcribe_audio_bytes
    response = Mock(status_code=200)
    response.json.return_value = {"text": "hello"}
    with patch("engine.groq_asr.requests.post", return_value=response) as mock_post:
        assert transcribe_audio_bytes(b"RIFFdata", api_key="key") == "hello"
    data = mock_post.call_args.kwargs["data"]
    assert data["language"] == "en"
    assert data["temperature"] == "0"
    assert "Output only" in data["prompt"]


def test_non_english_transcript_rejected():
    from engine.transcript_filter import is_gibberish_or_wrong_language
    assert is_gibberish_or_wrong_language("सர்ஜ ருனாள்டு") is True


def test_gibberish_transcript_rejected():
    from engine.transcript_filter import is_gibberish_or_wrong_language
    assert is_gibberish_or_wrong_language("Sarıç") is True
    assert is_gibberish_or_wrong_language("He's") is True
    assert is_gibberish_or_wrong_language("search ronaldo") is False
