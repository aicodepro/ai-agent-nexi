from __future__ import annotations

import hashlib
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive
from engine.training_safety import validate_training_rule
from engine.training_storage import read_json, write_json


TRAINING_RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "memory" / "training_rules.json"
RULE_TYPES = {"intent_rule", "tool_rule", "style_rule", "output_rule", "workflow_rule", "correction"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower().strip("'\" .?!"))


def _safe(text: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", redact_sensitive(str(text or ""))).strip()
    safe, _reason = is_safe_to_store(value)
    return value[:limit] if safe else ""


def _empty() -> dict[str, Any]:
    return {"rules": []}


def _load() -> dict[str, Any]:
    data = read_json(TRAINING_RULES_PATH, _empty())
    return data if isinstance(data, dict) and isinstance(data.get("rules"), list) else _empty()


def _save(data: dict[str, Any]) -> None:
    write_json(TRAINING_RULES_PATH, data, backup=True)


def _rule_id(rule_type: str, trigger: str, action: str) -> str:
    digest = hashlib.sha1(f"{rule_type}:{_norm(trigger)}:{_norm(action)}".encode("utf-8")).hexdigest()[:12]
    return f"rule_{digest}"


def parse_training_instruction(text: str) -> dict:
    value = _safe(text)
    if not value:
        return {"parsed": False, "reason": "unsafe_or_empty"}
    q = _norm(value)
    patterns = [
        (r"^when i say (.+?),?\s+(?:please\s+)?(?:do |use |run |open )?(.+)$", "tool_rule"),
        (r"^whenever i ask (.+?),?\s+(?:please\s+)?(?:do |use |run |open )?(.+)$", "intent_rule"),
    ]
    for pattern, rule_type in patterns:
        match = re.match(pattern, q, re.I)
        if match:
            trigger = _safe(match.group(1), 120)
            action = _safe(match.group(2), 240)
            if action and not action.startswith(("open ", "search ", "google ", "use ", "route ")):
                if "." in action or action in {"youtube", "gmail", "github"}:
                    action = "open " + action
            return _build_rule(rule_type, trigger, action, [value])
    if q.startswith("always "):
        return _build_rule("style_rule", "always", _safe(value[7:], 240), [value])
    if q.startswith("never "):
        return _build_rule("correction", "never", _safe(value[6:], 240), [value])
    if q.startswith("next time "):
        return _build_rule("correction", "next time", _safe(value[10:], 240), [value])
    if q in {"this is wrong", "correct this", "learn this", "learn from this"}:
        return _build_rule("correction", q, q, [value])
    return {"parsed": False, "reason": "no_training_pattern"}


def parse_rule(text: str) -> dict:
    return parse_training_instruction(text)


def parse_basic_training_rule(text: str) -> dict:
    return parse_training_instruction(text)


def _build_rule(rule_type: str, trigger: str, action: str, examples: list[str]) -> dict:
    safe_type = rule_type if rule_type in RULE_TYPES else "correction"
    trigger = _safe(trigger, 160).strip(" ,")
    action = _safe(action, 300).strip(" ,")
    if not trigger or not action:
        return {"parsed": False, "reason": "missing_trigger_or_action"}
    now = _now()
    return {
        "parsed": True,
        "id": _rule_id(safe_type, trigger, action),
        "type": safe_type,
        "trigger": trigger,
        "condition": "",
        "action": action,
        "examples": examples[-5:],
        "confidence": 1.0,
        "created_at": now,
        "last_used_at": "",
        "use_count": 0,
        "enabled": True,
    }


def save_training_rule(rule: dict) -> dict:
    if not rule or rule.get("parsed") is False:
        return {"stored": False, "reason": rule.get("reason", "invalid_rule") if isinstance(rule, dict) else "invalid_rule"}
    data = _load()
    clean_rule = {k: v for k, v in rule.items() if k != "parsed"}
    validated = validate_training_rule(clean_rule)
    if not validated.get("valid"):
        return {"stored": False, "reason": validated.get("reason", "unsafe_training_item")}
    clean_rule = validated["rule"]
    clean_rule["type"] = clean_rule.get("type") if clean_rule.get("type") in RULE_TYPES else "correction"
    clean_rule["id"] = clean_rule.get("id") or _rule_id(clean_rule["type"], clean_rule.get("trigger", ""), clean_rule.get("action", ""))
    for existing in data["rules"]:
        if existing.get("id") == clean_rule["id"]:
            existing.update(clean_rule)
            existing["enabled"] = True
            _save(data)
            print(f"[TRAIN] rule_saved type={existing.get('type')}", flush=True)
            return {"stored": True, "rule": dict(existing), "updated": True}
    data["rules"].append(clean_rule)
    data["rules"] = data["rules"][-200:]
    _save(data)
    print(f"[TRAIN] rule_saved type={clean_rule.get('type')}", flush=True)
    return {"stored": True, "rule": dict(clean_rule), "updated": False}


def save_rule(rule: dict) -> dict:
    return save_training_rule(rule)


def save_basic_rule(rule: dict) -> dict:
    return save_training_rule(rule)


def list_training_rules() -> list[dict]:
    return [dict(rule) for rule in _load().get("rules", [])]


def list_rules() -> list[dict]:
    return list_training_rules()


def list_basic_rules() -> list[dict]:
    return list_training_rules()


def _matches(rule: dict, user_text: str) -> bool:
    trigger = _norm(rule.get("trigger", ""))
    q = _norm(user_text)
    if not trigger or not q:
        return False
    if trigger in {"always", "never", "next time"}:
        return False
    return q == trigger or (len(trigger) > 5 and trigger in q)


def match_training_rules(user_text: str, context: dict | None = None) -> list[dict]:
    data = _load()
    matched = []
    now = _now()
    for rule in data.get("rules", []):
        if not rule.get("enabled", True):
            continue
        if _matches(rule, user_text):
            rule["last_used_at"] = now
            rule["use_count"] = int(rule.get("use_count", 0)) + 1
            matched.append(dict(rule))
            print(f"[TRAIN] rule_matched id={rule.get('id')}", flush=True)
    if matched:
        _save(data)
    return matched


def match_rules(user_text: str, context: dict | None = None) -> list[dict]:
    return match_training_rules(user_text, context)


def match_basic_rules(user_text: str, context: dict | None = None) -> list[dict]:
    return match_training_rules(user_text, context)


def apply_training_rule(rule: dict, strategy: dict) -> dict:
    updated = dict(strategy or {})
    action = _norm(rule.get("action", ""))
    slots = dict(updated.get("slots") or {})
    if action.startswith("open "):
        target = action[5:].strip()
        if target in {"youtube", "youtube.com"}:
            target = "youtube.com"
        if "." in target or target in {"gmail", "github"}:
            updated.update({"chosen_route": "tool", "chosen_intent": "open_website", "route": "tool", "intent": "open_website"})
            slots["url"] = target
        else:
            updated.update({"chosen_route": "tool", "chosen_intent": "open_app", "route": "tool", "intent": "open_app"})
            slots["app_name"] = target
    elif action.startswith(("search ", "google ")):
        query = action.split(" ", 1)[1].strip()
        updated.update({"chosen_route": "tool", "chosen_intent": "web_search", "route": "tool", "intent": "web_search"})
        slots["query"] = query
    else:
        updated.update({"chosen_route": "training", "chosen_intent": rule.get("type", "correction"), "route": "training", "intent": rule.get("type", "correction")})
    used = list(updated.get("learned_rules_used") or [])
    if rule.get("id") not in used:
        used.append(rule.get("id"))
    updated["slots"] = slots
    updated["confidence"] = max(float(updated.get("confidence", 0.0) or 0.0), float(rule.get("confidence", 1.0) or 1.0))
    updated["learned_rules_used"] = used
    updated["reason"] = f"learned rule maps {rule.get('trigger')} to {rule.get('action')}"
    print(f"[TRAIN] rule_applied id={rule.get('id')}", flush=True)
    return updated


def apply_rules(strategy: dict, rules: list[dict]) -> dict:
    updated = dict(strategy or {})
    for rule in rules or []:
        updated = apply_training_rule(rule, updated)
    return updated


def apply_basic_rules(strategy: dict, rules: list[dict]) -> dict:
    return apply_rules(strategy, rules)


def disable_training_rule(rule_id_or_query: str) -> dict:
    needle = _norm(rule_id_or_query)
    data = _load()
    disabled = 0
    for rule in data.get("rules", []):
        haystack = " ".join([str(rule.get("id", "")), str(rule.get("trigger", "")), str(rule.get("action", ""))]).lower()
        if needle and needle in haystack:
            rule["enabled"] = False
            disabled += 1
    if disabled:
        _save(data)
    return {"disabled": disabled}


def forget_rule(rule_id_or_query: str) -> dict:
    return disable_training_rule(rule_id_or_query)


def forget_basic_rule(rule_id_or_query: str) -> dict:
    return disable_training_rule(rule_id_or_query)


def format_rule_summary(limit: int = 8) -> str:
    rules = [r for r in list_training_rules() if r.get("enabled", True)]
    if not rules:
        return "No active training rules yet."
    chunks = [f"{r.get('trigger')} -> {r.get('action')}" for r in rules[-limit:]]
    return "Training rules: " + "; ".join(chunks)


def get_relevant_training_context(user_text: str = "", limit: int = 5, max_chars: int = 800) -> str:
    matched = match_training_rules(user_text, {}) if user_text else []
    rules = matched or [r for r in list_training_rules() if r.get("enabled", True)][-limit:]
    lines = [f"- {r.get('trigger')} -> {r.get('action')}" for r in rules[:limit]]
    return "\n".join(lines)[:max_chars]
