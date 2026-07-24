from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

MEMORY_PATH = Path(__file__).resolve().parents[1] / "data" / "nexi_memory.json"
SECRET_WORDS = {"password", "token", "api key", "secret", "private key", "cookie"}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _empty() -> dict:
    return {"notes": [], "preferences": {}, "facts": [], "recent_commands": []}


def _load() -> dict:
    try:
        if MEMORY_PATH.exists():
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            base = _empty()
            if isinstance(data, dict):
                base.update({k: data.get(k, base[k]) for k in base})
            return base
    except Exception:
        pass
    return _empty()


def _save(data: dict) -> None:
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _safe_text(text: str) -> str:
    value = (text or "").strip()
    low = value.lower()
    if any(word in low for word in SECRET_WORDS):
        return ""
    return value[:500]


def _display_text(text: str) -> str:
    value = (text or "").strip()
    if not value:
        return value
    value = value[0].upper() + value[1:]
    if value[-1] not in ".!?":
        value += "."
    return value


def _memory_key(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return (value or "memory")[:48]


def _log(message: str) -> None:
    print(message, file=sys.stdout, flush=True)


def remember(text: str, memory_type: str = "preferences", source: str = "explicit", confidence: float = 1.0, tags: list[str] | None = None) -> dict:
    from engine.adaptive_memory import remember as adaptive_remember

    result = adaptive_remember(text, memory_type=memory_type, source=source, confidence=confidence, tags=tags)
    try:
        from engine.memory.semantic_memory import SemanticFact, get_semantic_memory
        category = "preference" if memory_type in {"preference", "preferences"} else "fact"
        fact_id = get_semantic_memory().upsert(SemanticFact(
            subject="user",
            predicate="remembers",
            object=str(text or ""),
            category=category,
            source=source,
            confidence=confidence,
            tags=tags or [],
        ))
        if fact_id:
            result = {**dict(result or {}), "semantic_id": fact_id}
    except Exception:
        pass
    return result


def recall(query: str = "", limit: int = 10) -> list[dict]:
    from engine.adaptive_memory import recall as adaptive_recall

    items = list(adaptive_recall(query=query, limit=limit) or [])
    try:
        from engine.memory.semantic_memory import get_semantic_memory
        for fact in get_semantic_memory().recall(query=query, limit=limit):
            items.append({"text": fact.object, "type": fact.category, "source": "semantic", "confidence": fact.confidence})
    except Exception:
        pass
    return items[:limit]


def build_memory_context(user_text: str, limit: int = 8, max_chars: int = 1800) -> str:
    from engine.adaptive_memory import build_memory_context as adaptive_context

    return adaptive_context(user_text, limit=limit, max_chars=max_chars)


def maybe_extract_memory(user_text: str, assistant_text: str = "") -> list[dict]:
    from engine.adaptive_memory import maybe_extract_memory as adaptive_extract

    return adaptive_extract(user_text, assistant_text)


def remember_fact(text: str) -> str:
    _log("[MEMORY] intent=remember")
    value = _safe_text(text)
    if not value:
        return "I can't store secrets or empty memories."
    try:
        stored = remember(value, memory_type="preferences", source="explicit")
        if stored.get("id"):
            return "Remembered."
    except Exception:
        pass
    data = _load()
    data["facts"].append({"text": value, "created_at": _now()})
    data["facts"] = data["facts"][-50:]
    _save(data)
    _log(f"[MEMORY] saved key={_memory_key(value)}")
    return f"Remembered. {_display_text(value)}"


def add_note(text: str) -> str:
    _log("[MEMORY] intent=note")
    value = _safe_text(text)
    if not value:
        return "I can't save that note."
    data = _load()
    data["notes"].append({"text": value, "created_at": _now()})
    data["notes"] = data["notes"][-100:]
    _save(data)
    _log(f"[MEMORY] saved key={_memory_key(value)}")
    return "Note saved."


def forget(term: str) -> str:
    needle = (term or "").strip().lower()
    if not needle:
        return "What should I forget?"
    data = _load()
    before = len(data["facts"]) + len(data["notes"])
    data["facts"] = [item for item in data["facts"] if needle not in item.get("text", "").lower()]
    data["notes"] = [item for item in data["notes"] if needle not in item.get("text", "").lower()]
    removed = before - len(data["facts"]) - len(data["notes"])
    try:
        from engine.adaptive_memory import forget as adaptive_forget
        removed += int(adaptive_forget(term).get("removed", 0))
    except Exception:
        pass
    try:
        from engine.memory.semantic_memory import get_semantic_memory
        sem_result = get_semantic_memory().forget(term)
        if isinstance(sem_result, int):
            removed += sem_result
        elif isinstance(sem_result, dict):
            removed += int(sem_result.get("removed", 0))
        elif sem_result:
            removed += 1
    except Exception:
        pass
    _save(data)
    return "Forgot it." if removed else "I didn't find that memory."


def recall_summary(query: str = "") -> str:
    data = _load()
    items = [item.get("text", "") for item in data["facts"][-5:] + data["notes"][-5:] if item.get("text")]
    _log(f"[MEMORY] recall count={len(items)}")
    try:
        grouped = _grouped_memory_summary(query)
        if grouped:
            return grouped
    except Exception:
        pass
    if not items:
        return "I don't have any saved memories yet."
    return "I remember: " + "; ".join(items)


def _grouped_memory_summary(query: str = "") -> str:
    memories = recall(query=query, limit=12)
    if not memories:
        return ""
    groups: dict[str, list[str]] = {}
    for item in memories:
        groups.setdefault(item.get("type", "memory"), []).append(item.get("text", ""))
    chunks = []
    for category in sorted(groups):
        values = [value for value in groups[category] if value][:3]
        if values:
            chunks.append(f"{category.replace('_', ' ')}: " + "; ".join(values))
    return "I remember: " + " | ".join(chunks) if chunks else ""


def show_notes() -> str:
    data = _load()
    notes = [item.get("text", "") for item in data["notes"][-5:] if item.get("text")]
    if not notes:
        return "You don't have any saved notes yet."
    return "Your notes: " + "; ".join(notes)


def parse_memory_command(query: str):
    q = (query or "").strip()
    low = q.lower()
    if low.startswith("remember that "):
        return remember_fact(q[14:].strip())
    if low.startswith("remember "):
        return remember_fact(q[9:].strip())
    if low.startswith(("from now on ", "always ", "i prefer ", "i want ", "don't ", "do not ")):
        try:
            from engine.adaptive_memory import maybe_extract_memory
            if maybe_extract_memory(q):
                return "Understood."
        except Exception:
            pass
    if low in {"what do you remember", "what do you remember?", "what do you remember about me", "what do you remember about me?"}:
        return recall_summary()
    if low.startswith("forget that "):
        return forget(q[12:].strip())
    if low.startswith("forget my preference about "):
        return forget(q[27:].strip())
    if low.startswith("clear memory about "):
        return forget(q[19:].strip())
    if low.startswith("forget "):
        return forget(q[7:].strip())
    match = re.match(r"^(save note|take note|write note):\s*(.+)$", q, re.I)
    if match:
        return add_note(match.group(2))
    if low in {"show memory", "show memories", "show my memory", "what do you remember", "what do you remember?"}:
        return recall_summary()
    if low in {"show my notes", "show notes", "read my notes"}:
        return show_notes()
    return None


def get_brain_memory_context(limit: int = 5) -> str:
    data = _load()
    items = []
    for item in data["facts"][-limit:] + data["notes"][-limit:]:
        value = _safe_text(item.get("text", ""))
        if value:
            items.append(value)
    try:
        from engine.adaptive_memory import build_memory_context
        adaptive = build_memory_context("", limit=limit)
        if adaptive:
            items.append(adaptive)
    except Exception:
        pass
    if not items:
        _log("[MEMORY] context_built items=0")
        return ""
    _log(f"[MEMORY] context_built items={min(len(items), limit)}")
    return "Saved memories: " + "; ".join(items[-limit:])
