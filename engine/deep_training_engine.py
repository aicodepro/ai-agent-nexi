from __future__ import annotations


_ultra_need = ""


def start_ultra_training(need: str | None = None) -> dict:
    global _ultra_need
    _ultra_need = (need or "general").strip().lower() or "general"
    print(f"[ULTRA_TRAIN] started need={_ultra_need}", flush=True)
    return {"started": True, "need": _ultra_need, "message": f"Ultra training active for {_ultra_need}."}


def get_active_ultra_need() -> str:
    return _ultra_need


def create_training_dataset_item(item: dict) -> dict:
    from engine.training_dataset import create_training_dataset_item as create_item
    return create_item(item)


def build_dataset_from_profile(need: str) -> list[dict]:
    from engine.training_dataset import build_dataset_from_profile as build
    return build(need)


def simulate_training_scenarios(need: str, count: int = 10) -> list[dict]:
    from engine.training_simulator import simulate_training_scenarios as simulate
    return simulate(need, count)


def evaluate_strategy_against_dataset(strategy: dict, dataset_item: dict) -> dict:
    from engine.training_evaluator import evaluate_strategy_against_dataset as evaluate
    return evaluate(strategy, dataset_item)


def evaluate_last_response(user_text: str, assistant_text: str, result: dict) -> dict:
    from engine.training_evaluator import evaluate_last_response as evaluate
    return evaluate(user_text, assistant_text, result)


def run_training_evaluation(need: str | None = None) -> dict:
    from engine.training_evaluator import run_training_evaluation as run
    return run(need or _ultra_need or None)


def promote_rule(rule_id: str) -> dict:
    from engine.training_rules import list_rules, save_rule
    for rule in list_rules():
        if rule.get("id") == rule_id:
            rule["confidence"] = min(1.0, float(rule.get("confidence", 1.0)) + 0.1)
            save_rule(rule)
            print(f"[ULTRA_TRAIN] rule_promoted id={rule_id}", flush=True)
            return {"promoted": True, "rule": rule}
    return {"promoted": False, "reason": "rule_not_found"}


def demote_rule(rule_id: str, reason: str = "") -> dict:
    from engine.training_rules import list_rules, save_rule
    for rule in list_rules():
        if rule.get("id") == rule_id:
            rule["confidence"] = max(0.0, float(rule.get("confidence", 1.0)) - 0.1)
            rule["demotion_reason"] = reason
            save_rule(rule)
            return {"demoted": True, "rule": rule}
    return {"demoted": False, "reason": "rule_not_found"}


def rollback_training(version_or_time: str) -> dict:
    from engine.training_replay import rollback_training as rollback
    return rollback(version_or_time)


def get_training_score(need: str | None = None) -> dict:
    from engine.training_evaluator import get_training_score as score
    return score(need or _ultra_need or None)


def get_weak_areas(need: str | None = None) -> list[dict]:
    from engine.training_evaluator import get_weak_areas as weak
    return weak(need or _ultra_need or None)
