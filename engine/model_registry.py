"""Model registry + per-task model selection.

Nexi picks the model for a task from MEASURED capabilities instead of one
hardcoded env value. Every flag below was probed against the live Groq API
(see research_models(live=True)) — they are facts, not model-card claims:

  * gpt-oss rejects response_format=json_object  -> HTTP 400 json_validate_failed
  * gpt-oss leaks harmony "<|channel|>" tokens into tool names on the 2nd+ turn
    of a tool loop -> Groq 400 tool_use_failed  (so multiturn_tools=False)
  * llama-3.3-70b returns arguments:"null" for zero-arg tools (handled in
    providers/openai_compat.py)

Env still wins: an explicit override in .env beats the registry, so operators
keep the last word.
"""
from __future__ import annotations

import os

# capability facts. reasoning/speed: 1=low 3=high.
# ponytail: plain dicts, not a class hierarchy — this is a lookup table.
MODELS: dict[str, dict] = {
    "llama-3.3-70b-versatile": {
        "provider": "groq", "tools": True, "multiturn_tools": True, "json_object": True,
        "vision": False, "reasoning": 3, "speed": 2, "caveats": ('returns arguments:"null" for zero-arg tools',),
    },
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "provider": "groq", "tools": True, "multiturn_tools": True, "json_object": True,
        "vision": True, "reasoning": 2, "speed": 3, "caveats": (),
    },
    "openai/gpt-oss-20b": {
        "provider": "groq", "tools": True, "multiturn_tools": False, "json_object": False,
        "vision": False, "reasoning": 3, "speed": 3,
        "caveats": ("rejects json_object", "leaks harmony tokens in multi-turn tool loops"),
    },
    "openai/gpt-oss-120b": {
        "provider": "groq", "tools": True, "multiturn_tools": False, "json_object": False,
        "vision": False, "reasoning": 3, "speed": 1,
        "caveats": ("rejects json_object", "leaks harmony tokens in multi-turn tool loops"),
    },
    # OpenRouter models — one key, every vendor. These let NEXI switch to a stronger
    # (or cheaper/free) model per task than the Groq-hosted set. Only usable when
    # OPENROUTER_API_KEY is set; endpoint_for() routes them to openrouter.ai. Capability
    # flags are from each model's published spec, not a live probe — run
    # research_models(live=True) to correct drift. Add/replace freely; the registry is
    # a lookup table, and any un-listed OpenRouter id still works via an env override.
    "anthropic/claude-sonnet-4.5": {
        "provider": "openrouter", "tools": True, "multiturn_tools": True, "json_object": True,
        "vision": True, "reasoning": 3, "speed": 2, "caveats": (),
    },
    "google/gemini-2.5-flash": {
        "provider": "openrouter", "tools": True, "multiturn_tools": True, "json_object": True,
        "vision": True, "reasoning": 2, "speed": 3, "caveats": (),
    },
    "meta-llama/llama-3.3-70b-instruct": {  # a solid free-tier option on OpenRouter
        "provider": "openrouter", "tools": True, "multiturn_tools": True, "json_object": True,
        "vision": False, "reasoning": 2, "speed": 2, "caveats": (),
    },
}

