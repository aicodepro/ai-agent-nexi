"""Per-runtime model pools + per-task selection with fallback.

Darsh's model: each agent runtime already switches models internally —
claude-code across Sonnet/Opus/Fable, opencode across its free pool (NVIDIA NIM,
DeepSeek, etc.), Hermes across OpenAI/opencode/Anthropic. NEXI does NOT impose one
global default model (explicitly NOT gemini-2.5-flash). Instead it hands each runtime
an ORDERED, FREE-FIRST chain for the task and lets the runtime run it; if a model
fails, the next in the chain is tried.

Rules:
  * No single hardcoded default — a task resolves to a *chain*, not one model.
  * Free models first. Paid/subscription models only after the free ones.
  * Per-runtime pools, env-overridable (a deployment's actual accounts differ).
  * OpenRouter is FREE-models-only here (Darsh: the OpenRouter key is for free
    models). Paid OpenRouter ids are not placed in any default chain.

This is policy/ordering only — the adapters do the actual CLI invocation.
"""
from __future__ import annotations

import os
import threading

# Each entry: ordered model ids, FREE-first. `tasks` maps a task to the id to try
# FIRST; the rest of the pool follows as fallback. `free` marks the no-cost ids (free
# API tiers). Subscription models (Claude Max, OpenAI Plus) are allowed but ranked
# AFTER free. Everything is overridable via env (NEXI_<RUNTIME>_MODELS, comma list),
# because the exact free ids on each account drift — keep ~3 per provider as Darsh
# asked. Model versions here (4.8, 3.5, ...) are swappable; the ids are examples.
POOLS: dict[str, dict] = {
    # claude-code = Claude Max subscription, switches within the Claude family. No
    # per-call cost (subscription), so treated as free for ordering; task maps pick tier.
    "claude-code": {
        "models": ["claude-sonnet-5", "claude-opus-4-8", "claude-fable-5", "claude-haiku-4-5"],
        "free": ["claude-sonnet-5", "claude-opus-4-8", "claude-fable-5", "claude-haiku-4-5"],
        # HEAVY work -> strongest model; LIGHT work -> cheapest. One CLI runs every task
        # (Darsh picks it); only the model tier changes with the weight of the work.
        # FOUR tiers, each earning its place (Darsh: use haiku/sonnet/fable/opus per
        # need). opus = hardest reasoning; fable = strong generalist just under opus;
        # sonnet = standard engineering; haiku = trivial/high-volume.
        "tasks": {
            "orchestration": "claude-opus-4-8",    # hardest reasoning
            "architecture": "claude-opus-4-8",
            "debug": "claude-opus-4-8",            # root-causing is the hardest work
            "self_improve": "claude-opus-4-8",     # it rewrites Nexi — do not cheap out
            "code": "claude-opus-4-8",             # real programming
            "security": "claude-opus-4-8",
            "research": "claude-fable-5",          # broad synthesis, cheaper than opus
            "analysis": "claude-fable-5",
            "review": "claude-fable-5",
            "test": "claude-sonnet-5",             # standard engineering
            "ui": "claude-sonnet-5",
            "integration": "claude-sonnet-5",
            "docs": "claude-haiku-4-5",            # high-volume, low-risk
            "quick": "claude-haiku-4-5",
            "chat": "claude-haiku-4-5",
            "lookup": "claude-haiku-4-5",
        },
        "env": "NEXI_CLAUDE_CODE_MODELS",
    },
    # opencode's FREE pool — the ids Darsh named (DeepSeek v4 Flash free, MiniMax M3
    # free, etc.). opencode takes an API key only (a Claude token is NOT an API key), so
    # these are the free-API models. Override with NEXI_OPENCODE_MODELS for your account.
    "opencode": {
        # Two tiers in ONE pool: subscription-strength models for real programming
        # (Darsh has OpenAI Plus + Claude Max; opencode accepts an API KEY only — a
        # Claude Code token is NOT an API key), and free models for lightweight turns.
        # Ids are examples/hints: live discovery replaces the free tier at runtime and
        # NEXI_OPENCODE_MODELS overrides the whole list.
        "models": [
            "openai/gpt-5.2",                  # heavy: programming/orchestration
            "anthropic/claude-opus-4-8",       # heavy: hardest reasoning
            "deepseek/deepseek-v4-flash:free",  # light: small tasks, free
            "minimax/minimax-m3:free",
            "cohere/north-mini-code:free",
        ],
        "free": [
            "deepseek/deepseek-v4-flash:free",
            "minimax/minimax-m3:free",
            "cohere/north-mini-code:free",
        ],
        "tasks": {
            "orchestration": "openai/gpt-5.2",
            "architecture": "anthropic/claude-opus-4-8",
            "code": "openai/gpt-5.2",              # real programming = strong model
            "debug": "anthropic/claude-opus-4-8",
            "research": "openai/gpt-5.2",
            "self_improve": "anthropic/claude-opus-4-8",
            "review": "deepseek/deepseek-v4-flash:free",
            "test": "deepseek/deepseek-v4-flash:free",   # light: cheap + fast
            "ui": "minimax/minimax-m3:free",
            "docs": "deepseek/deepseek-v4-flash:free",
            "quick": "deepseek/deepseek-v4-flash:free",
            "chat": "deepseek/deepseek-v4-flash:free",
        },
        "env": "NEXI_OPENCODE_MODELS",
    },
    # Hermes wired to OpenAI + opencode + Anthropic; free-first, then the subscriptions.
    "hermes": {
        "models": ["deepseek/deepseek-v4-flash:free", "gpt-4o-mini", "claude-haiku-4-5"],
        "free": ["deepseek/deepseek-v4-flash:free"],
        "tasks": {},
        "env": "NEXI_HERMES_MODELS",
    },
    # OpenRouter: FREE models only (Darsh: the OpenRouter key is for free models).
    # ":free" ids are OpenRouter's no-cost variants. Exactly ~3 as requested.
    "openrouter": {
        "models": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-chat-v3:free",
            "qwen/qwen-2.5-coder-32b-instruct:free",
        ],
        "free": [
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-chat-v3:free",
            "qwen/qwen-2.5-coder-32b-instruct:free",
        ],
        "tasks": {"code": "qwen/qwen-2.5-coder-32b-instruct:free"},
        "env": "NEXI_OPENROUTER_MODELS",
    },
}


