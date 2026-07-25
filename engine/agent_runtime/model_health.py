"""Self-healing model health tracker.

Darsh's rule: when a runtime (opencode / claude-code / Hermes) runs a model and it
fails, DROP that model from selection, mark it not-working, and move to the next best
for the task — automatically, no manual edit. This is the state that makes model_policy
self-healing instead of statically hoping every model works.

Health is per (runtime, model). A model trips to "down" after N consecutive failures
and is skipped by selection until a cooldown elapses (models come back — a free tier
rate-limits, then recovers). A success clears the failure count immediately.

In-memory by default; persisted to a JSON file so a model that died stays skipped
across restarts within the cooldown. No external deps.
"""
from __future__ import annotations

import json
import os
import threading
import time

_LOCK = threading.RLock()
# key "runtime\x00model" -> {"fails": int, "down_until": float, "last_reason": str}
_STATE: dict[str, dict] = {}
_LOADED = False


def _fail_threshold() -> int:
    try:
        return max(1, int(os.getenv("NEXI_MODEL_FAIL_THRESHOLD", "2")))
    except ValueError:
        return 2


def _cooldown_s() -> float:
    # a downed free model is retried after this long (rate limits recover)
    try:
        return max(0.0, float(os.getenv("NEXI_MODEL_DOWN_COOLDOWN_S", "1800")))
    except ValueError:
        return 1800.0


def _path() -> str | None:
    p = (os.getenv("NEXI_MODEL_HEALTH_PATH") or "").strip()
    return p or None


def _key(runtime: str, model: str) -> str:
    return f"{runtime}\x00{model}"


def _load() -> None:
    global _LOADED
    if _LOADED:
        return
    _LOADED = True
    path = _path()
    if not path or not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            _STATE.update({k: v for k, v in data.items() if isinstance(v, dict)})
    except Exception:
        pass  # a corrupt health file must never block model selection


def _save() -> None:
    path = _path()
    if not path:
        return
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(_STATE, fh)
        os.replace(tmp, path)
    except Exception:
        pass  # persistence is best-effort; never fail a turn over it


def _now() -> float:
    # Date.now equivalent; monotonic-ish wall clock. time.time is fine here.
    return time.time()


def mark_failed(runtime: str, model: str, reason: str = "") -> bool:
    """Record a failure. Returns True if this tripped the model to 'down'."""
    if not model:
        return False
    with _LOCK:
        _load()
        st = _STATE.setdefault(_key(runtime, model), {"fails": 0, "down_until": 0.0, "last_reason": ""})
        st["fails"] = int(st.get("fails", 0)) + 1
        st["last_reason"] = str(reason)[:200]
        tripped = st["fails"] >= _fail_threshold()
        if tripped:
            st["down_until"] = _now() + _cooldown_s()
            print(f"[MODEL_HEALTH] down runtime={runtime} model={model} "
                  f"fails={st['fails']} reason={reason}", flush=True)
        _save()
        return tripped


def mark_ok(runtime: str, model: str) -> None:
    """A successful run clears the failure count so a recovered model is trusted again."""
    if not model:
        return
    with _LOCK:
        _load()
        key = _key(runtime, model)
        if key in _STATE:
            _STATE[key] = {"fails": 0, "down_until": 0.0, "last_reason": ""}
            _save()


def is_down(runtime: str, model: str) -> bool:
    """True if this model is currently benched (within its cooldown)."""
    with _LOCK:
        _load()
        st = _STATE.get(_key(runtime, model))
        if not st:
            return False
        return _now() < float(st.get("down_until", 0.0))


def healthy(runtime: str, models: list[str]) -> list[str]:
    """Filter a model list to the ones NOT currently benched, order preserved."""
    return [m for m in models if not is_down(runtime, m)]


def status(runtime: str | None = None) -> list[dict]:
    """Report for the `which_model` tool: what's down and why."""
    with _LOCK:
        _load()
        out = []
        for key, st in _STATE.items():
            rt, model = key.split("\x00", 1)
            if runtime and rt != runtime:
                continue
            out.append({
                "runtime": rt, "model": model,
                "down": _now() < float(st.get("down_until", 0.0)),
                "fails": int(st.get("fails", 0)),
                "reason": st.get("last_reason", ""),
            })
        return out


def reset(runtime: str | None = None) -> None:
    """Clear health (all, or one runtime). For tests and manual recovery."""
    with _LOCK:
        if runtime is None:
            _STATE.clear()
        else:
            for key in [k for k in _STATE if k.split("\x00", 1)[0] == runtime]:
                _STATE.pop(key, None)
        _save()


def _demo() -> None:
    reset()
    os.environ["NEXI_MODEL_FAIL_THRESHOLD"] = "2"
    assert not is_down("opencode", "free/x")
    assert mark_failed("opencode", "free/x") is False   # 1st failure: still up
    assert mark_failed("opencode", "free/x") is True    # 2nd: tripped down
    assert is_down("opencode", "free/x")
    assert healthy("opencode", ["free/x", "free/y"]) == ["free/y"]  # x skipped
    mark_ok("opencode", "free/x")                         # recovered
    assert not is_down("opencode", "free/x")
    del os.environ["NEXI_MODEL_FAIL_THRESHOLD"]
    reset()
    print("model_health._demo OK")


if __name__ == "__main__":
    _demo()
