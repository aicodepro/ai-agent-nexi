"""Bounded, expiring memory for time-sensitive public information."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from engine.memory.local_memory import atomic_write_json, lock_for_path, quarantine_corrupt_file


DEFAULT_TEMPORAL_PATH = Path(__file__).resolve().parents[2] / "data" / "memory" / "temporal_memory.json"


def _path() -> Path:
    override = os.getenv("NEXI_TEMPORAL_MEMORY_PATH", "").strip()
    return Path(override) if override else DEFAULT_TEMPORAL_PATH


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", str(query or "")).strip().lower()[:300]


def _query_id(query: str) -> str:
    return hashlib.sha256(_normalize_query(query).encode("utf-8")).hexdigest()[:20]


@dataclass
class TemporalFact:
    query_id: str
    query: str
    content: str
    valid_at: float
    retrieved_at: float
    expires_at: float
    source: str
    confidence: float
    citations: list[dict[str, Any]] = field(default_factory=list)
    retrieval_behavior: str = "live_first_explicit_stale_only"

    @property
    def stale(self) -> bool:
        return time.time() >= self.expires_at

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TemporalMemory:
    def __init__(self, path: Path | str | None = None, *, max_facts: int = 200) -> None:
        self.path = Path(path) if path is not None else _path()
        self.max_facts = max(1, int(max_facts))
        self._lock = lock_for_path(self.path)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": 1, "facts": []}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
                raise ValueError("invalid temporal memory schema")
            return data
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            quarantine_corrupt_file(self.path, exc)
            return {"schema_version": 1, "facts": []}
        except OSError:
            return {"schema_version": 1, "facts": []}

    def store(
        self,
        query: str,
        content: str,
        *,
        source: str,
        ttl_seconds: float,
        citations: list[dict[str, Any]] | None = None,
        confidence: float = 0.7,
        valid_at: float | None = None,
    ) -> TemporalFact | None:
        clean_query = _normalize_query(query)
        clean_content = re.sub(r"\s+", " ", str(content or "")).strip()[:4000]
        if not clean_query or not clean_content:
            return None
        now = time.time()
        fact = TemporalFact(
            query_id=_query_id(clean_query),
            query=clean_query,
            content=clean_content,
            valid_at=float(valid_at or now),
            retrieved_at=now,
            expires_at=now + max(1.0, float(ttl_seconds)),
            source=str(source or "web")[:80],
            confidence=max(0.0, min(1.0, float(confidence))),
            citations=list(citations or [])[:10],
        )
        with self._lock:
            data = self._load()
            facts = [item for item in data.get("facts", []) if item.get("query_id") != fact.query_id]
            facts.append(fact.to_dict())
            data["facts"] = facts[-self.max_facts:]
            atomic_write_json(self.path, data, sort_keys=True)
        return fact

    def recall(self, query: str, *, include_stale: bool = True) -> TemporalFact | None:
        query_id = _query_id(query)
        with self._lock:
            items = self._load().get("facts", [])
        for item in reversed(items):
            if item.get("query_id") != query_id:
                continue
            try:
                fact = TemporalFact(**item)
            except (TypeError, ValueError):
                return None
            return fact if include_stale or not fact.stale else None
        return None

    def prune_expired(self) -> int:
        now = time.time()
        with self._lock:
            data = self._load()
            facts = list(data.get("facts", []))
            kept = [item for item in facts if float(item.get("expires_at") or 0.0) > now]
            data["facts"] = kept
            atomic_write_json(self.path, data, sort_keys=True)
        return len(facts) - len(kept)


_TEMPORAL_MEMORY = TemporalMemory()


def get_temporal_memory() -> TemporalMemory:
    return _TEMPORAL_MEMORY
