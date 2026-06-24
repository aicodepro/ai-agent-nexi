from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


RULES_PATH = Path(__file__).resolve().parents[1] / "data" / "memory" / "correction_rules.json"
_ACTION_VERBS = ("open", "launch", "search", "go to", "navigate to", "copy", "save", "create", "make", "do")


def _norm(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return cleaned.strip(" .?!\"'")


def _safe_text(value: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())[:limit]
    try:
        from engine.memory_safety import is_safe_to_store, redact_sensitive

        redacted = redact_sensitive(text)
        safe, _reason = is_safe_to_store(redacted)
        return redacted if safe else ""
    except Exception:
        return text


def parse_correction(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    lower = raw.lower().strip()
    if not lower.startswith(("wrong", "no,", "no ", "incorrect", "that's wrong", "that is wrong")):
        return {"parsed": False}
    marker = re.search(r"when\s+i\s+say\s+", raw, flags=re.I)
    if not marker:
        return {"parsed": False}
    tail = raw[marker.end():].strip(" ,:;")
    if not tail:
        return {"parsed": False}

    if "," in tail:
        trigger_part, action_part = tail.split(",", 1)
        trigger = _safe_text(trigger_part)
        action = _safe_text(action_part)
    else:
        trigger = ""
        action = ""
        tail_lower = tail.lower()
        for verb in _ACTION_VERBS:
            needle = f" {verb} "
            idx = tail_lower.find(needle)
            if idx > 0:
                trigger = _safe_text(tail[:idx])
                action = _safe_text(tail[idx + 1:])
                break
    if not trigger or not action:
        return {"parsed": False}
    return {"parsed": True, "trigger": trigger, "action": action, "trigger_norm": _norm(trigger)}


def load_correction_rules() -> list[dict[str, Any]]:
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        rules = data.get("rules", []) if isinstance(data, dict) else []
        return [rule for rule in rules if isinstance(rule, dict)]
    except Exception:
        return []


def save_correction_rule(parsed: dict[str, Any]) -> dict[str, Any]:
    if not parsed.get("parsed"):
        return {"stored": False, "reason": "not_a_correction"}
    trigger = _safe_text(str(parsed.get("trigger") or ""))
    action = _safe_text(str(parsed.get("action") or ""))
    if not trigger or not action:
        return {"stored": False, "reason": "unsafe_or_empty"}
    trigger_norm = _norm(trigger)
    rule_id = hashlib.sha256(f"{trigger_norm}\n{_norm(action)}".encode("utf-8")).hexdigest()[:16]
    rule = {
        "id": rule_id,
        "trigger": trigger,
        "trigger_norm": trigger_norm,
        "action": action,
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
    rules = [existing for existing in load_correction_rules() if existing.get("trigger_norm") != trigger_norm]
    rules.append(rule)
    rules = rules[-100:]
    try:
        RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
        RULES_PATH.write_text(json.dumps({"schema_version": "1.0", "rules": rules}, indent=2), encoding="utf-8")
    except Exception as exc:
        return {"stored": False, "reason": type(exc).__name__}
    try:
        from engine.reflection_memory import ReflectionMemory
        ReflectionMemory.store_lesson(
            failure=f"Incorrect behavior for trigger: {trigger}",
            lesson=f"When the user says '{trigger}', apply: {action}",
            next_action=action,
            context=f"correction trigger={trigger}",
            intent="correction_rule",
            tool_name="correction_learner",
        )
    except Exception:
        pass
    print("[CORRECTION] stored=true", flush=True)
    return {"stored": True, "rule": rule}


def record_correction_from_text(text: str) -> dict[str, Any]:
    return save_correction_rule(parse_correction(text))


def apply_correction(text: str) -> dict[str, Any]:
    query_norm = _norm(text)
    if not query_norm:
        return {"matched": False}
    for rule in reversed(load_correction_rules()):
        if rule.get("trigger_norm") == query_norm:
            print("[CORRECTION] applied=true", flush=True)
            return {"matched": True, "rule": rule, "action_text": str(rule.get("action") or "")}
    return {"matched": False}
