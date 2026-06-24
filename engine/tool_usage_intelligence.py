from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


TOOL_HISTORY_PATH = Path(__file__).resolve().parents[1] / "data" / "memory" / "tool_usage_history.json"

BUILTIN_ALIASES = {
    "youtube": {"name": "open_website", "slots": {"url": "youtube.com"}, "confidence": 0.96},
    "gmail": {"name": "open_website", "slots": {"url": "gmail.com"}, "confidence": 0.94},
    "github": {"name": "open_website", "slots": {"url": "github.com"}, "confidence": 0.94},
    "chrome": {"name": "open_app", "slots": {"app_name": "chrome"}, "confidence": 0.95},
    "calculator": {"name": "open_app", "slots": {"app_name": "calculator"}, "confidence": 0.94},
    "notepad": {"name": "open_app", "slots": {"app_name": "notepad"}, "confidence": 0.94},
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower().rstrip(".?!"))


def _empty() -> dict[str, Any]:
    return {"tools": {}}


def _load() -> dict[str, Any]:
    try:
        if TOOL_HISTORY_PATH.exists():
            data = json.loads(TOOL_HISTORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("tools"), dict):
                return data
    except Exception:
        pass
    return _empty()


def _save(data: dict[str, Any]) -> None:
    TOOL_HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOOL_HISTORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def resolve_tool_alias(user_text: str, context: dict | None = None) -> dict:
    q = _norm(user_text)
    if q in BUILTIN_ALIASES:
        alias = dict(BUILTIN_ALIASES[q])
        print(f"[TOOL_AI] alias_resolved input={q} tool={alias['name']}", flush=True)
        print(f"[TOOL_AI] confidence={alias['confidence']:.2f}", flush=True)
        return {"handled": True, **alias, "reason": "built_in_alias"}
    try:
        from engine.training_rules import apply_training_rule, match_training_rules
        matches = match_training_rules(user_text, context or {})
        for rule in matches:
            strategy = apply_training_rule(rule, {"confidence": 0.0, "slots": {}})
            intent = strategy.get("chosen_intent")
            if strategy.get("chosen_route") == "tool" and intent in {"open_website", "open_app", "web_search"}:
                name = intent
                print(f"[TOOL_AI] alias_resolved input={q} tool={name}", flush=True)
                print(f"[TOOL_AI] confidence={float(strategy.get('confidence', 0.95)):.2f}", flush=True)
                return {
                    "handled": True,
                    "name": name,
                    "slots": dict(strategy.get("slots") or {}),
                    "confidence": float(strategy.get("confidence", 0.95)),
                    "reason": strategy.get("reason", "learned_rule"),
                    "learned_rules_used": strategy.get("learned_rules_used", []),
                }
    except Exception:
        pass
    return {"handled": False}


def record_tool_result(tool_name: str, slots: dict | None, result: dict | None) -> dict:
    data = _load()
    name = str(tool_name or "unknown")
    entry = data["tools"].setdefault(name, {"success_count": 0, "failure_count": 0, "last_used_at": "", "recent_failures": []})
    success = bool(result and result.get("success") is True)
    entry["last_used_at"] = _now()
    if success:
        entry["success_count"] = int(entry.get("success_count", 0)) + 1
    else:
        entry["failure_count"] = int(entry.get("failure_count", 0)) + 1
        reason = str((result or {}).get("message") or "unverified")[:160]
        entry.setdefault("recent_failures", []).append({"reason": reason, "at": entry["last_used_at"]})
        entry["recent_failures"] = entry["recent_failures"][-10:]
    _save(data)
    print(f"[TOOL_AI] result_verified={str(success).lower()}", flush=True)
    return {"recorded": True, "success": success, "tool": name}


def get_tool_confidence(tool_name: str) -> float:
    entry = _load().get("tools", {}).get(tool_name, {})
    success = int(entry.get("success_count", 0))
    failure = int(entry.get("failure_count", 0))
    total = success + failure
    if total == 0:
        return 0.90
    return max(0.2, min(0.99, 0.5 + (success / total) * 0.49))


def summarize_tool_lessons(limit: int = 5) -> str:
    tools = _load().get("tools", {})
    failures = []
    for name, entry in tools.items():
        if int(entry.get("failure_count", 0)):
            failures.append(f"{name}: {entry.get('failure_count')} failures")
    return "; ".join(failures[:limit])


def count_tool_failure_lessons() -> int:
    return sum(1 for entry in _load().get("tools", {}).values() if int(entry.get("failure_count", 0)) > 0)
