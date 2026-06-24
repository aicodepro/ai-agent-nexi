from __future__ import annotations


def get_training_maturity(need: str) -> dict:
    level = 0
    try:
        from engine.training_rules import list_basic_rules
        if list_basic_rules():
            level = max(level, 1)
    except Exception:
        pass
    try:
        from engine.need_training_manager import list_need_profiles
        profiles = [p for p in list_need_profiles() if p.get("enabled", True) and p.get("need_name") == need]
        if profiles:
            level = max(level, 2)
            if profiles[0].get("examples"):
                level = max(level, 3)
    except Exception:
        pass
    try:
        from engine.training_dataset import list_dataset_items
        if list_dataset_items(need):
            level = max(level, 4)
    except Exception:
        pass
    try:
        from engine.training_evaluator import get_training_score, get_weak_areas
        score = get_training_score(need)
        if score.get("evaluation_count", 0):
            level = max(level, 5)
        if get_weak_areas(need):
            level = max(level, 6)
    except Exception:
        score = {"overall_score": 0.0, "evaluation_count": 0}
    return {"need": need, "level": level, "score": score.get("overall_score", 0.0), "evaluation_count": score.get("evaluation_count", 0)}


def recommend_next_training_step(need: str) -> dict:
    maturity = get_training_maturity(need)
    level = int(maturity.get("level", 0))
    steps = {
        0: "add a basic rule",
        1: "create a need profile",
        2: "save ideal and negative examples",
        3: "create a training dataset",
        4: "run training evaluation",
        5: "review weak areas",
        6: "apply safe improvements",
        7: "run live validation",
    }
    return {"need": need, "next_step": steps.get(level, "keep validating live behavior"), "maturity": maturity}


def build_training_curriculum(need: str) -> list[dict]:
    return [
        {"level": 1, "name": "Basic rules", "action": "when I say X, do Y"},
        {"level": 2, "name": "Need profile", "action": f"train Nexi for {need}"},
        {"level": 3, "name": "Examples", "action": "use this as ideal example"},
        {"level": 4, "name": "Dataset", "action": "create training dataset for this need"},
        {"level": 5, "name": "Evaluation", "action": "run training evaluation"},
        {"level": 6, "name": "Weak areas", "action": "show weak areas"},
        {"level": 8, "name": "Live validation", "action": "python run.py"},
    ]
