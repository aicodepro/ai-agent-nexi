"""User model — learns preferences, corrections, and frequently used targets."""

import json
import re
from datetime import datetime
from pathlib import Path
from memory.safety import is_safe_to_store, redact_sensitive

USER_MODEL_PATH = Path(__file__).resolve().parent.parent / "data" / "user_model.json"


def _now() -> str:
    return datetime.now().isoformat()


def _empty() -> dict:
    return {
        "preferences": [], "common_apps": [], "common_sites": [],
        "corrections": [], "repeated_commands": [],
    }


def _load() -> dict:
    try:
        if USER_MODEL_PATH.exists():
            return json.loads(USER_MODEL_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return _empty()


def _save(data: dict) -> None:
    USER_MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_MODEL_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def infer_user_preference(user_text: str) -> dict | None:
    lower = user_text.lower().strip()
    patterns = [
        (r"keep (?:answers?|responses?) (short|brief|concise)", "response_length", "short"),
        (r"give (?:me )?(detailed|long|verbose) (?:answers?|responses?)", "response_length", "long"),
        (r"(?:always |)show (?:output |results? )?in (?:the )?workspace", "output_destination", "workspace"),
        (r"(?:don't|do not) use workspace", "output_destination", "main_ui"),
    ]
    for pattern, pref_type, value in patterns:
        if re.search(pattern, lower):
            return {"type": pref_type, "value": value, "source": "inferred", "timestamp": _now()}
    return None


def update_user_model(event: dict) -> None:
    data = _load()
    etype = event.get("type", "")

    if etype == "preference":
        text = redact_sensitive(event.get("text", ""))
        if text and is_safe_to_store(text):
            data.setdefault("preferences", []).append({
                "text": text[:200], "value": event.get("value", ""),
                "timestamp": _now(),
            })
            if len(data["preferences"]) > 50:
                data["preferences"] = data["preferences"][-50:]

    elif etype == "common_app":
        name = event.get("name", "").lower()
        for app in data.get("common_apps", []):
            if app.get("name") == name:
                app["count"] = app.get("count", 0) + 1
                _save(data)
                return
        data.setdefault("common_apps", []).append({"name": name, "count": 1})

    elif etype == "correction":
        text = redact_sensitive(event.get("text", ""))
        if text and is_safe_to_store(text):
            data.setdefault("corrections", []).append({
                "text": text[:200], "timestamp": _now(),
            })
            if len(data["corrections"]) > 30:
                data["corrections"] = data["corrections"][-30:]

    _save(data)


def get_user_model_context(max_chars: int = 400) -> str:
    data = _load()
    sections = []

    prefs = data.get("preferences", [])[-5:]
    if prefs:
        sections.append("Preferences: " + "; ".join(p["text"][:50] for p in prefs))

    apps = sorted(data.get("common_apps", []), key=lambda x: x.get("count", 0), reverse=True)[:5]
    if apps:
        sections.append("Frequent apps: " + ", ".join(a["name"] for a in apps))

    corrections = data.get("corrections", [])[-3:]
    if corrections:
        sections.append("Recent corrections: " + "; ".join(c["text"][:50] for c in corrections))

    return "\n".join(sections)[:max_chars]