def _pool(runtime: str) -> dict:
    return POOLS.get(runtime, {"models": [], "free": [], "tasks": {}, "env": ""})


def _models(runtime: str) -> list[str]:
    """The runtime's model list. Priority:
      1. explicit env override (comma list) — operator's account wins;
      2. LIVE-discovered free models (openrouter) if the discovery cache is already
         warm — no hardcoding, and non-blocking (never fetch in the hot path, per the
         e5 lesson: warm it in the background via warm_discovery());
      3. the static pool as the offline fallback.
    """
    pool = _pool(runtime)
    override = (os.getenv(pool.get("env", "")) or "").strip()
    if override:
        return [m.strip() for m in override.split(",") if m.strip()]
    if runtime in ("openrouter", "opencode"):
        # opencode can consume OpenRouter-hosted free models too; both share the live
        # free set. Cached-read only — returns [] instantly if not yet warmed, and kicks
        # off a ONE-SHOT background warm so the next call has live data. Never blocks.
        try:
            from engine.agent_runtime import model_discovery
            live = model_discovery.discovered_cached("openrouter")
            if live:
                return live
            _warm_once()
        except Exception:
            pass
    return list(pool.get("models", []))


_WARMED = False
_WARM_LOCK = threading.Lock()


def _warm_once() -> None:
    global _WARMED
    with _WARM_LOCK:
        if _WARMED:
            return
        _WARMED = True
    warm_discovery()


def warm_discovery() -> None:
    """Populate the live free-model cache in a background thread so the hot path can
    read it without a network call. Safe to call at startup; no-op without a key."""
    import threading

    def _run():
        try:
            from engine.agent_runtime import model_discovery
            model_discovery.discover_free_models("openrouter")
        except Exception:
            pass
    threading.Thread(target=_run, name="nexi-model-discovery-warm", daemon=True).start()


