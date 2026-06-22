"""Unified memory manager — replaces adaptive_memory + memory_store."""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from memory.safety import is_safe_to_store, redact_sensitive, clean_for_storage

MEMORY_PATH = Path(__file__).resolve().parent.parent / "data" / "memory.json"

CATEGORIES = [
    "identity", "preferences", "projects", "current_tasks", "corrections",
    "tool_failures", "successful_workflows", "notes", "facts", "rules",
]


def _now() -> str:
    return datetime.now().isoformat()


def _empty() -> dict:
    return {cat: [] for cat in CATEGORIES}


def _load() -> dict:
    try:
        if MEMORY_PATH.exists():
            return json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return _empty()


def _save(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _memory_id(category: str, text: str) -> str:
    return hashlib.sha1(f"{category}:{text.lower().strip()}".encode()).hexdigest()[:12]


def _score(item: dict, query: str) -> float:
    tokens = set(query.lower().split())
    item_tokens = set(item.get("text", "").lower().split())
    if not tokens:
        return 0.0
    overlap = tokens & item_tokens
    return len(overlap) / len(tokens)


def _classify_category(text: str) -> str:
    lower = text.lower()
    if any(w in lower for w in ("my name is", "i am ", "i'm ", "call me")):
        return "identity"
    if any(w in lower for w in ("i prefer", "i like", "i want", "always ", "never ")):
        return "preferences"
    if any(w in lower for w in ("project", "working on", "building")):
        return "projects"
    if any(w in lower for w in ("when i say", "rule:", "learn that")):
        return "rules"
    return "facts"


def remember(text: str, category: str = "", source: str = "user",
             confidence: float = 1.0, tags: list = None) -> str:
    text = clean_for_storage(text)
    if not text:
        return "I can't store that — it may contain sensitive information."

    if not category:
        category = _classify_category(text)
    if category not in CATEGORIES:
        category = "facts"

    data = _load()
    mid = _memory_id(category, text)

    # Deduplicate
    for item in data.get(category, []):
        if item.get("id") == mid:
            item["updated_at"] = _now()
            item["use_count"] = item.get("use_count", 0) + 1
            _save(data)
            return f"Updated: {text[:60]}"

    entry = {
        "id": mid, "text": text, "category": category, "source": source,
        "confidence": confidence, "tags": tags or [],
        "created_at": _now(), "updated_at": _now(), "use_count": 0,
    }
    if category not in data:
        data[category] = []
    data[category].append(entry)

    # Cap per category
    if len(data[category]) > 80:
        data[category] = data[category][-80:]

    _save(data)
    return f"Remembered: {text[:60]}"


def recall(query: str = "", limit: int = 5) -> list:
    data = _load()
    all_items = []
    for cat in CATEGORIES:
        all_items.extend(data.get(cat, []))

    if not query:
        all_items.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        return all_items[:limit]

    scored = [(item, _score(item, query)) for item in all_items]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, score in scored[:limit] if score > 0]


def forget(query: str) -> int:
    data = _load()
    removed = 0
    query_lower = query.lower()
    for cat in CATEGORIES:
        before = len(data.get(cat, []))
        data[cat] = [item for item in data.get(cat, [])
                     if query_lower not in item.get("text", "").lower()]
        removed += before - len(data[cat])
    if removed > 0:
        _save(data)
    return removed


def build_memory_context(user_text: str = "", limit: int = 6, max_chars: int = 600) -> str:
    items = recall(user_text, limit=limit) if user_text else recall(limit=limit)
    if not items:
        return ""
    lines = [f"- {item['text'][:100]}" for item in items]
    text = "\n".join(lines)
    return text[:max_chars]


def maybe_extract_memory(user_text: str, assistant_text: str = "") -> None:
    """Auto-extract memory-worthy statements from user input."""
    patterns = [
        (r"remember\s+that\s+(.+)", None),
        (r"my name is\s+(.+)", "identity"),
        (r"i (?:prefer|like|want)\s+(.+)", "preferences"),
        (r"i(?:'m| am) working on\s+(.+)", "projects"),
    ]
    lower = user_text.lower().strip()
    for pattern, category in patterns:
        match = re.match(pattern, lower)
        if match:
            remember(match.group(1).strip(), category=category or "facts", source="auto_extract")
            return


def add_note(text: str) -> str:
    return remember(text, category="notes", source="user")


def show_notes(limit: int = 10) -> str:
    data = _load()
    notes = data.get("notes", [])[-limit:]
    if not notes:
        return "No notes saved."
    return "\n".join(f"- {n['text'][:100]}" for n in notes)


def parse_memory_command(query: str) -> dict:
    """Parse natural-language memory commands."""
    lower = query.lower().strip()

    if re.match(r"remember\s+(that\s+)?", lower):
        text = re.sub(r"^remember\s+(that\s+)?", "", lower).strip()
        if text:
            msg = remember(text)
            return {"handled": True, "response": msg}

    if re.match(r"forget\s+", lower):
        term = re.sub(r"^forget\s+", "", lower).strip()
        if term:
            count = forget(term)
            msg = f"Forgot {count} item(s) about '{term}'." if count else f"Nothing found about '{term}'."
            return {"handled": True, "response": msg}

    if re.match(r"show\s+(my\s+)?notes", lower):
        return {"handled": True, "response": show_notes()}

    if re.match(r"(what do you (know|remember)|recall)", lower):
        items = recall(limit=8)
        if items:
            lines = [f"- {i['text'][:80]}" for i in items]
            return {"handled": True, "response": "Here's what I remember:\n" + "\n".join(lines)}
        return {"handled": True, "response": "I don't have any memories stored yet."}

    return {"handled": False, "response": ""}
