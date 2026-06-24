from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from engine.training_safety import redact_training_text, validate_text
from engine.training_storage import read_json, training_path, write_json


TRAINING_FEEDBACK_PATH = training_path("training_feedback.json")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load() -> dict[str, Any]:
    data = read_json(TRAINING_FEEDBACK_PATH, {"feedback": []})
    return data if isinstance(data, dict) and isinstance(data.get("feedback"), list) else {"feedback": []}


def _save(data: dict[str, Any]) -> None:
    write_json(TRAINING_FEEDBACK_PATH, data)


def classify_feedback(text: str) -> dict:
    q = str(text or "").strip().lower()
    score_match = re.search(r"score (?:this )?(\d{1,2})\s*(?:out of|/)\s*10", q)
    if score_match:
        return {"feedback_type": "score", "score": min(10, int(score_match.group(1))) / 10}
    if any(word in q for word in ("perfect", "good", "ideal")):
        return {"feedback_type": "positive", "score": 1.0}
    if any(word in q for word in ("wrong", "bad", "not like this", "too long", "too short", "less generic", "more technical")):
        return {"feedback_type": "negative", "score": 0.3}
    return {"feedback_type": "style", "score": None}


def record_feedback(user_text: str, assistant_text: str = "", need: str = "", notes: str = "") -> dict:
    clean_user = redact_training_text(user_text)[:500]
    clean_assistant = redact_training_text(assistant_text)[:800]
    safe, reason = validate_text(clean_user + " " + clean_assistant)
    if not safe:
        return {"saved": False, "reason": reason}
    classified = classify_feedback(clean_user)
    item = {
        "id": "fb_" + hashlib.sha1(f"{clean_user}:{_now()}".encode("utf-8")).hexdigest()[:12],
        "user_text": clean_user,
        "assistant_text": clean_assistant,
        "feedback_type": classified["feedback_type"],
        "score": classified.get("score"),
        "need": need,
        "notes": redact_training_text(notes)[:400],
        "created_at": _now(),
    }
    data = _load()
    data["feedback"].append(item)
    data["feedback"] = data["feedback"][-500:]
    _save(data)
    return {"saved": True, "feedback": item}


def list_feedback(need: str | None = None) -> list[dict]:
    items = [dict(item) for item in _load().get("feedback", [])]
    if need:
        items = [item for item in items if item.get("need") == need]
    return items
