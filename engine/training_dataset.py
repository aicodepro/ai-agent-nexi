from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any

from engine.training_safety import is_safe_training_item, redact_training_text
from engine.training_storage import read_json, training_path, write_json


TRAINING_DATASET_PATH = training_path("training_dataset.json")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {"items": []}


def _load() -> dict[str, Any]:
    data = read_json(TRAINING_DATASET_PATH, _empty())
    return data if isinstance(data, dict) and isinstance(data.get("items"), list) else _empty()


def _save(data: dict[str, Any]) -> None:
    write_json(TRAINING_DATASET_PATH, data)


def _id(item: dict) -> str:
    seed = f"{item.get('need','')}:{item.get('input','')}:{item.get('expected_intent','')}"
    return "td_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def create_training_dataset_item(item: dict) -> dict:
    clean = dict(item or {})
    clean["input"] = redact_training_text(clean.get("input", ""))[:800]
    if not is_safe_training_item(clean) or not clean.get("input"):
        return {"saved": False, "reason": "unsafe_or_empty"}
    clean.setdefault("level", "ultra")
    clean.setdefault("need", "general")
    clean.setdefault("expected_route", "brain")
    clean.setdefault("expected_intent", "general_qa")
    clean.setdefault("expected_tools", [])
    clean.setdefault("ideal_answer_traits", [])
    clean.setdefault("bad_answer_traits", [])
    clean.setdefault("success_criteria", [])
    clean.setdefault("source", "manual")
    clean.setdefault("created_at", _now())
    clean.setdefault("last_tested_at", "")
    clean.setdefault("score", None)
    clean["id"] = clean.get("id") or _id(clean)
    data = _load()
    for index, existing in enumerate(data["items"]):
        if existing.get("id") == clean["id"]:
            data["items"][index] = {**existing, **clean}
            _save(data)
            print(f"[ULTRA_TRAIN] dataset_item_saved id={clean['id']}", flush=True)
            return {"saved": True, "item": data["items"][index]}
    data["items"].append(clean)
    data["items"] = data["items"][-500:]
    _save(data)
    print(f"[ULTRA_TRAIN] dataset_item_saved id={clean['id']}", flush=True)
    return {"saved": True, "item": clean}


def list_dataset_items(need: str | None = None) -> list[dict]:
    items = [dict(item) for item in _load().get("items", [])]
    if need:
        items = [item for item in items if str(item.get("need", "")).lower() == str(need).lower()]
    return items


def build_dataset_from_profile(need: str) -> list[dict]:
    from engine.need_training_manager import list_need_profiles
    profiles = [p for p in list_need_profiles() if p.get("enabled", True) and p.get("need_name") == need]
    created = []
    for profile in profiles[:1]:
        for alias in profile.get("aliases", [])[:5]:
            result = create_training_dataset_item({
                "need": need,
                "input": alias,
                "expected_route": "brain",
                "expected_intent": "need_profile_task",
                "ideal_answer_traits": profile.get("rules", [])[:6],
                "success_criteria": profile.get("success_criteria", [])[:6],
                "source": "profile",
            })
            if result.get("saved"):
                created.append(result["item"])
    return created
