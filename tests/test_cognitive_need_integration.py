import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_cognitive_strategy_applies_need_profile(monkeypatch, tmp_path):
    import engine.training_profile_store as store
    import engine.training_rules as rules
    from engine.need_training_manager import start_need_training, capture_training_instruction, stop_need_training
    from engine.realtime_cognitive_engine import analyze_input

    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    start_need_training("seo")
    capture_training_instruction("For SEO audits, include technical fixes and quick wins.")
    stop_need_training()

    strategy = analyze_input("SEO audit this page", source="typed")
    assert strategy["need_profile_used"] is True
    assert strategy["detected_need"] == "seo"
    assert strategy["profile_rules_used"]


def test_cognitive_learned_rule_still_wins_over_profile(monkeypatch, tmp_path):
    import engine.training_profile_store as store
    import engine.training_rules as rules
    from engine.need_training_manager import start_need_training, capture_training_instruction, stop_need_training
    from engine.realtime_cognitive_engine import analyze_input

    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")
    rules.save_rule(rules.parse_rule("when I say seo docs, open docs.python.org"))
    start_need_training("seo")
    capture_training_instruction("For SEO, answer in audit style.")
    stop_need_training()

    strategy = analyze_input("seo docs", source="typed")
    assert strategy["need_profile_used"] is True
