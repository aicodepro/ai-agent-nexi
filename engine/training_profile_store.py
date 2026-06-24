from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any

from engine.training_storage import read_json, training_path, write_json


NEED_PROFILES_PATH = training_path("need_profiles.json")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {"profiles": []}


def _load() -> dict[str, Any]:
    data = read_json(NEED_PROFILES_PATH, _empty())
    return data if isinstance(data, dict) and isinstance(data.get("profiles"), list) else _empty()


def _save(data: dict[str, Any]) -> None:
    write_json(NEED_PROFILES_PATH, data)


def normalize_need(need: str) -> str:
    return " ".join(str(need or "").strip().lower().replace("_", " ").split())


def profile_id(need: str) -> str:
    return "profile_" + normalize_need(need).replace(" ", "_")[:64]


def _merge_list(existing: list, incoming: list, limit: int = 40) -> list:
    merged = []
    seen = set()
    for item in (existing or []) + (incoming or []):
        try:
            key = json.dumps(item, sort_keys=True)
        except TypeError:
            key = str(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged[-limit:]


def upsert_profile(profile: dict) -> dict:
    data = _load()
    now = _now()
    clean = dict(profile or {})
    need = normalize_need(clean.get("need_name") or clean.get("need") or "general")
    clean.setdefault("level", "medium")
    clean["need_name"] = need
    clean["id"] = clean.get("id") or profile_id(need)
    clean["updated_at"] = now
    clean.setdefault("created_at", now)
    clean.setdefault("last_used_at", "")
    clean.setdefault("use_count", 0)
    clean.setdefault("enabled", True)
    for index, existing in enumerate(data["profiles"]):
        if existing.get("id") == clean["id"] or normalize_need(existing.get("need_name")) == need:
            merged = dict(existing)
            for key, value in clean.items():
                if isinstance(value, list):
                    merged[key] = _merge_list(merged.get(key) or [], value)
                elif value not in ("", None) and not (isinstance(value, list) and not value):
                    merged[key] = value
            data["profiles"][index] = merged
            _save(data)
            print(f"[NEED_TRAINING] profile_saved need={need}", flush=True)
            return dict(merged)
    data["profiles"].append(clean)
    data["profiles"] = data["profiles"][-100:]
    _save(data)
    print(f"[NEED_TRAINING] profile_saved need={need}", flush=True)
    return dict(clean)


def list_profiles(enabled_only: bool = False) -> list[dict]:
    profiles = [dict(item) for item in _load().get("profiles", [])]
    if enabled_only:
        profiles = [item for item in profiles if item.get("enabled", True)]
    return profiles


def disable_profile(query: str) -> dict:
    needle = normalize_need(query)
    data = _load()
    count = 0
    for profile in data.get("profiles", []):
        haystack = " ".join([profile.get("need_name", ""), " ".join(profile.get("aliases", []) or [])]).lower()
        if needle and needle in haystack:
            profile["enabled"] = False
            profile["updated_at"] = _now()
            count += 1
    if count:
        _save(data)
    return {"disabled": count}


def mark_profile_used(profile_id_value: str) -> None:
    data = _load()
    now = _now()
    changed = False
    for profile in data.get("profiles", []):
        if profile.get("id") == profile_id_value:
            profile["last_used_at"] = now
            profile["use_count"] = int(profile.get("use_count", 0)) + 1
            changed = True
            break
    if changed:
        _save(data)
