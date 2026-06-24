import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_train_mode_need_profile_flow(monkeypatch, tmp_path):
    import engine.training_profile_store as store
    import engine.training_rules as rules
    from engine import train_mode

    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(rules, "TRAINING_RULES_PATH", tmp_path / "rules.json")

    assert "Cognitive training active" in train_mode.handle_training_command("train Jarvis for coding")
    learned = train_mode.handle_training_command("For coding tasks, inspect files before editing and run focused tests.")
    assert "Learned for coding" in learned
    stopped = train_mode.handle_training_command("stop training")
    assert "ready" in stopped or "stopped" in stopped
    assert "coding" in train_mode.handle_training_command("show training profiles")


def test_train_mode_ultra_commands(monkeypatch, tmp_path):
    import engine.training_dataset as dataset
    import engine.training_evaluator as evaluator
    import engine.training_profile_store as store
    from engine import train_mode

    monkeypatch.setattr(store, "NEED_PROFILES_PATH", tmp_path / "profiles.json")
    monkeypatch.setattr(dataset, "TRAINING_DATASET_PATH", tmp_path / "dataset.json")
    monkeypatch.setattr(evaluator, "TRAINING_EVALUATIONS_PATH", tmp_path / "evals.json")

    assert "Ultra training active" in train_mode.handle_training_command("train Jarvis deeply for sales")
    simulated = train_mode.handle_training_command("simulate training for sales")
    assert "Items: 10" in simulated
    evaluated = train_mode.handle_training_command("run training evaluation for sales")
    assert "Training evaluation complete" in evaluated
