import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_gemini_context_contains_recent_turns(monkeypatch, tmp_path):
    import engine.training_rules as rules
    import engine.user_model as user_model
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    monkeypatch.setattr(user_model, "USER_MODEL_PATH", tmp_path / "user_model.json")
    from engine.conversation_context import add_turn, clear_recent_context
    from engine.gemini_brain import _build_cognitive_context
    clear_recent_context()
    add_turn("user", "what is AI", source="typed")
    context, turns, _rules, _model = _build_cognitive_context("continue")
    assert turns == 1
    assert "what is AI" in context


def test_gemini_context_contains_training_rules(monkeypatch, tmp_path):
    import engine.training_rules as rules
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    rules.save_training_rule(rules.parse_training_instruction("when I say youtube, open youtube.com"))
    from engine.gemini_brain import _build_cognitive_context
    context, _turns, count, _model = _build_cognitive_context("youtube")
    assert count == 1
    assert "youtube" in context.lower()