def model_chain(runtime: str, task: str | None = None, exclude_down: bool = True) -> list[str]:
    """Ordered models to try for (runtime, task): task-preferred first, then free
    models, then the rest (subscription) as fallback. Never a single default — always a
    chain, so a failure has somewhere to fall back to. Models currently benched by the
    health tracker (failed too many times) are dropped, which is the self-healing part:
    a model that stops working falls out of selection until its cooldown passes.
    Set exclude_down=False to see the full pool ignoring health (for diagnostics)."""
    pool = _pool(runtime)

    # An explicit operator override ALWAYS wins — over discovery and over the static
    # pool. If Darsh pins NEXI_OPENCODE_MODELS, that is a decision, not a hint, and
    # auto-discovery must not quietly overrule it.
    override = (os.getenv(pool.get("env", "")) or "").strip()

    # Otherwise: no hardcoded model names. Ask the CLI what it actually has right now,
    # rank it by capability (refreshable benchmark table), and pick by the weight of the
    # work. A new model works the day it appears; a removed one stops being offered.
    # The static pool below is only the offline fallback.
    try:
        if override:
            raise RuntimeError("operator override set; skip discovery")
        from engine.agent_runtime import model_ranking
        from engine.agent_runtime.cli_capabilities import task_weight
        live = model_ranking.discover_cli_models(runtime)
        if live:
            chain = model_ranking.select(live, task_weight(task or ""), limit=6)
            if exclude_down:
                from engine.agent_runtime import model_health
                chain = model_health.healthy(runtime, chain) or chain
            if chain:
                return chain
    except Exception:
        pass  # discovery unavailable -> fall through to the static pool

    models = _models(runtime)
    if not models:
        return []
    free = set(pool.get("free", []))

    ordered: list[str] = []
    # 1. the task's preferred model, if it is actually in the (possibly overridden) pool
    preferred = pool.get("tasks", {}).get(task) if task else None
    if preferred and preferred in models:
        ordered.append(preferred)

    # 2. Order the FALLBACKS by the weight of the work.
    #    HEAVY (programming, orchestration, debugging): fall back to other STRONG models
    #    before cheap ones — dropping a real programming task onto a small free model
    #    produces bad code, which costs more time than it saves.
    #    LIGHT (quick edits, docs, chat): free-first, to save tokens/money/time.
    # Heavy ordering only when a task is NAMED and classified heavy. With no task given,
    # stay free-first — a caller who didn't say the work is hard shouldn't silently be
    # put on the expensive tier. (Cost default: free; opt UP for real programming.)
    try:
        from engine.agent_runtime.cli_capabilities import task_weight
        heavy = bool(task) and task_weight(task) == "heavy"
    except Exception:
        heavy = False

    tiers = ([m for m in models if m not in free], [m for m in models if m in free]) \
        if heavy else ([m for m in models if m in free], [m for m in models if m not in free])
    for tier in tiers:
        for m in tier:
            if m not in ordered:
                ordered.append(m)

    if exclude_down:
        from engine.agent_runtime import model_health
        healthy = model_health.healthy(runtime, ordered)
        # If EVERY model is benched, don't strand the runtime with nothing — return the
        # full ordered list so it can at least try the least-bad option (and re-probe
        # health). A model down-list must never become a total outage.
        return healthy or ordered
    return ordered


def select_model(runtime: str, task: str | None = None) -> str | None:
    """The first model to try for (runtime, task), or None if the pool is empty."""
    chain = model_chain(runtime, task)
    return chain[0] if chain else None


def _demo() -> None:
    # no single default; a task yields a chain
    chain = model_chain("claude-code", "orchestration")
    assert chain[0] == "claude-opus-4-8", chain           # task preference first
    assert len(chain) > 1, "a chain must have fallbacks"
    assert model_chain("claude-code", "quick")[0] == "claude-haiku-4-5"
    # free-first on opencode
    oc = model_chain("opencode")
    assert oc and all("/" in m for m in oc), oc
    # env override wins
    os.environ["NEXI_OPENCODE_MODELS"] = "acme/free-1, acme/free-2"
    assert model_chain("opencode")[0] == "acme/free-1"
    del os.environ["NEXI_OPENCODE_MODELS"]
    # unknown runtime -> empty, no crash
    assert model_chain("nope") == []
    print("model_policy._demo OK ->", {t: select_model("claude-code", t)
                                       for t in ("orchestration", "code", "quick")})


if __name__ == "__main__":
    _demo()
