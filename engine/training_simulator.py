from __future__ import annotations

import re


def simulate_training_scenarios(need: str, count: int = 10) -> list[dict]:
    clean_need = re.sub(r"\s+", " ", str(need or "general").strip().lower()) or "general"
    templates = {
        "seo": ["SEO audit this page", "rank this page", "find technical SEO issues", "improve metadata", "create priority SEO fixes"],
        "coding": ["fix this code", "debug this failing test", "refactor this function", "create a small patch", "inspect files before editing"],
        "sales": ["write client follow up", "prepare sales call notes", "make this proposal concise", "create CTA", "handle objection"],
    }
    base = templates.get(clean_need, [f"{clean_need} task", f"improve {clean_need}", f"evaluate {clean_need}"])
    scenarios = []
    for index in range(max(1, int(count or 10))):
        text = base[index % len(base)]
        scenarios.append({"need": clean_need, "input": text, "expected_route": "brain", "expected_intent": "need_profile_task", "source": "simulation"})
    print(f"[ULTRA_TRAIN] simulation_created count={len(scenarios)}", flush=True)
    return scenarios


def simulate_and_store(need: str, count: int = 10) -> list[dict]:
    from engine.training_dataset import create_training_dataset_item
    stored = []
    for scenario in simulate_training_scenarios(need, count):
        result = create_training_dataset_item(scenario)
        if result.get("saved"):
            stored.append(result["item"])
    return stored
