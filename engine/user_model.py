from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive


USER_MODEL_PATH = Path(__file__).resolve().parents[1] / "data" / "memory" / "user_model.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict[str, Any]:
    return {
        "preferences": {},
        "preferred_tools": {},
        "common_apps_sites": {},
        "project_names": {},
        "correction_patterns": [],
        "repeated_commands": {},
        "debugging_preference": "",
        "demo_preference": "",
    }


def _load() -> dict[str, Any]:
    try:
        if USER_MODEL_PATH.exists():
            data = json.loads(USER_MODEL_PATH.read_text(encoding="utf-8"))
            base = _empty()
            if isinstance(data, dict):
                for key in base:
                    if key in data:
                        base[key] = data[key]
            return base
    except Exception:
        pass
    return _empty()


def _save(data: dict[str, Any]) -> None:
    USER_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_MODEL_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _clean(text: str, limit: int = 400) -> str:
    value = re.sub(r"\s+", " ", redact_sensitive(str(text or ""))).strip()
    safe, _reason = is_safe_to_store(value)
    return value[:limit] if safe else ""


def infer_user_preference(user_text: str) -> dict | None:
    value = _clean(user_text)
    if not value:
        return None
    q = value.lower()
    if any(phrase in q for phrase in ("keep answers short", "short answers", "short and direct", "be concise")):
        return {"type": "preference", "key": "response_length", "value": "short", "source_text": value}
    if any(phrase in q for phrase in ("long answers in the workspace", "use the workspace", "open long answers in the box")):
        return {"type": "preference", "key": "output_destination", "value": "workspace", "source_text": value}
    if "debug" in q and any(word in q for word in ("commands", "logs", "first")):
        return {"type": "preference", "key": "debugging_preference", "value": "commands_and_logs_first", "source_text": value}
    if q.startswith(("no,", "actually", "that's wrong", "that is wrong", "this is wrong")):
        return {"type": "correction", "key": "correction", "value": value, "source_text": value}
    return None


def update_user_model(event: dict) -> dict:
    data = _load()
    event_type = str(event.get("type") or "preference")
    key = _clean(event.get("key") or event.get("name") or event_type, 120)
    value = _clean(event.get("value") or event.get("text") or event.get("source_text") or "")
    if not key or not value:
        return {"updated": False, "reason": "unsafe_or_empty"}
    now = _now()
    if event_type == "preference":
        data["preferences"][key] = {"value": value, "updated_at": now}
    elif event_type == "common_app_site":
        item = data["common_apps_sites"].setdefault(key, {"count": 0, "value": value, "updated_at": now})
        item["count"] = int(item.get("count", 0)) + 1
        item["value"] = value
        item["updated_at"] = now
    elif event_type == "repeated_command":
        item = data["repeated_commands"].setdefault(value.lower(), {"count": 0, "updated_at": now})
        item["count"] = int(item.get("count", 0)) + 1
        item["updated_at"] = now
    elif event_type == "correction":
        data["correction_patterns"].append({"text": value, "updated_at": now})
        data["correction_patterns"] = data["correction_patterns"][-50:]
    elif key == "debugging_preference":
        data["debugging_preference"] = value
    else:
        data["preferences"][key] = {"value": value, "updated_at": now}
    _save(data)
    print(f"[USER_MODEL] updated type={event_type}", flush=True)
    return {"updated": True, "type": event_type, "key": key, "value": value}


def get_user_model_context(max_chars: int = 1200) -> str:
    data = _load()
    lines = []
    for key, item in sorted(data.get("preferences", {}).items()):
        if isinstance(item, dict) and item.get("value"):
            lines.append(f"- preference {key}: {item['value']}")
    if data.get("debugging_preference"):
        lines.append(f"- debugging preference: {data['debugging_preference']}")
    for key, item in sorted(data.get("common_apps_sites", {}).items()):
        lines.append(f"- common target {key}: {item.get('value', key)}")
    corrections = data.get("correction_patterns", [])[-3:]
    for item in corrections:
        lines.append(f"- correction: {item.get('text', '')}")
    return "\n".join(line for line in lines if line.strip())[:max_chars]


def apply_user_model_to_strategy(strategy: dict) -> dict:
    data = _load()
    updated = dict(strategy or {})
    applied = []
    response_pref = data.get("preferences", {}).get("response_length", {})
    if response_pref.get("value") == "short":
        updated["response_style"] = "short"
        applied.append("response_length")
    output_pref = data.get("preferences", {}).get("output_destination", {})
    if output_pref.get("value"):
        updated["output_destination"] = output_pref.get("value")
        applied.append("output_destination")
    updated["applied_user_preferences"] = applied
    print(f"[USER_MODEL] applied preferences={len(applied)}", flush=True)
    return updated


def count_preferences() -> int:
    data = _load()
    return len(data.get("preferences", {})) + len(data.get("correction_patterns", []))