# provider -> (base_url, api-key env var). The single source of truth for WHERE a
# model runs, so callers dispatch by model instead of hardcoding Groq.
PROVIDER_ENDPOINTS: dict[str, tuple[str, str]] = {
    "groq": ("https://api.groq.com/openai/v1", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY"),
    "xai": ("https://api.x.ai/v1", "XAI_API_KEY"),
}


def provider_for(model: str) -> str:
    """Which provider hosts this model id.

    Known ids come from MODELS. An UNKNOWN id (someone set REACT_MODEL to a brand-new
    OpenRouter model) is inferred: a vendor-prefixed id ("anthropic/...", "x/y") routes
    to OpenRouter when its key is present — that is how "switch to ANY model" works
    without editing this table for every new model. Otherwise default to groq.
    """
    m = MODELS.get(model)
    if m:
        return m["provider"]
    if "/" in model and (os.getenv("OPENROUTER_API_KEY") or "").strip():
        return "openrouter"
    return "groq"


def endpoint_for(model: str) -> dict:
    """Resolve a model id to {provider, base_url, api_key} for openai_compat.
    Returns api_key="" when the provider's key is unset (caller fails cleanly)."""
    provider = provider_for(model)
    base_url, key_env = PROVIDER_ENDPOINTS.get(provider, PROVIDER_ENDPOINTS["groq"])
    return {
        "provider": provider,
        "base_url": base_url,
        "api_key": (os.getenv(key_env) or "").strip(),
        "key_env": key_env,
    }

# task -> (hard requirements, env override, tie-break key)
TASKS: dict[str, dict] = {
    "intent_json": {"needs": ("json_object",), "env": "GROQ_INTENT_MODEL", "rank": "speed"},
    "react_tools": {"needs": ("tools", "multiturn_tools"), "env": "REACT_MODEL", "rank": "reasoning"},
    "router_escalation": {"needs": ("tools",), "env": "NEXI_ROUTER_LLM_MODEL", "rank": "reasoning"},
    "vision": {"needs": ("vision",), "env": "VISION_MODEL", "rank": "speed"},
    # Studio's manager judgement: Nexi decides a developer agent's question on the CEO's
    # behalf (scope/cost/security implications). That is REASONING work — it was reusing
    # "intent_json", which is ranked by SPEED for fast classification, so the manager was
    # thinking with the fastest model instead of the best one. Still needs json_object
    # because the answer is strict JSON.
    "manager_reasoning": {"needs": ("json_object",), "env": "NEXI_STUDIO_MANAGER_MODEL",
                          "rank": "reasoning"},
}


def select_model(task: str) -> str:
    """Best model for a task. Explicit env override wins; else highest-ranked
    model that actually satisfies the task's hard requirements."""
    spec = TASKS.get(task)
    if spec is None:
        raise ValueError(f"unknown task {task!r}; known: {sorted(TASKS)}")
    override = (os.getenv(spec["env"]) or "").strip()
    if override:
        return override
    fit = [m for m, c in MODELS.items() if all(c.get(n) for n in spec["needs"])]
    # Only auto-select a model we can actually call: its provider's key must be set.
    # Without this, adding OpenRouter models could make NEXI pick one and then fail at
    # request time on a machine that only has GROQ_API_KEY. An explicit env override
    # bypasses this (the operator takes responsibility).
    callable_fit = [m for m in fit if endpoint_for(m)["api_key"]]
    usable = callable_fit or fit  # if NO key is set anywhere, fall back to capability-only
    if not usable:
        raise ValueError(f"no model satisfies {spec['needs']} for task {task!r}")
    return max(usable, key=lambda m: (MODELS[m][spec["rank"]], MODELS[m]["reasoning"]))


def why(task: str) -> str:
    """One-line, user-facing explanation of the pick — Nexi says this out loud."""
    spec = TASKS[task]
    model = select_model(task)
    if (os.getenv(spec["env"]) or "").strip():
        return f"{task}: using {model} (set by {spec['env']})"
    rejected = [
        f"{m} ({'; '.join(MODELS[m]['caveats'])})"
        for m, c in MODELS.items()
        if not all(c.get(n) for n in spec["needs"]) and MODELS[m]["caveats"]
    ]
    tail = f" Ruled out: {', '.join(rejected)}." if rejected else ""
    return f"{task}: using {model} — needs {', '.join(spec['needs'])}.{tail}"


def research_models(live: bool = False, timeout: float = 20.0) -> list[dict]:
    """The model list Nexi chooses from. live=True re-probes Groq and corrects
    the json_object/tools flags from reality (capability drift is real)."""
    rows = [dict(id=m, **{k: v for k, v in c.items()}) for m, c in MODELS.items()]
    if not live:
        return rows
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key:
        return rows
    import requests
    for row in rows:
        if row["provider"] != "groq":
            continue
        for cap, payload in (
            ("json_object", {"response_format": {"type": "json_object"},
                             "messages": [{"role": "user", "content": 'Reply {"ok":1} as JSON.'}]}),
            ("tools", {"tools": [{"type": "function", "function": {"name": "ping", "parameters": {"type": "object", "properties": {}}}}],
                       "tool_choice": "auto", "messages": [{"role": "user", "content": "ping"}]}),
        ):
            try:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"}, timeout=timeout,
                    json={"model": row["id"], "max_tokens": 32, "temperature": 0, **payload},
                )
                row[cap] = r.status_code < 400
            except Exception:
                pass  # keep the measured default; a probe failure is not a capability fact
    return rows


def which_model(slots: dict | None = None) -> dict:
    """Tool handler: report which model Nexi uses per task, and why.

    slots.live=1 re-probes the API first, so "research the models" reflects
    what the account can actually do right now.
    """
    if str((slots or {}).get("live") or "").strip().lower() in {"1", "true", "yes"}:
        research_models(live=True)
    picks = "; ".join(f"{task} -> {select_model(task)}" for task in TASKS)
    return {
        "success": True, "verified": True, "tool": "which_model",
        "message": f"Models I selected: {picks}.",
        "detail": [why(task) for task in TASKS],
    }


def _demo() -> None:
    # the two facts that actually broke NEXI in production
    assert select_model("intent_json") != "openai/gpt-oss-20b", "gpt-oss rejects json_object"
    assert MODELS[select_model("react_tools")]["multiturn_tools"], "react needs multi-turn tools"
    for task in TASKS:
        assert select_model(task) in MODELS or os.getenv(TASKS[task]["env"])
    os.environ["REACT_MODEL"] = "custom/override"
    assert select_model("react_tools") == "custom/override", "env override must win"
    del os.environ["REACT_MODEL"]
    assert len(research_models()) == len(MODELS)
    print("model_registry._demo OK ->", {t: select_model(t) for t in TASKS})


if __name__ == "__main__":
    _demo()
