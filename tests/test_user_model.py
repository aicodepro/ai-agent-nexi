import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_user_model_stores_short_answer_preference(monkeypatch, tmp_path):
    import engine.user_model as user_model
    monkeypatch.setattr(user_model, "USER_MODEL_PATH", tmp_path / "user_model.json")
    pref = user_model.infer_user_preference("from now on keep answers short")
    assert pref["key"] == "response_length"
    result = user_model.update_user_model(pref)
    assert result["updated"] is True
    assert "response_length" in user_model.get_user_model_context()


def test_user_model_applies_output_preference(monkeypatch, tmp_path):
    import engine.user_model as user_model
    monkeypatch.setattr(user_model, "USER_MODEL_PATH", tmp_path / "user_model.json")
    user_model.update_user_model({"type": "preference", "key": "output_destination", "value": "workspace"})
    strategy = user_model.apply_user_model_to_strategy({})
    assert strategy["output_destination"] == "workspace"
