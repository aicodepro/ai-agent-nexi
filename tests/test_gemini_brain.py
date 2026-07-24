import os
import sys
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_gemini_configured_from_gemini_or_google_key(monkeypatch):
    from engine import gemini_brain
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert gemini_brain.is_gemini_configured() is False
    monkeypatch.setenv("GOOGLE_API_KEY", "test-key")
    assert gemini_brain.is_gemini_configured() is True


def test_gemini_model_chain_default_and_override(monkeypatch):
    from engine import gemini_brain
    monkeypatch.delenv("GEMINI_MODEL_CHAIN", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    assert gemini_brain.get_gemini_model_chain()[0].startswith("gemini-")
    monkeypatch.setenv("GEMINI_MODEL_CHAIN", "gemini-a, gemini-b")
    assert gemini_brain.get_gemini_model_chain() == ["gemini-a", "gemini-b"]


def test_ask_gemini_posts_to_flash_and_extracts_text(monkeypatch):
    from engine import gemini_brain
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL_CHAIN", "gemini-test-flash")
    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {
        "candidates": [
            {"content": {"parts": [{"text": "Two plus two is four."}]}}
        ]
    }
    with patch("engine.gemini_brain.requests.post", return_value=fake_response) as mock_post:
        result = gemini_brain.ask_gemini("what is 2+2", context="Saved memories: demo")
    assert result == "Two plus two is four."
    args, kwargs = mock_post.call_args
    assert "gemini-test-flash:generateContent" in args[0]
    # The API key rides in a header, not a ?key= query param, so it never
    # leaks into URLs or request logs (see gemini_brain.ask_gemini comment).
    assert kwargs["headers"]["x-goog-api-key"] == "test-key"
    sent_text = kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "Saved memories: demo" in sent_text


def test_gemini_receives_recent_10_turns_context(monkeypatch):
    from engine import gemini_brain
    from engine.conversation_context import add_turn, clear_recent_context
    clear_recent_context()
    for idx in range(10):
        add_turn("user", f"question {idx}", source="typed")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL_CHAIN", "gemini-test-flash")
    fake_response = Mock(status_code=200)
    fake_response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}
    with patch("engine.gemini_brain.requests.post", return_value=fake_response) as mock_post:
        gemini_brain.ask_gemini("continue")
    sent_text = mock_post.call_args.kwargs["json"]["contents"][0]["parts"][0]["text"]
    assert "Recent conversation:" in sent_text
    assert "question 9" in sent_text


def test_gemini_memory_context_under_limit(monkeypatch):
    from engine import gemini_brain
    prompt, _turns, _memories = gemini_brain._memory_sections("hello", "x" * 8000, max_chars=1800)
    assert len(prompt) <= 1800


def test_ask_gemini_missing_key_raises(monkeypatch):
    from engine import gemini_brain
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    try:
        gemini_brain.ask_gemini("hello")
    except gemini_brain.GeminiConfigurationError:
        return
    raise AssertionError("missing key should raise GeminiConfigurationError")
