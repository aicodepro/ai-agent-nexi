import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_groq_asr_sends_language_en():
    from engine.groq_asr import pcm_float32_to_wav_bytes, transcribe_audio_bytes
    response = Mock(status_code=200)
    response.json.return_value = {"text": "hello"}
    # 600ms/16kHz tone loud enough to pass the ASR audio-quality gate
    # (engine/groq_asr.py _audio_has_speech: >=500ms duration, >=0.01 RMS).
    wav = pcm_float32_to_wav_bytes([0.5, -0.5] * 4800, sample_rate=16000)
    # groq_asr posts via a pooled requests.Session (engine.groq_asr._session),
    # not the bare requests.post function, so that's what must be patched.
    with patch("engine.groq_asr._session.post", return_value=response) as mock_post:
        assert transcribe_audio_bytes(wav, api_key="key") == "hello"
    data = mock_post.call_args.kwargs["data"]
    assert data["language"] == "en"
    assert data["temperature"] == "0"
    # No default prompt is sent anymore: a non-empty prompt was found to be
    # ECHOED verbatim by Whisper on silence/noise, so it was deliberately
    # removed as an anti-hallucination fix (see groq_asr._load_asr_prompt).
    assert "prompt" not in data


def test_non_english_transcript_rejected():
    from engine.transcript_filter import is_gibberish_or_wrong_language
    assert is_gibberish_or_wrong_language("सர்ஜ ருனாள்டு") is True


def test_gibberish_transcript_rejected():
    from engine.transcript_filter import is_gibberish_or_wrong_language
    assert is_gibberish_or_wrong_language("Sarıç") is True
    assert is_gibberish_or_wrong_language("He's") is True
    assert is_gibberish_or_wrong_language("search ronaldo") is False
