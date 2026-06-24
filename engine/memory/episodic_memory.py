from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


DEFAULT_EPISODIC_PATH = Path(__file__).resolve().parents[2] / "data" / "memory" / "episodic_memory.json"


def _memory_path() -> Path:
    override = os.getenv("NEXI_EPISODIC_MEMORY_PATH", "").strip()
    return Path(override) if override else DEFAULT_EPISODIC_PATH


def _safe_text(text: str, limit: int = 1200) -> str:
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
    return value[: max(0, int(limit or 1200))]


def _tokens(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]{3,}", str(text or "").lower())}


@dataclass
class Episode:
    id: str = ""
    user_input: str = ""
    intent: str = ""
    route: str = ""
    outcome: str = "success"
    steps_taken: list[str] = field(default_factory=list)
    duration_ms: int = 0
    error: str = ""
    reflection_id: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Episode":
        return cls(
            id=str(data.get("id") or ""),
            user_input=str(data.get("user_input") or ""),
            intent=str(data.get("intent") or ""),
            route=str(data.get("route") or ""),
            outcome=str(data.get("outcome") or "success"),
            steps_taken=list(data.get("steps_taken") or []),
            duration_ms=int(data.get("duration_ms") or 0),
            error=str(data.get("error") or ""),
            reflection_id=str(data.get("reflection_id") or ""),
            timestamp=float(data.get("timestamp") or time.time()),
            metadata=dict(data.get("metadata") or {}),
        )


class EpisodicMemory:
    """Append-only memory for past command/task episodes."""

    def __init__(self, path: Path | str | None = None, *, max_episodes: int = 200) -> None:
        self.path = Path(path) if path is not None else _memory_path()
        self.max_episodes = max(1, int(max_episodes or 200))
        self._lock = threading.Lock()

    def _empty(self) -> dict[str, Any]:
        return {"schema_version": 1, "episodes": []}

    def _load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    base = self._empty()
                    base["episodes"] = list(data.get("episodes") or [])
                    return base
        except Exception:
            pass
        return self._empty()

    def _save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def store(self, episode: Episode | dict[str, Any]) -> str:
        item = episode if isinstance(episode, Episode) else Episode.from_dict(episode)
        item.user_input = _safe_text(item.user_input, 900)
        item.error = _safe_text(item.error, 400)
        safe_steps = []
        for step in item.steps_taken:
            safe_step = _safe_text(step, 400)
            if safe_step:
                safe_steps.append(safe_step)
        item.steps_taken = safe_steps
        if not item.user_input and not item.steps_taken:
            return ""
        if not item.id:
            item.id = f"ep_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        if item.outcome not in {"success", "failure", "partial", "interrupted"}:
            item.outcome = "partial"
        with self._lock:
            data = self._load()
            episodes = list(data.get("episodes") or [])
            episodes.append(item.to_dict())
            data["episodes"] = episodes[-self.max_episodes:]
            self._save(data)
        print(f"[EPISODIC_MEMORY] stored id={item.id} outcome={item.outcome}", flush=True)
        return item.id

    def recall_recent(self, n: int = 20) -> list[Episode]:
        count = max(1, int(n or 20))
        with self._lock:
            episodes = [Episode.from_dict(item) for item in self._load().get("episodes", [])]
        return episodes[-count:]

    def recall_similar(self, query: str, n: int = 5) -> list[Episode]:
        query_tokens = _tokens(query)
        if not query_tokens:
            return []
        scored: list[tuple[int, float, Episode]] = []
        for episode in self.recall_recent(self.max_episodes):
            haystack = " ".join([episode.user_input, episode.intent, episode.route, " ".join(episode.steps_taken)])
            score = len(query_tokens & _tokens(haystack))
            if score:
                scored.append((score, episode.timestamp, episode))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [episode for _score, _timestamp, episode in scored[: max(1, int(n or 5))]]

    def prune_old(self, days: int = 30) -> int:
        cutoff = time.time() - max(0, int(days or 30)) * 86400
        with self._lock:
            data = self._load()
            episodes = list(data.get("episodes") or [])
            kept = [item for item in episodes if float(item.get("timestamp") or 0) >= cutoff]
            data["episodes"] = kept
            self._save(data)
        removed = len(episodes) - len(kept)
        print(f"[EPISODIC_MEMORY] pruned count={removed}", flush=True)
        return removed

    def count(self) -> int:
        with self._lock:
            return len(self._load().get("episodes", []))


_episodic_memory = EpisodicMemory()


def get_episodic_memory() -> EpisodicMemory:
    return _episodic_memory


def store_episode(episode: Episode | dict[str, Any]) -> str:
    return _episodic_memory.store(episode)


def recall_recent(n: int = 20) -> list[Episode]:
    return _episodic_memory.recall_recent(n)


def recall_similar(query: str, n: int = 5) -> list[Episode]:
    return _episodic_memory.recall_similar(query, n)
