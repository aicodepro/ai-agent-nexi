from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.memory.local_memory import atomic_write_json, lock_for_path, quarantine_corrupt_file


DEFAULT_SEMANTIC_PATH = Path(__file__).resolve().parents[2] / "data" / "memory" / "semantic_memory.json"
SEMANTIC_CATEGORIES = {
    "identity",
    "preference",
    "project",
    "correction",
    "skill",
    "fact",
    "workflow",
    "environment",
}
CATEGORY_ALIASES = {
    "preferences": "preference",
    "projects": "project",
    "corrections": "correction",
    "facts": "fact",
    "workflows": "workflow",
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _memory_path() -> Path:
    override = os.getenv("NEXI_SEMANTIC_MEMORY_PATH", "").strip()
    return Path(override) if override else DEFAULT_SEMANTIC_PATH


def _normalize_category(category: str) -> str:
    value = str(category or "fact").strip().lower()
    value = CATEGORY_ALIASES.get(value, value)
    return value if value in SEMANTIC_CATEGORIES else "fact"


def _clean_text(text: str, limit: int = 600) -> str:
    value = str(text or "")
    try:
        from engine.memory_safety import is_safe_to_store, redact_sensitive
        value = redact_sensitive(value)
        safe, _reason = is_safe_to_store(value)
        if not safe:
            return ""
    except Exception:
        pass
    value = re.sub(r"\s+", " ", value).strip()
    return value[: max(0, int(limit or 600))]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", str(text or "").lower())}


def _fact_id(category: str, subject: str, predicate: str, obj: str) -> str:
    key = f"{category}:{subject.lower()}:{predicate.lower()}:{obj.lower()}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
    return f"sem_{digest}"


def _safe_metadata(metadata: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in dict(metadata or {}).items():
        safe_key = re.sub(r"[^a-z0-9_\-]", "_", str(key or "").lower())[:40]
        safe_value = _clean_text(str(value), 200)
        if safe_key and safe_value:
            result[safe_key] = safe_value
    return result


@dataclass
class SemanticFact:
    id: str = ""
    subject: str = "user"
    predicate: str = "says"
    object: str = ""
    category: str = "fact"
    confidence: float = 0.7
    source: str = "semantic"
    evidence: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    last_used_at: str = ""
    use_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SemanticFact":
        return cls(
            id=str(data.get("id") or ""),
            subject=str(data.get("subject") or "user"),
            predicate=str(data.get("predicate") or "says"),
            object=str(data.get("object") or ""),
            category=_normalize_category(str(data.get("category") or "fact")),
            confidence=float(data.get("confidence") or 0.7),
            source=str(data.get("source") or "semantic"),
            evidence=str(data.get("evidence") or ""),
            tags=list(data.get("tags") or []),
            created_at=str(data.get("created_at") or _now()),
            updated_at=str(data.get("updated_at") or _now()),
            last_used_at=str(data.get("last_used_at") or ""),
            use_count=int(data.get("use_count") or 0),
            metadata=dict(data.get("metadata") or {}),
        )


class SemanticMemory:
    """Normalized long-term semantic facts, preferences, and corrections."""

    def __init__(self, path: Path | str | None = None, *, max_facts: int = 500) -> None:
        self.path = Path(path) if path is not None else _memory_path()
        self.max_facts = max(1, int(max_facts or 500))
        self._lock = lock_for_path(self.path)

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": 1, "facts": []}

    def _load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(data, dict) or not isinstance(data.get("facts", []), list):
                    raise ValueError("semantic memory has an invalid schema")
                base = self._empty()
                base["facts"] = [item for item in data.get("facts", []) if isinstance(item, dict)]
                return base
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            quarantine_corrupt_file(self.path, exc)
        except OSError as exc:
            warnings.warn(f"Could not read semantic memory: {self.path} ({exc})", RuntimeWarning, stacklevel=2)
        return self._empty()

    def _save(self, data: dict[str, Any]) -> None:
        atomic_write_json(self.path, data, sort_keys=True)

    def upsert(self, fact: SemanticFact | dict[str, Any]) -> str:
        item = fact if isinstance(fact, SemanticFact) else SemanticFact.from_dict(fact)
        item.category = _normalize_category(item.category)
        item.subject = _clean_text(item.subject, 120) or "user"
        item.predicate = _clean_text(item.predicate, 120) or "says"
        item.object = _clean_text(item.object, 600)
        item.evidence = _clean_text(item.evidence, 600)
        safe_tags = []
        for tag in item.tags:
            safe_tag = _clean_text(tag, 60)
            if safe_tag:
                safe_tags.append(safe_tag)
        item.tags = safe_tags
        item.metadata = _safe_metadata(item.metadata)
        if not item.object:
            return ""
        item.confidence = max(0.0, min(1.0, float(item.confidence or 0.7)))
        if not item.id:
            item.id = _fact_id(item.category, item.subject, item.predicate, item.object)
        now = _now()
        item.updated_at = now

        with self._lock:
            data = self._load()
            facts = list(data.get("facts") or [])
            for existing in facts:
                if existing.get("id") == item.id:
                    existing["confidence"] = max(float(existing.get("confidence") or 0.0), item.confidence)
                    existing["updated_at"] = now
                    if item.evidence:
                        existing["evidence"] = item.evidence
                    existing["tags"] = sorted(set(list(existing.get("tags") or []) + item.tags))
                    existing["metadata"] = {**dict(existing.get("metadata") or {}), **item.metadata}
                    self._save(data)
                    print(f"[SEMANTIC_MEMORY] upserted id={item.id} category={item.category}", flush=True)
                    return item.id
            facts.append(item.to_dict())
            data["facts"] = facts[-self.max_facts:]
            self._save(data)

        print(f"[SEMANTIC_MEMORY] upserted id={item.id} category={item.category}", flush=True)
        return item.id

    def recall(self, query: str = "", *, categories: list[str] | None = None, limit: int = 8) -> list[SemanticFact]:
        query_tokens = _tokens(query)
        allowed = {_normalize_category(category) for category in categories or []}
        with self._lock:
            data = self._load()
            facts = [SemanticFact.from_dict(item) for item in data.get("facts", [])]

        scored: list[tuple[int, str, SemanticFact]] = []
        for fact in facts:
            if allowed and fact.category not in allowed:
                continue
            haystack = " ".join([fact.category, fact.subject, fact.predicate, fact.object, " ".join(fact.tags)])
            score = len(query_tokens & _tokens(haystack)) if query_tokens else int(fact.use_count)
            if query_tokens and score <= 0:
                continue
            scored.append((score, fact.updated_at, fact))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        result = [fact for _score, _updated, fact in scored[: max(1, int(limit or 8))]]
        if result:
            self._mark_used({fact.id for fact in result})
        return result

    def _mark_used(self, ids: set[str]) -> None:
        now = _now()
        with self._lock:
            data = self._load()
            changed = False
            for item in data.get("facts", []):
                if item.get("id") in ids:
                    item["last_used_at"] = now
                    item["use_count"] = int(item.get("use_count") or 0) + 1
                    changed = True
            if changed:
                self._save(data)

    def forget(self, query: str) -> int:
        needle = str(query or "").strip().lower()
        if not needle:
            return 0
        with self._lock:
            data = self._load()
            facts = list(data.get("facts") or [])
            kept = []
            for item in facts:
                haystack = " ".join([
                    str(item.get("id", "")),
                    str(item.get("category", "")),
                    str(item.get("subject", "")),
                    str(item.get("predicate", "")),
                    str(item.get("object", "")),
                ]).lower()
                if needle not in haystack:
                    kept.append(item)
            data["facts"] = kept
            self._save(data)
        removed = len(facts) - len(kept)
        print(f"[SEMANTIC_MEMORY] forgot count={removed}", flush=True)
        return removed

    def build_context(self, query: str = "", *, limit: int = 6, max_chars: int = 1200) -> str:
        facts = self.recall(query, limit=limit)
        lines = []
        for fact in facts[:limit]:
            text = f"- {fact.category}: {fact.subject} {fact.predicate} {fact.object}"
            lines.append(text)
        compact = "\n".join(lines)[: max(0, int(max_chars or 1200))]
        print(f"[SEMANTIC_MEMORY] context_built items={len(lines)}", flush=True)
        return compact

    def count(self) -> int:
        with self._lock:
            return len(self._load().get("facts", []))


def extract_semantic_facts(user_text: str, assistant_text: str = "") -> list[SemanticFact]:
    text = _clean_text(user_text, 700)
    if not text:
        return []
    lower = text.lower().strip()
    facts: list[SemanticFact] = []

    name_match = re.search(r"\bmy name is\s+([^.!?]+)", text, re.I)
    if name_match:
        facts.append(SemanticFact(subject="user", predicate="name_is", object=name_match.group(1).strip(), category="identity", source="explicit", evidence=text, confidence=1.0, tags=["identity"]))

    preference_triggers = ("i prefer", "from now on", "always ", "don't ", "do not ", "i want")
    if any(trigger in lower for trigger in preference_triggers):
        facts.append(SemanticFact(subject="user", predicate="prefers", object=text, category="preference", source="explicit", evidence=text, confidence=0.9, tags=["preference"]))

    if lower.startswith(("actually", "no,", "that's wrong", "that is wrong", "this is wrong")) or " next time " in lower:
        facts.append(SemanticFact(subject="user", predicate="corrected", object=text, category="correction", source="correction", evidence=text, confidence=0.9, tags=["correction"]))

    if any(token in lower for token in ("project", "repo", "workspace")):
        facts.append(SemanticFact(subject="user", predicate="works_on", object=text, category="project", source="explicit", evidence=text, confidence=0.75, tags=["project"]))

    assistant = _clean_text(assistant_text, 300)
    if assistant and any(term in assistant.lower() for term in ("done", "created", "opened", "saved", "copied")):
        facts.append(SemanticFact(subject="nexi", predicate="completed", object=f"User: {text} -> Nexi: {assistant}", category="workflow", source="assistant", confidence=0.6, tags=["success"]))

    return facts


_semantic_memory = SemanticMemory()


def get_semantic_memory() -> SemanticMemory:
    return _semantic_memory


def remember_fact(subject: str, predicate: str, obj: str, *, category: str = "fact", source: str = "semantic", confidence: float = 0.7, evidence: str = "", tags: list[str] | None = None, metadata: dict[str, Any] | None = None) -> str:
    return _semantic_memory.upsert(SemanticFact(subject=subject, predicate=predicate, object=obj, category=category, source=source, confidence=confidence, evidence=evidence, tags=tags or [], metadata=metadata or {}))


def recall(query: str = "", *, categories: list[str] | None = None, limit: int = 8) -> list[SemanticFact]:
    return _semantic_memory.recall(query=query, categories=categories, limit=limit)


def build_semantic_context(query: str = "", *, limit: int = 6, max_chars: int = 1200) -> str:
    return _semantic_memory.build_context(query=query, limit=limit, max_chars=max_chars)


def maybe_extract_semantic_memory(user_text: str, assistant_text: str = "") -> list[str]:
    ids = []
    for fact in extract_semantic_facts(user_text, assistant_text):
        fact_id = _semantic_memory.upsert(fact)
        if fact_id:
            ids.append(fact_id)
    return ids
