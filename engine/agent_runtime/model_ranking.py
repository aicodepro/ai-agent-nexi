"""Rank whatever models are ACTUALLY available, then pick by task weight.

Darsh's rule: no hardcoded model names. NEXI must look at what the selected CLI
offers right now (`opencode models` returns ~380 across 9 providers, and the free set
changes constantly), rank it, and choose per task — strong models for real programming,
cheap free ones for small turns.

So nothing here names a model for a task. Instead each DISCOVERED id is scored from
signals in the id itself plus a refreshable benchmark table, and selection is by score:

    heavy work  -> highest capability available
    light work  -> cheapest/fastest that is still competent (free preferred)

`BENCHMARKS` is a cache, not a hardcode: it maps a family substring to a measured
capability score and is meant to be refreshed from public leaderboards
(refresh_benchmarks()). If a model is unknown, it is scored from its id signals rather
than being dropped — a brand-new model must still be usable the day it appears.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path

# Capability scores (0-100) by family substring, from public benchmark standings
# (SWE-bench / LMArena class). REFRESHABLE — see refresh_benchmarks(). Substrings, not
# exact ids, so a version bump (4.8 -> 4.9) keeps working without an edit.
BENCHMARKS: dict[str, int] = {
    # frontier — newer point-releases score above their family baseline
    "gpt-5.6": 96, "gpt-5.5": 95, "gpt-5.4": 94, "gpt-5": 93,
    "opus-4-8": 96, "opus-4-7": 94, "opus-4-6": 93, "opus": 92,
    "codex": 93,                       # code-specialised OpenAI variants
    "fable": 90, "sonnet-5": 89, "sonnet": 87,
    "gemini-3.1-pro": 89, "gemini-3-pro": 88, "gemini-2.5-pro": 84,
    "grok-4": 86, "deepseek-v4-pro": 88, "deepseek-r1": 84, "deepseek-v4": 84,
    "kimi-k2.7": 84, "kimi-k2": 82, "glm-5": 83, "glm-4.7": 79,
    "qwen3.6": 83, "qwen3.5": 81, "qwen3-coder": 82, "qwen3": 78,
    "nemotron-3-ultra": 84, "nemotron-3-super": 78, "minimax-m3": 78, "minimax-m2": 74,
    "llama-4": 78, "llama-3.3": 74, "mistral-large": 76, "gpt-oss-120b": 76,
    "gpt-oss": 70, "step-3.7": 72, "north-mini-code": 74, "hy3": 74, "mimo": 70,
    # cheap/fast tiers
    "haiku": 68, "flash": 66, "mini": 60, "lite": 55, "nano": 52, "small": 50,
}
_BENCHMARK_LOCK = threading.RLock()

# Signals that a model is cheap/fast rather than strong. Used for the LIGHT tier and to
# damp the score of small variants that share a strong family name (gpt-5-nano).
_SMALL = ("nano", "mini", "lite", "small", "flash", "haiku", "tiny", "8b", "7b", "3b", "1b")
_FREE = ("-free", ":free", "/free")

_CACHE: dict[str, dict] = {}
_BENCH_PATH = Path(os.getenv("NEXI_BENCHMARK_CACHE", "")) if os.getenv("NEXI_BENCHMARK_CACHE") else None


def _ttl() -> float:
    try:
        return max(30.0, float(os.getenv("NEXI_MODEL_LIST_TTL_S", "600")))
    except ValueError:
        return 600.0


def is_free(model: str) -> bool:
    m = model.lower()
    return any(tok in m for tok in _FREE)


def is_small(model: str) -> bool:
    m = model.lower()
    return any(tok in m for tok in _SMALL)


def score(model: str) -> int:
    """Capability score for ANY model id, known or brand-new."""
    m = model.lower()
    best = 0
    with _BENCHMARK_LOCK:
        benchmarks = list(BENCHMARKS.items())
    for family, val in benchmarks:
        if family in m:
            best = max(best, val)
    if best == 0:
        # Unknown model: infer from size/tier signals so it is still usable today.
        best = 45 if is_small(m) else 65
    # A small variant of a strong family is not the strong model.
    if is_small(m) and best > 70:
        best = min(best, 66)
    return best


def _hermes_model_cache_paths() -> list[Path]:
    """Where Hermes keeps its model-picker cache. HERMES_HOME first, then defaults."""
    roots = []
    hh = (os.getenv("HERMES_HOME") or "").strip()
    if hh:
        roots.append(Path(hh))
    roots += [Path.home() / ".hermes", Path("D:/hermes")]
    out = []
    for r in roots:
        out.append(r / "cache" / "model_catalog.json")
    return out


def _hermes_models_from_cache() -> list[str]:
    """Parse `provider/model` ids out of Hermes' model_catalog.json.

    Shape: {"providers": {"<provider>": {"metadata": {...}, "models": [...] }}}
    The models list may hold plain strings or dicts with an id/name — accept both, since
    a cache-format change should degrade to "no models discovered", never crash a turn.
    """
    for path in _hermes_model_cache_paths():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        providers = data.get("providers")
        if not isinstance(providers, dict):
            continue
        found: list[str] = []
        for prov, body in providers.items():
            entries = (body or {}).get("models") if isinstance(body, dict) else None
            if isinstance(entries, dict):
                entries = list(entries.keys())
            if not isinstance(entries, list):
                continue
            for e in entries:
                mid = e if isinstance(e, str) else (
                    (e.get("id") or e.get("name")) if isinstance(e, dict) else None)
                if not mid:
                    continue
                found.append(str(mid) if "/" in str(mid) else f"{prov}/{mid}")
        if found:
            print(f"[MODEL_RANK] hermes catalogue={len(found)} from {path.name}", flush=True)
            return sorted(set(found))
    return []


def discover_cli_models(cli: str, *, timeout: float = 60.0, force: bool = False) -> list[str]:
    """Ask the CLI what models it actually has. No static list."""
    cached = _CACHE.get(cli)
    if cached and not force and (time.time() - cached["at"]) < _ttl():
        return list(cached["models"])
    models: list[str] = []

    # Hermes has no non-interactive list command (`hermes model` opens a picker and
    # would hang an automated call). It does keep a model-picker DISK CACHE of every
    # provider's live /v1/models, so read that instead of driving the TUI.
    if cli == "hermes":
        models = _hermes_models_from_cache()
        if models:
            _CACHE[cli] = {"at": time.time(), "models": models}
            return models

    cmds = {
        "opencode": ["opencode", "models"],
        "claude-code": [],          # fixed family; no list command to scrape
    }
    argv = cmds.get(cli) or []
    if argv:
        try:
            out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                 encoding="utf-8", errors="replace")
            for line in (out.stdout or "").splitlines():
                line = line.strip()
                # provider/path... — the model segment may itself contain slashes and @:
                #   huggingface/deepseek-ai/DeepSeek-V4-Pro
                #   cloudflare-workers-ai/@cf/meta/llama-4-scout-17b-16e-instruct
                # An earlier single-slash pattern silently dropped ~275 of 380 real
                # models, so NEXI could only ever pick from a quarter of the catalogue.
                # Plugin banners are excluded because they contain spaces or brackets.
                if re.fullmatch(r"[A-Za-z0-9_.\-]+/[A-Za-z0-9_.:@/\-]+", line):
                    models.append(line)
        except Exception as exc:
            print(f"[MODEL_RANK] discover_failed cli={cli} reason={type(exc).__name__}", flush=True)
    if models:
        _CACHE[cli] = {"at": time.time(), "models": models}
    return models


def rank(models: list[str]) -> list[str]:
    """Strongest first. Ties broken by preferring free (cheaper for the same power)."""
    return sorted(models, key=lambda m: (-score(m), not is_free(m), m))


def select(models: list[str], weight: str = "heavy", *, limit: int = 5) -> list[str]:
    """Ordered chain for the weight of the work — the chain, never a single model.

    heavy: strongest first (a real programming task on a tiny model wastes more time
           than the cheaper model saves).
    light: cheapest competent first, free preferred, but never junk — a floor keeps
           obviously-weak models out even of the light tier.
    """
    if not models:
        return []
    if weight == "light":
        light = [m for m in models if is_free(m) or is_small(m)]
        pool = light or models
        # cheapest-but-competent: prefer free, then higher score among the small set
        ordered = sorted(pool, key=lambda m: (not is_free(m), -score(m), m))
        # always keep a strong fallback at the end in case every cheap model fails
        strong = rank([m for m in models if m not in ordered])[:1]
        return (ordered + strong)[:limit]
    return rank(models)[:limit]


def refresh_benchmarks(source: dict[str, int] | None = None, path: str | Path | None = None) -> int:
    """Update the capability table from researched data (a leaderboard scrape, or a
    hand-curated JSON). Keeps NEXI current without a code change — the whole point of
    not hardcoding. Returns how many entries were applied."""
    data = source
    p = Path(path) if path else _BENCH_PATH
    if data is None and p and p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            data = None
    if not isinstance(data, dict):
        return 0
    applied = 0
    with _BENCHMARK_LOCK:
        for k, v in data.items():
            try:
                BENCHMARKS[str(k).lower()] = int(v)
                applied += 1
            except (TypeError, ValueError):
                continue
    return applied


def explain(model: str) -> str:
    return (f"{model}: score={score(model)} "
            f"{'free ' if is_free(model) else ''}{'small' if is_small(model) else 'full-size'}")


def _demo() -> None:
    pool = ["opencode/claude-opus-4-8", "opencode/gpt-5-nano",
            "opencode/deepseek-v4-flash-free", "opencode/gemini-3.1-pro",
            "opencode/some-brand-new-model"]
    heavy = select(pool, "heavy")
    light = select(pool, "light")
    assert "opus" in heavy[0] or "gpt-5" in heavy[0] or "pro" in heavy[0], heavy
    assert is_free(light[0]) or is_small(light[0]), light
    # a small variant of a strong family must not outrank the real thing
    assert score("opencode/claude-opus-4-8") > score("opencode/gpt-5-nano")
    # unknown models are still usable
    assert score("opencode/some-brand-new-model") > 0
    # benchmark table is refreshable, not hardcoded
    assert refresh_benchmarks({"some-brand-new-model": 99}) == 1
    assert score("opencode/some-brand-new-model") == 99
    BENCHMARKS.pop("some-brand-new-model", None)
    print("model_ranking._demo OK")
    print("  heavy ->", heavy[:3])
    print("  light ->", light[:3])


if __name__ == "__main__":
    import sys
    if "--demo" in sys.argv:
        _demo()
    else:
        cli = sys.argv[1] if len(sys.argv) > 1 else "opencode"
        found = discover_cli_models(cli, force=True)
        print(f"{cli}: discovered {len(found)} models")
        print("  HEAVY:", select(found, "heavy", limit=5))
        print("  LIGHT:", select(found, "light", limit=5))
