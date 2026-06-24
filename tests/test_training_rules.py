import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_training_rule_when_i_say_youtube(monkeypatch, tmp_path):
    import engine.training_rules as rules
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    parsed = rules.parse_training_instruction("when I say youtube, open youtube.com")
    assert parsed["parsed"] is True
    saved = rules.save_training_rule(parsed)
    assert saved["stored"] is True
    assert saved["rule"]["trigger"] == "youtube"


def test_training_rule_applies_next_time(monkeypatch, tmp_path):
    import engine.training_rules as rules
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    rules.save_training_rule(rules.parse_training_instruction("when I say youtube, open youtube.com"))
    matched = rules.match_training_rules("youtube", {})
    strategy = rules.apply_training_rule(matched[0], {})
    assert strategy["chosen_intent"] == "open_website"
    assert strategy["slots"]["url"] == "youtube.com"
