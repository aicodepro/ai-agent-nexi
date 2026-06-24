from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from engine.training_storage import read_json, training_path, write_json


TRAINING_EVALUATIONS_PATH = training_path("training_evaluations.json")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {"evaluations": []}


def _load() -> dict[str, Any]:
    data = read_json(TRAINING_EVALUATIONS_PATH, _empty())
    return data if isinstance(data, dict) and isinstance(data.get("evaluations"), list) else _empty()


def _save(data: dict[str, Any]) -> None:
    write_json(TRAINING_EVALUATIONS_PATH, data)


def evaluate_strategy_against_dataset(strategy: dict, dataset_item: dict) -> dict:
    route_score = 1.0 if strategy.get("chosen_route") == dataset_item.get("expected_route") else 0.6
    intent_score = 1.0 if strategy.get("chosen_intent") == dataset_item.get("expected_intent") else 0.6
    tool_score = 1.0
    answer_score = 0.8
    safety_score = 1.0 if "conscious" not in str(strategy).lower() else 0.0
    overall = round((route_score + intent_score + tool_score + answer_score + safety_score) / 5, 2)
    failures = []
    if route_score < 1.0:
        failures.append("route_mismatch")
    if intent_score < 1.0:
        failures.append("intent_mismatch")
    result = {
        "id": "eval_" + hashlib.sha1(f"{dataset_item.get('id','')}:{_now()}".encode("utf-8")).hexdigest()[:12],
        "dataset_item_id": dataset_item.get("id", ""),
        "need": dataset_item.get("need", ""),
        "route_score": route_score,
        "intent_score": intent_score,
        "tool_score": tool_score,
        "answer_score": answer_score,
        "safety_score": safety_score,
        "overall_score": overall,
        "failure_reasons": failures,
        "recommended_improvements": ["Add profile alias or rule" for _ in failures][:1],
        "created_at": _now(),
    }
    print(f"[ULTRA_TRAIN] evaluation score={overall:.2f}", flush=True)
    return result


def evaluate_last_response(user_text: str, assistant_text: str, result: dict) -> dict:
    safe = 0.0 if "i am conscious" in str(assistant_text).lower() else 1.0
    concise = 1.0 if len(str(assistant_text or "")) < 1200 else 0.6
    verified = 1.0 if not result.get("tool") or result.get("success") is True else 0.5
    overall = round((safe + concise + verified) / 3, 2)
    evaluation = {
        "id": "eval_last_" + hashlib.sha1(f"{user_text}:{_now()}".encode("utf-8")).hexdigest()[:12],
        "dataset_item_id": "",
        "need": result.get("need", ""),
        "route_score": 0.8,
        "intent_score": 0.8,
        "tool_score": verified,
        "answer_score": concise,
        "safety_score": safe,
        "overall_score": overall,
        "failure_reasons": [] if overall >= 0.8 else ["answer_quality"],
        "recommended_improvements": [] if overall >= 0.8 else ["Tighten response or verify tool result"],
        "created_at": _now(),
    }
    _append_evaluation(evaluation)
    return evaluation


def _append_evaluation(evaluation: dict) -> None:
    data = _load()
    data["evaluations"].append(evaluation)
    data["evaluations"] = data["evaluations"][-500:]
    _save(data)


def run_training_evaluation(need: str | None = None) -> dict:
    from engine.realtime_cognitive_engine import analyze_input
    from engine.training_dataset import build_dataset_from_profile, list_dataset_items
    items = list_dataset_items(need)
    if not items and need:
        items = build_dataset_from_profile(need)
    evaluations = []
    for item in items[:20]:
        strategy = analyze_input(item.get("input", ""), source="training_eval")
        evaluation = evaluate_strategy_against_dataset(strategy, item)
        _append_evaluation(evaluation)
        evaluations.append(evaluation)
    score = round(sum(e["overall_score"] for e in evaluations) / len(evaluations), 2) if evaluations else 0.0
    return {"need": need or "all", "count": len(evaluations), "overall_score": score, "evaluations": evaluations}


def list_evaluations(need: str | None = None) -> list[dict]:
    evaluations = [dict(item) for item in _load().get("evaluations", [])]
    if need:
        evaluations = [item for item in evaluations if item.get("need") == need]
    return evaluations


def get_training_score(need: str | None = None) -> dict:
    evaluations = list_evaluations(need)
    score = round(sum(e.get("overall_score", 0.0) for e in evaluations) / len(evaluations), 2) if evaluations else 0.0
    return {"need": need or "all", "evaluation_count": len(evaluations), "overall_score": score}


def get_weak_areas(need: str | None = None) -> list[dict]:
    counts: dict[str, int] = {}
    for evaluation in list_evaluations(need):
        for reason in evaluation.get("failure_reasons", []) or []:
            counts[reason] = counts.get(reason, 0) + 1
    weak = [{"area": key, "count": value} for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)]
    for item in weak[:3]:
        print(f"[ULTRA_TRAIN] weak_area={item['area']}", flush=True)
    return weak
