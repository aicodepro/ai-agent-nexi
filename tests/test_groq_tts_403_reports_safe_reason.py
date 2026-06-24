from __future__ import annotations

import io
import urllib.error
from unittest.mock import patch


def test_groq_tts_403_reports_safe_reason(monkeypatch, capsys):
    monkeypatch.setenv("GROQ_API_KEY", "secret-test-key")

    from engine import groq_tts

    err = urllib.error.HTTPError(
        url="https://api.groq.com/openai/v1/audio/speech",
        code=403,
        msg="Forbidden",
        hdrs=None,
        fp=io.BytesIO(b"forbidden"),
    )

    with patch("urllib.request.urlopen", side_effect=err):
        result = groq_tts.speak_text("hello")

    out = capsys.readouterr().out
    assert not result.ok
    assert result.fallback_used
    assert result.error == "groq_http_403"
    assert "groq_http_403" in out
    assert "secret-test-key" not in out
