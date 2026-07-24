from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REFLECTION_MEMORY_PATH = Path(__file__).resolve().parents[1] / "data" / "memory" / "reflection_memory.json"


def _clean(text: str, limit: int = 600) -> str:
    value = str(text or "")
    try:
        from engine.memory_safety import is_safe_to_store, redact_sensitive
        # check BEFORE redacting: redaction erases the very markers the gate
        # looks for, so the old order let every secret through.
        safe, _reason = is_safe_to_store(value)
        if not safe:
            return ""
        value = redact_sensitive(value)
    except Exception:
        pass
    value = re.sub(r"\s+", " ", value).strip()
    return value[: max(0, int(limit or 600))]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", str(text or "").lower())}


def _lesson_id(failure: str, tool_name: str = "") -> str:
    key = f"{tool_name.lower()}:{failure.lower()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"ref_{digest}"


@dataclass
class ReflectionLesson:
    id: str = ""
    failure: str = ""
    lesson: str = ""
    next_action: str = ""
    context: str = ""
    timestamp: float = 0.0
    count: int = 1
    intent: str = ""
    tool_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReflectionLesson":
        return cls(
            id=str(data.get("id") or ""),
            failure=str(data.get("failure") or ""),
            lesson=str(data.get("lesson") or ""),
            next_action=str(data.get("next_action") or ""),
            context=str(data.get("context") or ""),
            timestamp=float(data.get("timestamp") or 0.0),
            count=max(1, int(data.get("count") or 1)),
            intent=str(data.get("intent") or ""),
            tool_name=str(data.get("tool_name") or ""),
        )


class ReflectionMemory:
    """Persisted Reflexion-style lessons for avoiding repeated failures."""

    PATH = REFLECTION_MEMORY_PATH
    MAX_LESSONS = 50
    SIMILARITY_THRESHOLD = 2

    @classmethod
    def _empty(cls) -> dict[str, Any]:
        return {"version": 1, "lessons": []}

    @classmethod
    def _load(cls) -> dict[str, Any]:
        try:
            path = Path(cls.PATH)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    base = cls._empty()
                    base["lessons"] = [item for item in list(data.get("lessons") or []) if isinstance(item, dict)]
                    return base
        except Exception:
            pass
        return cls._empty()

    @classmethod
    def _save(cls, data: dict[str, Any]) -> None:
        path = Path(cls.PATH)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def store_lesson(
        cls,
        failure: str,
        lesson: str,
        next_action: str = "",
        context: str = "",
        intent: str = "",
        tool_name: str = "",
    ) -> str:
        safe_failure = _clean(failure, 500)
        safe_lesson = _clean(lesson, 500)
        if not safe_failure or not safe_lesson:
            return ""
        safe_tool = _clean(tool_name, 80)
        safe_intent = _clean(intent, 100)
        safe_next_action = _clean(next_action, 400)
        safe_context = _clean(context, 500)
        lesson_id = _lesson_id(safe_failure, safe_tool)
        now = time.time()

        data = cls._load()
        lessons = list(data.get("lessons") or [])
        for item in lessons:
            if item.get("id") == lesson_id or str(item.get("failure", "")).lower() == safe_failure.lower():
                item["lesson"] = safe_lesson
                item["next_action"] = safe_next_action or item.get("next_action", "")
                item["context"] = safe_context or item.get("context", "")
                item["intent"] = safe_intent or item.get("intent", "")
                item["tool_name"] = safe_tool or item.get("tool_name", "")
                item["timestamp"] = now
                item["count"] = int(item.get("count") or 1) + 1
                cls._save(data)
                print(f"[REFLECTION_MEMORY] stored id={lesson_id} count={item['count']}", flush=True)
                return lesson_id

        item = ReflectionLesson(
            id=lesson_id,
            failure=safe_failure,
            lesson=safe_lesson,
            next_action=safe_next_action,
            context=safe_context,
            timestamp=now,
            count=1,
            intent=safe_intent,
            tool_name=safe_tool,
        ).to_dict()
        lessons.append(item)
        data["lessons"] = lessons[-cls.MAX_LESSONS:]
        cls._save(data)
        print(f"[REFLECTION_MEMORY] stored id={lesson_id} count=1", flush=True)
        return lesson_id

    @classmethod
    def recall_similar(cls, context: str = "", top_k: int = 3) -> list[dict[str, Any]]:
        query_tokens = _tokens(context)
        lessons = [ReflectionLesson.from_dict(item) for item in cls._load().get("lessons", [])]
        scored: list[tuple[int, float, ReflectionLesson]] = []
        for lesson in lessons:
            haystack = " ".join([lesson.failure, lesson.lesson, lesson.next_action, lesson.context, lesson.intent, lesson.tool_name])
            score = len(query_tokens & _tokens(haystack)) if query_tokens else int(lesson.count)
            if query_tokens and score < cls.SIMILARITY_THRESHOLD:
                continue
            scored.append((score, lesson.timestamp, lesson))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [lesson.to_dict() for _score, _timestamp, lesson in scored[: max(1, int(top_k or 3))]]

    @classmethod
    def get_context(cls, context: str = "", max_lessons: int = 3) -> str:
        lessons = cls.recall_similar(context, top_k=max_lessons)
        if not lessons:
            return ""
        lines = ["Lessons from past experience:"]
        for lesson in lessons[:max_lessons]:
            action = lesson.get("next_action") or lesson.get("lesson") or "avoid repeating the same failure"
            lines.append(f"- When {lesson.get('failure')}, {action}")
        compact = "\n".join(lines)[:1200]
        print(f"[REFLECTION_MEMORY] context_built items={len(lines) - 1}", flush=True)
        return compact

    @classmethod
    def prune_old(cls, days: int = 30) -> int:
        cutoff = time.time() - max(0, int(days or 30)) * 86400
        data = cls._load()
        lessons = list(data.get("lessons") or [])
        kept = [item for item in lessons if float(item.get("timestamp") or 0.0) >= cutoff]
        data["lessons"] = kept
        cls._save(data)
        removed = len(lessons) - len(kept)
        print(f"[REFLECTION_MEMORY] pruned count={removed}", flush=True)
        return removed

    @classmethod
    def count(cls) -> int:
        return len(cls._load().get("lessons", []))


def store_lesson(failure: str, lesson: str, next_action: str = "", context: str = "", intent: str = "", tool_name: str = "") -> str:
    return ReflectionMemory.store_lesson(failure, lesson, next_action, context, intent, tool_name)


def recall_similar(context: str = "", top_k: int = 3) -> list[dict[str, Any]]:
    return ReflectionMemory.recall_similar(context, top_k)


def get_context(context: str = "", max_lessons: int = 3) -> str:
    return ReflectionMemory.get_context(context, max_lessons)
