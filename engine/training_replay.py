from __future__ import annotations


def replay_training_dataset(need: str | None = None) -> dict:
    from engine.training_evaluator import run_training_evaluation
    return run_training_evaluation(need)


def rollback_training(version_or_time: str) -> dict:
    print(f"[ULTRA_TRAIN] rollback version={version_or_time}", flush=True)
    return {"rolled_back": False, "reason": "No rollback snapshot selected.", "version": version_or_time}
