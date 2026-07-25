"""Idea #75 — sleep-time compute: think while the machine is idle.

The serve-time budget for a voice turn is ~1 second. Every autonomy idea worth having
(distilling workflow memory, re-indexing the router, auditing today's mistakes) costs far
more than that. The resolution from the sleep-time-compute paper: do the expensive
reasoning OFFLINE, so serve-time latency is untouched — measured ~5x less serve compute.

The machine is idle ~95% of the day. This module notices that and uses it.

Hard rules, each learned from a real failure in this codebase:
  * NEVER run inside a voice turn. Building e5 inline once took 83s in the UI process and
    froze the app ([[nexi-e5-blocked-voice-turn]]). Any activity here yields immediately
    when the user speaks.
  * Idle is measured from real user activity, not a timer that fires blindly.
  * Every job is budgeted and independently failable — one broken job must not stop the rest.
  * Jobs are read-mostly. Sleep-time is for THINKING, not for editing the repo unattended.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

_lock = threading.RLock()
_last_activity = time.time()
_running = False
_thread: threading.Thread | None = None
_stop = threading.Event()
_history: list[dict] = []

# name -> (callable, min_interval_seconds)
_JOBS: dict[str, tuple[Callable[[], dict], float]] = {}


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def idle_threshold_s() -> float:
    """How long with no user activity before NEXI considers itself idle."""
    return _env_float("NEXI_SLEEP_IDLE_SECONDS", 300.0)


def enabled() -> bool:
    return str(os.getenv("NEXI_SLEEP_TIME_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}


def note_activity(source: str = "") -> None:
    """Call on ANY user activity (wake word, command, UI click).

    This is the yield point: a job checks `is_idle()` between units of work and stops
    the moment the user is back, so sleep-time work can never delay a voice turn.
    """
    global _last_activity
    with _lock:
        _last_activity = time.time()


def seconds_idle() -> float:
    with _lock:
        return max(0.0, time.time() - _last_activity)


def is_idle() -> bool:
    return seconds_idle() >= idle_threshold_s()


def register(name: str, fn: Callable[[], dict], *, min_interval_s: float = 3600.0) -> None:
    """Register an offline job. Must be read-mostly, interruptible, and self-contained."""
    with _lock:
        _JOBS[name] = (fn, float(min_interval_s))


def _last_run(name: str) -> float:
    for row in reversed(_history):
        if row.get("job") == name:
            return float(row.get("at", 0.0))
    return 0.0


def run_due_jobs(*, force: bool = False) -> list[dict]:
    """Run every job whose interval has elapsed. Stops early if the user returns."""
    results: list[dict] = []
    for name, (fn, interval) in list(_JOBS.items()):
        if _stop.is_set():
            break
        if not force and not is_idle():
            results.append({"job": name, "skipped": "user_active"})
            break                      # user is back — yield immediately
        if not force and (time.time() - _last_run(name)) < interval:
            continue
        started = time.time()
        try:
            out = fn() or {}
            row = {"job": name, "ok": True, "at": started,
                   "seconds": round(time.time() - started, 2), **out}
        except Exception as exc:
            # one bad job must never stop the others
            row = {"job": name, "ok": False, "at": started, "error": type(exc).__name__}
        with _lock:
            _history.append(row)
            del _history[:-50]
        print(f"[SLEEP] job={name} ok={row.get('ok')} {row.get('seconds', 0)}s", flush=True)
        results.append(row)
    return results


def _loop(poll_s: float) -> None:
    while not _stop.wait(poll_s):
        if not enabled():
            continue
        try:
            if is_idle():
                run_due_jobs()
        except Exception as exc:
            print(f"[SLEEP] loop_error reason={type(exc).__name__}", flush=True)


def start(poll_s: float | None = None) -> bool:
    """Start the background sleep-time loop. Daemon thread — never blocks shutdown."""
    global _running, _thread
    with _lock:
        if _running or not enabled():
            return False
        _stop.clear()
        _thread = threading.Thread(
            target=_loop, args=(poll_s or _env_float("NEXI_SLEEP_POLL_SECONDS", 60.0),),
            name="nexi-sleep-time", daemon=True)
        _thread.start()
        _running = True
        print(f"[SLEEP] started idle_threshold={idle_threshold_s():.0f}s jobs={len(_JOBS)}", flush=True)
        return True


def stop() -> None:
    global _running
    _stop.set()
    with _lock:
        _running = False


def status() -> dict:
    with _lock:
        return {
            "enabled": enabled(),
            "running": _running,
            "idle_seconds": round(seconds_idle(), 1),
            "is_idle": is_idle(),
            "jobs": sorted(_JOBS),
            "recent": list(_history[-5:]),
        }


# ---- the default offline jobs ---------------------------------------------------

def job_consolidate_workflows() -> dict:
    """Report what NEXI has actually learned, and retire what stopped working (#66/#77)."""
    from engine.memory import workflow_memory
    return {"detail": workflow_memory.stats()}


def job_warm_model_discovery() -> dict:
    """Refresh the free-model catalogue offline so no voice turn ever pays for it."""
    from engine.agent_runtime import model_discovery
    found = model_discovery.discover_free_models("openrouter", force=True)
    return {"detail": {"free_models": len(found)}}


def job_self_audit() -> dict:
    """"Which routes did I get wrong today?" (#78) — surfaced, never auto-applied."""
    try:
        from engine.cognitive_context import get_last_decision
        last = get_last_decision() or {}
        return {"detail": {"last_route": last.get("chosen_route", ""),
                           "confidence": last.get("confidence", 0)}}
    except Exception:
        return {"detail": {}}


def register_defaults() -> None:
    register("consolidate_workflows", job_consolidate_workflows, min_interval_s=3600)
    register("warm_model_discovery", job_warm_model_discovery, min_interval_s=3600)
    register("self_audit", job_self_audit, min_interval_s=7200)


def _demo() -> None:
    global _history
    _history = []
    os.environ["NEXI_SLEEP_IDLE_SECONDS"] = "0.2"
    register("noop", lambda: {"detail": "ok"}, min_interval_s=0)
    note_activity()
    assert not is_idle(), "must not be idle immediately after activity"
    assert run_due_jobs()[0].get("skipped") == "user_active", "must yield while the user is active"
    time.sleep(0.25)
    assert is_idle()
    assert run_due_jobs()[0]["ok"] is True
    # a failing job must not stop the others
    register("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")), min_interval_s=0)
    register("after", lambda: {"detail": "still ran"}, min_interval_s=0)
    rows = {r["job"]: r for r in run_due_jobs(force=True)}
    assert rows["boom"]["ok"] is False and rows["after"]["ok"] is True
    _JOBS.clear()
    print("sleep_time._demo OK ->", {k: v for k, v in status().items() if k != "recent"})


if __name__ == "__main__":
    _demo()
