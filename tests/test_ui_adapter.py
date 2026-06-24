import pytest
from ui.adapter import submit_text, get_env_status, get_capabilities


def test_submit_empty():
    result = submit_text("")
    assert result == {"status": "empty"}


def test_submit_whitespace():
    result = submit_text("   ")
    assert result == {"status": "empty"}


def test_submit_none():
    result = submit_text(None)
    assert result == {"status": "empty"}


def test_get_env_status():
    result = get_env_status()
    assert isinstance(result, dict)
    assert "groq" in result
    assert "gemini" in result


def test_get_capabilities():
    result = get_capabilities()
    assert isinstance(result, dict)
    assert result.get("file_drop") is True
    assert result.get("voice_input") is True
    assert result.get("text_input") is True
