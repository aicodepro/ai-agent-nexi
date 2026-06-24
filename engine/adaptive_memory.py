from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

from engine.memory_safety import is_safe_to_store, redact_sensitive


MEMORY_PATH = Path(__file__).resolve().parents[1] / "data" / "adaptive_memory.json"
CATEGORIES = {
    "identity", "preferences", "projects", "current_tasks", "corrections",
    "tool_failures", "successful_workflows", "ui_preferences", "output_preferences",
    "voice_preferences", "model_preferences", "file_preferences",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict:
    return {category: [] for category in sorted(CATEGORIES)}


def _load() -> dict:
    try:
        data = json.loads(MEMORY_PATH.read_text(encoding="utf-8")) if MEMORY_PATH.exists() else {}
    except Exception:
        data = {}
    base = _empty()
    if isinstance(data, dict):
        for key in base:
            if isinstance(data.get(key), list):
                base[key] = data[key]
    return base


def _save(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _clean(text: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", redact_sensitive(str(text or ""))).strip()
    if not value:
        return ""
    safe, _reason = is_safe_to_store(value)
    return value[:limit] if safe else ""


def _memory_id(memory_type: str, text: str) -> str:
    digest = hashlib.sha1(f"{memory_type}:{text}".encode("utf-8")).hexdigest()[:12]
    return f"mem_{digest}"


def _score(item: dict, query: str) -> int:
    if not query:
        return int(item.get("use_count", 0))
    haystack = " ".join([item.get("text", ""), " ".join(item.get("tags", [])), item.get("type", "")]).lower()
    return sum(1 for token in re.findall(r"[a-z0-9]+", query.lower()) if token in haystack)


def _summarize_preference(text: str) -> tuple[str, str]:
    lower = text.lower().strip()
    if "my name is" in lower:
        name = re.sub(r".*my name is\s+", "", text, flags=re.I).strip(" .")
        return "identity", f"User's name is {name}."
    if "short" in lower and ("answer" in lower or "reply" in lower or "direct" in lower):
        return "preferences", "User prefers short and direct answers."
    if "long" in lower and ("box" in lower or "workspace" in lower or "main ui" in lower):
        return "output_preferences", "User prefers long answers in the Jarvis Output Workspace."
    if "copy code" in lower:
        return "output_preferences", "User prefers code to be copied by default when requested."
    if "markdown" in lower:
        return "file_preferences", "User prefers markdown files for saved generated content."
    if any(term in lower for term in ("tts failed", "tool failed", "didn't work", "did not work")):
        return "tool_failures", text
    if lower.startswith(("no,", "actually", "this is wrong", "that's wrong", "that is wrong")) or " next time " in lower:
        return "corrections", text
    if any(term in lower for term in ("project", "repo", "workspace")):
        return "projects", text
    if any(term in lower for term in ("model", "gemini", "groq")):
        return "model_preferences", text
    if any(term in lower for term in ("voice", "speak", "speech")):
        return "voice_preferences", text
    if any(term in lower for term in ("ui", "interface", "screen")):
        return "ui_preferences", text
    return "preferences", text


def remember(text: str, memory_type: str = "preferences", source: str = "explicit", confidence: float = 1.0, tags: list[str] | None = None) -> dict:
    safe_type = memory_type if memory_type in CATEGORIES else "preferences"
    value = _clean(text)
    if not value:
        return {"stored": False, "reason": "unsafe_or_empty"}
    data = _load()
    now = _now()
    mem_id = _memory_id(safe_type, value)
    for item in data[safe_type]:
        if item.get("id") == mem_id or item.get("text", "").lower() == value.lower():
            item["updated_at"] = now
            item["confidence"] = max(float(item.get("confidence", 0.0)), float(confidence))
            _save(data)
            print(f"[MEMORY] stored type={safe_type}", flush=True)
            return dict(item)
    item = {
        "id": mem_id,
        "type": safe_type,
        "text": value,
        "source": source,
        "confidence": max(0.0, min(1.0, float(confidence))),
        "created_at": now,
        "updated_at": now,
        "last_used_at": "",
        "use_count": 0,
        "tags": tags or [],
        "safe": True,
    }
    data[safe_type].append(item)
    data[safe_type] = data[safe_type][-80:]
    _save(data)
    print(f"[MEMORY] stored type={safe_type}", flush=True)
    return dict(item)


def recall(query: str = "", limit: int = 10) -> list[dict]:
    data = _load()
    items = [dict(item) for category in CATEGORIES for item in data.get(category, []) if item.get("safe", True)]
    ranked = sorted(items, key=lambda item: (_score(item, query), item.get("updated_at", "")), reverse=True)
    result = [item for item in ranked if not query or _score(item, query) > 0]
    if not result and not query:
        result = ranked
    now = _now()
    ids = {item.get("id") for item in result[:limit]}
    if ids:
        for category in CATEGORIES:
            for item in data.get(category, []):
                if item.get("id") in ids:
                    item["last_used_at"] = now
                    item["use_count"] = int(item.get("use_count", 0)) + 1
        _save(data)
    return result[:max(1, int(limit or 10))]


def forget(query: str) -> dict:
    needle = str(query or "").lower().strip()
    if not needle:
        return {"removed": 0}
    data = _load()
    removed = 0
    for category in CATEGORIES:
        before = len(data[category])
        data[category] = [item for item in data[category] if needle not in item.get("text", "").lower() and needle not in item.get("id", "").lower()]
        removed += before - len(data[category])
    _save(data)
    return {"removed": removed}


def build_memory_context(user_text: str = "", limit: int = 8, max_chars: int = 1800) -> str:
    memories = recall(user_text, limit=limit)
    lines = [f"- {item['type']}: {item['text']}" for item in memories[:limit] if item.get("text")]
    compact = "\n".join(lines)[:max(0, int(max_chars or 1800))]
    print(f"[MEMORY] context_built items={len(lines)}", flush=True)
    return compact


def maybe_extract_memory(user_text: str, assistant_text: str = "") -> list[dict]:
    text = _clean(user_text, limit=500)
    if not text:
        return []
    lower = text.lower()
    triggers = (
        "remember that", "from now on", "always ", "don't ", "do not ", "i prefer", "actually", "no,",
        "i want", "my name is", "this is wrong", "that's wrong", "that is wrong",
        "next time", "use this style", "keep answers short", "keep your answers short",
        "open long answers", "copy code", "save as markdown", "tts failed",
    )
    if not any(trigger in lower for trigger in triggers):
        return []
    memory_type, summary = _summarize_preference(text)
    source = "correction" if memory_type == "corrections" else "explicit"
    return [remember(summary, memory_type=memory_type, source=source, confidence=1.0)]


def store_memory(category: str, text: str, source: str = "chat") -> bool:
    return bool(remember(text, memory_type=category, source=source).get("id"))


def learn_from_user_text(text: str, source: str = "chat") -> bool:
    return bool(maybe_extract_memory(text))


def learn_from_exchange(user_text: str, assistant_text: str) -> None:
    maybe_extract_memory(user_text, assistant_text)
    lower = str(assistant_text or "").lower()
    if any(term in lower for term in ("done", "created", "opened", "saved", "copied")):
        remember(f"User: {user_text} -> Jarvis: {assistant_text}", "successful_workflows", "tool_success", 0.6)


def record_tool_failure(tool: str, reason: str) -> None:
    remember(f"{tool}: {reason}", "tool_failures", "tool_failure", 0.8)


def recall_adaptive(limit: int = 8) -> str:
    items = recall(limit=limit)
    return "; ".join(f"{item['type']}: {item['text']}" for item in items)


def forget_adaptive(term: str) -> int:
    return int(forget(term).get("removed", 0))
