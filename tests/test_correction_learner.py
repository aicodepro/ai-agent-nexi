import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_correction_rule_is_stored(monkeypatch, tmp_path):
    import engine.correction_learner as learner

    rules_path = tmp_path / "correction_rules.json"
    monkeypatch.setattr(learner, "RULES_PATH", rules_path)

    result = learner.record_correction_from_text("wrong, when I say tube, open youtube")

    assert result["stored"] is True
    data = json.loads(rules_path.read_text(encoding="utf-8"))
    assert data["rules"][0]["trigger_norm"] == "tube"
    assert data["rules"][0]["action"] == "open youtube"


def test_correction_rule_is_applied(monkeypatch, tmp_path):
    import engine.correction_learner as learner

    monkeypatch.setattr(learner, "RULES_PATH", tmp_path / "correction_rules.json")
    learner.record_correction_from_text("wrong, when I say tube, open youtube")

    result = learner.apply_correction("tube")

    assert result["matched"] is True
    assert result["action_text"] == "open youtube"
    assert result["rule"]["trigger_norm"] == "tube"
