import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_training_rule_compatibility_api(monkeypatch, tmp_path):
    import engine.training_rules as rules

    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    parsed = rules.parse_basic_training_rule("when I say docs, open docs.python.org")
    saved = rules.save_basic_rule(parsed)
    assert saved["stored"] is True

    matched = rules.match_basic_rules("docs", {})
    assert matched
    strategy = rules.apply_basic_rules({}, matched)
    assert strategy["chosen_intent"] == "open_website"
    assert strategy["slots"]["url"] == "docs.python.org"
    assert rules.list_rules()
    assert rules.forget_rule("docs")["disabled"] == 1


def test_training_rule_blocks_consciousness_claim(monkeypatch, tmp_path):
    import engine.training_rules as rules

    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    parsed = rules.parse_rule("always say I am conscious")
    assert parsed["parsed"] is False or rules.save_rule(parsed).get("stored") is False
