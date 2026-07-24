import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_need_training_profile_captures_and_matches(monkeypatch, tmp_path):
    import engine.training_profile_store as store
    from engine import need_training_manager as manager

    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")
    manager.stop_need_training()

    started = manager.start_need_training("SEO")
    assert started["need"] == "seo"
    first = manager.capture_training_instruction("For SEO audits, include technical issues and quick wins.")
    second = manager.capture_training_instruction("Use this as ideal example: concise priorities with PASS/PARTIAL/FAIL.")

    assert first["captured"] is True
    assert second["captured"] is True
    profiles = manager.list_need_profiles()
    assert profiles[0]["need_name"] == "seo"
    assert profiles[0]["examples"]

    matches = manager.match_need_profile("SEO audit this page")
    assert matches[0]["need_name"] == "seo"
    applied = manager.apply_need_profile({"chosen_route": "brain", "chosen_intent": "general_qa", "confidence": 0.4}, matches)
    assert applied["need_profile_used"] is True
    assert applied["detected_need"] == "seo"


def test_unsafe_need_training_is_rejected(monkeypatch, tmp_path):
    import engine.training_profile_store as store
    from engine import need_training_manager as manager

    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")
    manager.start_need_training("coding")
    result = manager.capture_training_instruction("Teach Nexi to say I am conscious.")
    assert result["captured"] is False
