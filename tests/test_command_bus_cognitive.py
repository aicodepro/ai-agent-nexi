import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_what_have_you_learned_summary(monkeypatch, tmp_path):
    import engine.training_rules as rules
    import engine.user_model as user_model
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    monkeypatch.setattr(user_model, "USER_MODEL_PATH", tmp_path / "user_model.json")
    rules.save_training_rule(rules.parse_training_instruction("when I say youtube, open youtube.com"))
    from engine.command import _handle_cognitive_command
    with patch("engine.command.speak") as speak:
        assert _handle_cognitive_command("what have you learned") is True
    assert "youtube" in speak.call_args.args[0].lower()


def test_why_did_you_do_that_explains_route():
    from engine.cognitive_context import set_last_strategy
    from engine.command import _handle_cognitive_command
    set_last_strategy({"chosen_route": "tool", "chosen_intent": "open_website", "reason": "learned rule maps youtube to youtube.com", "learned_rules_used": ["rule_1"]})
    with patch("engine.command.speak") as speak:
        assert _handle_cognitive_command("why did you do that?") is True
    assert "open_website" in speak.call_args.args[0]


def test_command_bus_records_cognitive_strategy(monkeypatch, tmp_path):
    import engine.training_rules as rules
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    from engine.command_bus import submit_user_command
    from engine.cognitive_context import get_last_strategy
    with patch("engine.command.allCommands"):
        submit_user_command("what is AI", source="typed", mode="typed")
    assert get_last_strategy()["chosen_route"] in {"brain", "clarify", "tool"}
