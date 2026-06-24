import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_transcript_filter_allows_chrome_with_pending(monkeypatch):
    from engine.transcript_filter import accepts_pending_followup_answer, is_gibberish_or_wrong_language

    monkeypatch.setenv("TRANSCRIPT_ALLOW_SHORT_FOLLOWUP", "true")
    assert is_gibberish_or_wrong_language("chrome") is True
    assert accepts_pending_followup_answer("chrome") is True


def test_transcript_filter_rejects_um_without_pending():
    from engine.transcript_filter import accepts_pending_followup_answer, is_gibberish_or_wrong_language

    assert is_gibberish_or_wrong_language("um") is True
    assert accepts_pending_followup_answer("um") is False
