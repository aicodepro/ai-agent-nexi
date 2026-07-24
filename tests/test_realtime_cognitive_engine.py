import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_generates_multiple_intent_hypotheses(monkeypatch, tmp_path):
    import engine.training_rules as training_rules
    import engine.tool_usage_intelligence as tool_ai
    monkeypatch.setattr(training_rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", tmp_path / "tools.json")
    from engine.realtime_cognitive_engine import generate_intent_hypotheses
    hypotheses = generate_intent_hypotheses("open chrome", {})
    assert len(hypotheses) >= 1
    assert any(item["route"] == "tool" for item in hypotheses)


def test_chooses_learned_rule_over_generic_intent(monkeypatch, tmp_path):
    import engine.training_rules as training_rules
    import engine.tool_usage_intelligence as tool_ai
    monkeypatch.setattr(training_rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", tmp_path / "tools.json")
    rule = training_rules.parse_training_instruction("when I say youtube, open youtube.com")
    training_rules.save_training_rule(rule)
    from engine.realtime_cognitive_engine import analyze_input
    strategy = analyze_input("youtube")
    assert strategy["chosen_route"] == "tool"
    assert strategy["chosen_intent"] == "open_website"
    assert strategy["slots"]["url"] == "youtube.com"
    assert strategy["learned_rules_used"]


def test_low_confidence_asks_clarification(monkeypatch, tmp_path):
    import engine.training_rules as training_rules
    monkeypatch.setattr(training_rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    from engine.realtime_cognitive_engine import analyze_input
    strategy = analyze_input("zz")
    assert strategy["chosen_route"] == "clarify"
    assert strategy["needs_clarification"] is True


def test_pending_open_accepts_youtube_as_open_website():
    from engine.realtime_cognitive_engine import generate_intent_hypotheses
    context = {"pending_followup": {"followup_type": "open_app"}}
    hypotheses = generate_intent_hypotheses("youtube", context)
    assert any(h["intent"] == "open_website" and h["slots"]["url"] == "youtube.com" for h in hypotheses)
