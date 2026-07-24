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
    # 600ms/16kHz tone loud enough to pass the ASR audio-quality gate
    # (engine/groq_asr.py _audio_has_speech: >=500ms duration, >=0.01 RMS).
    wav = pcm_float32_to_wav_bytes([0.5, -0.5] * 4800, sample_rate=16000)

    # groq_asr posts via a pooled requests.Session (engine.groq_asr._session),
    # not the bare requests.post function, so that's what must be patched.
    with patch("engine.groq_asr._session.post", return_value=fake) as mock_post:
        assert transcribe_audio_bytes(wav) == "chrome"

    data = mock_post.call_args.kwargs["data"]
    assert data["language"] == "en"
    assert data["temperature"] == "0"
    # No default prompt is sent anymore: a non-empty prompt was found to be
    # ECHOED verbatim by Whisper on silence/noise (see groq_asr._load_asr_prompt
    # docstring), so the default prompt was deliberately removed as an
    # anti-hallucination fix. Opt-in only via GROQ_ASR_PROMPT.
    assert "prompt" not in data
    out = capsys.readouterr().out
    assert "[ASR] provider=groq language=en" in out
    assert "[ASR] record_ms=" in out
    assert "[ASR] upload_ms=" in out
    assert "[ASR] transcribe_ms=" in out
    assert '[ASR] text="chrome"' in out
