import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_deep_training_dataset_and_evaluation(monkeypatch, tmp_path):
    import engine.training_dataset as dataset
    import engine.training_evaluator as evaluator
    from engine.deep_training_engine import create_training_dataset_item, evaluate_strategy_against_dataset, start_ultra_training

    monkeypatch.setattr(dataset, "TRAINING_DATASET_PATH", tmp_path / "dataset.json")
    monkeypatch.setattr(evaluator, "TRAINING_EVALUATIONS_PATH", tmp_path / "evals.json")

    assert start_ultra_training("seo")["need"] == "seo"
    created = create_training_dataset_item({"need": "seo", "input": "SEO audit this page", "expected_route": "brain", "expected_intent": "need_profile_task"})
    assert created["saved"] is True
    evaluation = evaluate_strategy_against_dataset({"chosen_route": "brain", "chosen_intent": "need_profile_task"}, created["item"])
    assert evaluation["overall_score"] >= 0.8


def test_training_feedback_and_curriculum(monkeypatch, tmp_path):
    import engine.training_feedback as feedback
    import engine.training_dataset as dataset
    import engine.training_evaluator as evaluator
    import engine.training_profile_store as store
    from engine.training_curriculum import recommend_next_training_step

    monkeypatch.setattr(feedback, "TRAINING_FEEDBACK_PATH", tmp_path / "feedback.json")
    monkeypatch.setattr(dataset, "TRAINING_DATASET_PATH", tmp_path / "dataset.json")
    monkeypatch.setattr(evaluator, "TRAINING_EVALUATIONS_PATH", tmp_path / "evals.json")
    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")

    saved = feedback.record_feedback("This was good", "Short answer", need="coding")
    assert saved["saved"] is True
    step = recommend_next_training_step("coding")
    assert "next_step" in step
