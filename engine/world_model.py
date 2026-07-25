"""Nexi's current-situation state.

One process-wide snapshot of what is true right now: what the user asked for,
what Nexi last did, and what the machine looks like. Read by the router's
context builder on every turn, written at turn boundaries and by the ambient
sampler.

This is deliberately NOT another memory store. The 14 stores under data/ answer
"what happened before"; this answers "what is happening now" and is small enough
to fit in every prompt.
"""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_STORE = Path(__file__).resolve().parents[1] / "data" / "memory" / "world_model.json"

# Turn-scoped fields. Reloading these from a snapshot written days ago would let
# Nexi say "I just opened Chrome" about last week, which is the exact class of
# false claim the router's brain-signal narrowing already fought. Dropped when
# the snapshot is stale; environment and working_memory are durable and kept.
_VOLATILE = ("user_intent", "last_action", "last_result", "current_step")


def _stale_after_seconds() -> float:
    # ponytail: read per call, not at import, so tests and .env reloads can move it
    try:
        return float(os.getenv("NEXI_WORLD_STALE_SECONDS", "900"))
    except (TypeError, ValueError):
        return 900.0


@dataclass
class WorldState:
    user_intent: str = ""
    last_action: str = ""
    last_result: str = ""
    current_step: str = ""
    environment: dict[str, Any] = field(default_factory=dict)
    working_memory: dict[str, Any] = field(default_factory=dict)
    updated_at: float = 0.0


_LOCK = threading.RLock()
_WORLD = WorldState()


def update_world(*, persist: bool = True, **fields: Any) -> None:
    """Merge fields into the world state.

    Dict fields merge shallowly so an ambient sampler tick writing `environment`
    never wipes project facts written by a turn. Pass persist=False for
    high-frequency writes; they land on disk with the next turn-boundary write.
    """
    if not fields:
        return
    with _LOCK:
        for key, value in fields.items():
            if key == "updated_at" or not hasattr(_WORLD, key):
                continue
            current = getattr(_WORLD, key)
            if isinstance(current, dict) and isinstance(value, dict):
                current.update(value)
            else:
                setattr(_WORLD, key, value)
        _WORLD.updated_at = time.time()
        if persist:
            _save_locked()


def get_world() -> dict[str, Any]:
    with _LOCK:
        return asdict(_WORLD)


def to_prompt_block() -> str:
    state = get_world()
    parts: list[str] = []
    if state["user_intent"]:
        parts.append(f"  Intent: {str(state['user_intent'])[:300]}")
    if state["last_action"]:
        parts.append(f"  Last: {state['last_action']} -> {str(state['last_result'])[:200]}")
    if state["current_step"]:
        parts.append(f"  Step: {state['current_step']}")
    if state["environment"]:
        env = "; ".join(f"{k}={v}" for k, v in list(state["environment"].items())[:6])
        parts.append(f"  Env: {env}")
    if state["working_memory"]:
        mem = "; ".join(f"{k}={v}" for k, v in list(state["working_memory"].items())[:3])
        parts.append(f"  Memory: {mem}")
    if not parts:
        return ""
    return "\n".join(["[World]"] + parts)


def reset_world(*, keep_durable: bool = True) -> None:
    """Clear turn-scoped state. Durable environment/project facts survive by default."""
    global _WORLD
    with _LOCK:
        environment = dict(_WORLD.environment) if keep_durable else {}
        working_memory = dict(_WORLD.working_memory) if keep_durable else {}
        _WORLD = WorldState(environment=environment, working_memory=working_memory)
        _save_locked()


# ── Ambient sampler ────────────────────────────────────────────────────────
# Every signal below already existed as a tool. The only thing missing was a
# clock: tools answer "what is my CPU" when asked and can never notice anything.

_SAMPLER: threading.Thread | None = None
_SAMPLER_STOP = threading.Event()


def _env_off(name: str, default: str = "1") -> bool:
    return (os.getenv(name, default) or "").strip().lower() in {"0", "false", "no", "off"}


def _sampler_interval() -> float:
    try:
        return max(1.0, float(os.getenv("NEXI_WORLD_SAMPLE_SECONDS", "10")))
    except (TypeError, ValueError):
        return 10.0


def _sample_environment() -> dict[str, Any]:
    """Read current machine state through os_awareness' public tool functions."""
    env: dict[str, Any] = {}
    try:
        from engine.os_awareness import get_active_window

        window = get_active_window()
        app = str(window.get("active_app") or "").rsplit(".", 1)[0]
        if app:
            env["active_app"] = app
        title = str(window.get("active_title") or "")
        # Window titles carry document and page names. Low-risk by this repo's own
        # tool card, but it lands in every prompt -- NEXI_WORLD_SAMPLE_TITLES=0 opts out.
        if title and not _env_off("NEXI_WORLD_SAMPLE_TITLES"):
            env["active_title"] = title[:120]
    except Exception:
        pass
    try:
        from engine.os_awareness import get_system_state

        state = get_system_state()
        env["cpu_percent"] = state.get("cpu")
        env["memory_percent"] = state.get("mem")
    except Exception:
        pass
    try:
        from engine.os_awareness import get_idle_time

        env["idle_seconds"] = round(float(get_idle_time().get("idle_seconds") or 0))
    except Exception:
        pass
    return {key: value for key, value in env.items() if value is not None}


def _sampler_loop(interval: float) -> None:
    # wait() first so the sampler never competes with the startup import burst
    while not _SAMPLER_STOP.wait(interval):
        try:
            env = _sample_environment()
            if env:
                update_world(environment=env, persist=False)
        except Exception:
            pass


def start_world_sampler(interval: float | None = None) -> bool:
    """Start the ambient perception tick. Idempotent; returns False if already running."""
    global _SAMPLER
    if _env_off("NEXI_WORLD_SAMPLER"):
        print("[WORLD] sampler disabled", flush=True)
        return False
    with _LOCK:
        if _SAMPLER is not None and _SAMPLER.is_alive():
            return False
        seconds = _sampler_interval() if interval is None else max(1.0, float(interval))
        _SAMPLER_STOP.clear()
        _SAMPLER = threading.Thread(
            target=_sampler_loop, args=(seconds,), name="nexi-world-sampler", daemon=True
        )
        _SAMPLER.start()
    print(f"[WORLD] sampler started interval={seconds:.0f}s", flush=True)
    return True


def stop_world_sampler() -> None:
    _SAMPLER_STOP.set()


def _save_locked() -> None:
    # ponytail: best-effort. The world model must never break a voice turn.
    try:
        from engine.memory.local_memory import atomic_write_json

        atomic_write_json(_STORE, asdict(_WORLD))
    except Exception:
        pass


def _load() -> None:
    try:
        if not _STORE.exists():
            return
        with _STORE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            return
        if time.time() - float(data.get("updated_at") or 0.0) > _stale_after_seconds():
            for key in _VOLATILE:
                data.pop(key, None)
        with _LOCK:
            for key, value in data.items():
                if hasattr(_WORLD, key):
                    setattr(_WORLD, key, value)
    except Exception:
        pass


_load()
