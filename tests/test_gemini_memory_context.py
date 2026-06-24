import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_gemini_memory_context_under_limit():
    from engine.gemini_brain import _memory_sections
    context, turns, memories = _memory_sections("hello", "x" * 5000, max_chars=1800)
    assert len(context) <= 1800
    assert turns >= 0
    assert memories >= 0


def test_gemini_receives_recent_10_turns_context():
    from engine.conversation_context import add_turn, clear_recent_context
    from engine.gemini_brain import _memory_sections
    clear_recent_context()
    for idx in range(10):
        add_turn("user", f"question {idx}", source="typed")
    context, turns, _memories = _memory_sections("continue", "", max_chars=2500)
    assert turns == 10
    assert "Recent conversation:" in context
    assert "question 9" in context
