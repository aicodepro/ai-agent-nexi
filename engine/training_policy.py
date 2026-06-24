from __future__ import annotations

from engine.training_storage import read_json, training_path, write_json


TOOL_POLICIES_PATH = training_path("tool_policies.json")


def _load() -> dict:
    data = read_json(TOOL_POLICIES_PATH, {"policies": []})
    return data if isinstance(data, dict) and isinstance(data.get("policies"), list) else {"policies": []}


def _save(data: dict) -> None:
    write_json(TOOL_POLICIES_PATH, data)


def save_tool_policy(policy: dict) -> dict:
    clean = dict(policy or {})
    clean.setdefault("need", "general")
    clean.setdefault("tool", "")
    clean.setdefault("preference", "preferred")
    clean.setdefault("condition", "")
    clean.setdefault("confidence", 1.0)
    clean.setdefault("source", "training")
    data = _load()
    data["policies"].append(clean)
    data["policies"] = data["policies"][-200:]
    _save(data)
    return {"saved": True, "policy": clean}


def match_tool_policies(need: str, tool: str = "") -> list[dict]:
    policies = []
    for item in _load().get("policies", []):
        if item.get("need") == need and (not tool or item.get("tool") == tool):
            policies.append(dict(item))
    return policies


def apply_tool_policy(strategy: dict, policies: list[dict]) -> dict:
    updated = dict(strategy or {})
    preferred = [p.get("tool") for p in policies if p.get("preference") == "preferred" and p.get("tool")]
    blocked = [p.get("tool") for p in policies if p.get("preference") == "blocked" and p.get("tool")]
    if preferred:
        updated["tools_preferred"] = preferred
    if blocked:
        updated["tools_blocked"] = blocked
    return updated
