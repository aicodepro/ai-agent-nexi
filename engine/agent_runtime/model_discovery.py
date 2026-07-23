"""Live free-model discovery — no hardcoded model lists.

Darsh's constraint: providers add and REMOVE free models constantly (a hardcoded
id goes stale or 404s), so NEXI must discover what's actually free right now and pick
per task. OpenRouter exposes this directly: GET /api/v1/models returns every model with
pricing, so "free" is a fact we read, not a list we maintain.

Flow: query the provider's model catalogue -> keep the free ones (pricing 0 or ":free")
-> categorize by task from the id/name -> cache with a TTL. The static model_policy
pool is the OFFLINE fallback only, used when discovery can't reach the network.

This is discovery + categorization. Health/failure tracking is model_health; ordering
is model_policy. Live benchmark research per task (the "Sakana Fugu" idea) rides on top
via research_task_models() — kept OUT of the hot voice path (it's a slow web call).
"""
from __future__ import annotations

import json
import os
import threading
import time

# cache: provider -> {"at": epoch, "models": [ids], "by_task": {task: [ids]}}
_CACHE: dict[str, dict] = {}
_CACHE_LOCK = threading.RLock()


def _ttl_s() -> float:
    try:
        return max(60.0, float(os.getenv("NEXI_MODEL_DISCOVERY_TTL_S", "3600")))
    except ValueError:
        return 3600.0


def _is_free(model: dict) -> bool:
    mid = str(model.get("id") or "")
    if mid.endswith(":free"):
        return True
    pricing = model.get("pricing") or {}
    def _zero(v):
        try:
            return float(v) == 0.0
        except (TypeError, ValueError):
            return False
    # free only if BOTH prompt and completion are 0 (a 0-prompt/paid-completion model
    # is not free).
    return _zero(pricing.get("prompt")) and _zero(pricing.get("completion"))


# task categorization from the model id/name. Heuristic, not a benchmark — a cheap way
# to route "code" work to a coding model without a per-turn web call. research_task_models
# refines this with live benchmark data on demand.
_TASK_HINTS: dict[str, tuple[str, ...]] = {
    "code": ("code", "coder", "poolside", "laguna", "qwen", "deepseek", "codestral", "starcoder"),
    "orchestration": ("nemotron", "ultra", "reason", "-r1", "think", "opus", "70b", "120b", "405b", "large"),
}


def _categorize(model_ids: list[str]) -> dict[str, list[str]]:
    by_task: dict[str, list[str]] = {"code": [], "orchestration": [], "general": list(model_ids)}
    for mid in model_ids:
        low = mid.lower()
        for task, hints in _TASK_HINTS.items():
            if any(h in low for h in hints):
                by_task[task].append(mid)
    return by_task


def discover_free_models(provider: str = "openrouter", *, timeout: float = 8.0,
                         force: bool = False) -> list[str]:
    """Free model ids available on `provider` right now. Cached for TTL. Returns []
    (and callers fall back to the static pool) when discovery can't run."""
    if provider != "openrouter":
        return []  # only OpenRouter exposes a catalogue we can read without a CLI
    with _CACHE_LOCK:
        cached = _CACHE.get(provider)
        if cached and not force and (time.time() - cached["at"]) < _ttl_s():
            return list(cached["models"])
        key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
        try:
            import requests
            headers = {"Authorization": f"Bearer {key}"} if key else {}
            r = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=timeout)
            if r.status_code >= 400:
                print(f"[MODEL_DISCOVERY] http_{r.status_code} — using static fallback", flush=True)
                return list(cached["models"]) if cached else []
            data = r.json().get("data") or []
            free = [str(m.get("id")) for m in data if isinstance(m, dict) and _is_free(m) and m.get("id")]
            _CACHE[provider] = {"at": time.time(), "models": free, "by_task": _categorize(free)}
            print(f"[MODEL_DISCOVERY] provider={provider} free_models={len(free)}", flush=True)
            return list(free)
        except Exception as exc:
            print(f"[MODEL_DISCOVERY] failed reason={type(exc).__name__} — static fallback", flush=True)
            return list(cached["models"]) if cached else []


def discovered_cached(provider: str = "openrouter") -> list[str]:
    """Non-blocking read of the discovery cache — NEVER makes a network call. Returns []
    if not yet warmed (caller falls back to the static pool). This is what the hot path
    uses; warm_discovery() populates the cache off the hot path."""
    with _CACHE_LOCK:
        cached = _CACHE.get(provider)
        if cached and (time.time() - cached["at"]) < _ttl_s():
            return list(cached["models"])
    return []


def free_models_for_task(provider: str, task: str | None, *, limit: int = 3) -> list[str]:
    """Up to `limit` free models best suited to the task (Darsh wants ~3), from live
    discovery. Empty -> caller uses the static model_policy pool."""
    models = discover_free_models(provider)
    if not models:
        return []
    with _CACHE_LOCK:
        by_task = (_CACHE.get(provider) or {}).get("by_task") or _categorize(models)
    ranked = by_task.get(task or "", []) if task else []
    # task-suited first, then any other free model as fallback, de-duped
    ordered = ranked + [m for m in models if m not in ranked]
    return ordered[:limit]


def research_task_models(task_description: str) -> dict:
    """On-demand (NOT hot-path): NEXI researches which current free model fits a task,
    using live discovery + a note to consult benchmarks. Returns a structured pick so
    the `which_model` tool / Studio can explain the choice out loud.

    This is deliberately shallow — a full web-benchmark crawl per selection is too slow
    for a voice turn; the categorizer + live discovery cover the common case, and this
    surfaces the candidate set for a human/Studio to confirm on hard tasks."""
    low = (task_description or "").lower()
    task = "code" if any(w in low for w in ("code", "bug", "refactor", "implement", "function")) \
        else "orchestration" if any(w in low for w in ("plan", "orchestrate", "research", "design")) \
        else "general"
    candidates = free_models_for_task("openrouter", task, limit=3)
    return {
        "task": task,
        "candidates": candidates,
        "source": "openrouter-live" if candidates else "static-fallback",
        "note": "Free models only. Confirm on benchmarks (e.g. lmarena / SWE-bench) for hard tasks.",
    }


def _demo() -> None:
    # categorization is pure and testable offline
    cats = _categorize(["cohere/north-mini-code:free", "nvidia/nemotron-3-ultra:free", "tencent/hy3:free"])
    assert "cohere/north-mini-code:free" in cats["code"], cats
    assert "nvidia/nemotron-3-ultra:free" in cats["orchestration"], cats
    assert _is_free({"id": "x/y:free"})
    assert _is_free({"id": "x/y", "pricing": {"prompt": "0", "completion": "0"}})
    assert not _is_free({"id": "x/y", "pricing": {"prompt": "0", "completion": "0.5"}})
    print("model_discovery._demo OK")


if __name__ == "__main__":
    _demo()
