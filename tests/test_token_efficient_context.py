import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_compact_prompt_file_exists():
    root = Path(__file__).resolve().parents[1]
    assert (root / "prompts" / "compact_runtime_prompt.txt").exists()


def test_gemini_context_includes_only_last_5_turns_and_excludes_secrets():
    from engine.conversation_context import add_user_turn, add_assistant_turn, clear_recent_context, build_compact_context
    clear_recent_context()
    for i in range(7):
        add_user_turn(f"question {i}", "typed")
        add_assistant_turn(f"answer {i}")
    add_user_turn("my api key is SECRET", "typed")
    context = build_compact_context(limit=5)
    assert "question 0" not in context
    assert "question 1" not in context
    assert "question 2" not in context
    assert "answer 6" in context
    assert "SECRET" not in context


def test_gemini_prompt_uses_supplied_compact_context():
    from engine.gemini_brain import _build_prompt
    prompt = _build_prompt("make it shorter", "Recent turns:\nJarvis: a long answer")
    assert "Recent turns" in prompt
    assert "make it shorter" in prompt
