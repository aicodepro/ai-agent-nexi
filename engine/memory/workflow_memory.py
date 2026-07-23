"""Agent Workflow Memory — NEXI learns reusable procedures from its OWN verified runs.

Ideas #65 (AWM) + #70 (outcome-gating) + #66 (Memp Update/deprecate) from
docs/NEXI_AUTONOMY_IDEAS.md. NEXI already stores episodic/semantic facts and one-line
reflection lessons; what it could not do is remember HOW a job was actually completed
and reuse that procedure next time.

The rule that makes this safe rather than a compounding-error machine:

    ONLY a run whose verifier PASSED may enter memory.

That is outcome-gating (#70). A self-learning loop that admits its own unverified
output is how agents reward-hack themselves — measured at 73.8% in the DGM paper (#82).
Success is therefore never self-reported: `verified` must come from the independent
check, not from the agent claiming it finished.

Two more properties from the research:
  * store DISTILLED steps, not raw transcripts (ExpeL #68) — heuristics transfer, logs don't;
  * DEPRECATE stale procedures (Memp #66) — a workflow whose success rate collapses is
    retired instead of being replayed forever. Memory that only grows, rots.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import warnings
from pathlib import Path

from engine.memory.local_memory import atomic_write_json, quarantine_corrupt_file

_LOCK = threading.RLock()
_MEM: dict[str, dict] | None = None
_LOAD_ERROR = ""

# A procedure must prove itself before it is trusted, and is retired if it stops working.
_MIN_RUNS_TO_TRUST = 2
_RETIRE_BELOW_SUCCESS_RATE = 0.5


def _path() -> Path:
    raw = (os.getenv("NEXI_WORKFLOW_MEMORY_PATH") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parents[2] / "data" / "workflow_memory.json"


def _load() -> dict[str, dict]:
    global _MEM, _LOAD_ERROR
    if _MEM is not None:
        return _MEM
    path = _path()
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("workflow memory root must be a JSON object")
            _MEM = {k: v for k, v in data.items() if isinstance(v, dict)}
        else:
            _MEM = {}
        _LOAD_ERROR = ""
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        _LOAD_ERROR = quarantine_corrupt_file(path, exc)
        _MEM = {}
    except OSError as exc:
        _LOAD_ERROR = f"Could not read workflow memory: {path} ({exc})"
        warnings.warn(_LOAD_ERROR, RuntimeWarning, stacklevel=2)
        _MEM = {}
    return _MEM


def _save() -> None:
    path = _path()
    try:
        atomic_write_json(path, _MEM or {})
    except Exception:
        pass


def last_load_error() -> str:
    return _LOAD_ERROR


_STOP = {"the", "a", "an", "to", "for", "of", "and", "in", "on", "with", "my", "me",
         "please", "nexi", "can", "you", "it", "this", "that", "is", "are", "add"}


def signature(task: str) -> str:
    """Stable key for 'this kind of task'.

    Content words only, sorted — so "add a login form" and "add login form please"
    resolve to the same procedure instead of storing a near-duplicate per phrasing.
    """
    words = re.findall(r"[a-z0-9]+", str(task or "").lower())
    keep = sorted({w for w in words if w not in _STOP and len(w) > 2})
    return "-".join(keep[:8]) or "general"


def record_run(task: str, steps: list[str], *, verified: bool,
               outcome: str = "", cli: str = "", duration_s: float = 0.0) -> dict:
    """Record a completed run. UNVERIFIED runs are counted but never become procedure.

    `verified` must come from the independent verifier — never from the agent's own
    claim that it succeeded.
    """
    sig = signature(task)
    with _LOCK:
        mem = _load()
        entry = mem.setdefault(sig, {
            "signature": sig, "example_task": str(task)[:200], "steps": [],
            "runs": 0, "successes": 0, "failures": 0, "retired": False,
            "cli": cli, "updated_at": 0.0, "lessons": [],
        })
        entry["runs"] += 1
        if verified:
            entry["successes"] += 1
            # Distilled steps replace the old ones only on a VERIFIED run, so a failed
            # attempt can never overwrite a procedure that works.
            clean = [str(s).strip()[:200] for s in (steps or []) if str(s).strip()][:20]
            if clean:
                entry["steps"] = clean
            if cli:
                entry["cli"] = cli
        else:
            entry["failures"] += 1
            if outcome:
                lesson = f"failed: {str(outcome)[:160]}"
                if lesson not in entry["lessons"]:
                    entry["lessons"] = ([lesson] + entry["lessons"])[:5]
        entry["updated_at"] = time.time()
        entry["duration_s"] = round(float(duration_s or 0.0), 1)
        # Memp Update phase: retire a procedure whose success rate collapsed.
        if entry["runs"] >= _MIN_RUNS_TO_TRUST:
            rate = entry["successes"] / max(1, entry["runs"])
            entry["retired"] = rate < _RETIRE_BELOW_SUCCESS_RATE
        _save()
        return dict(entry)


def recall(task: str) -> dict | None:
    """The learned procedure for this kind of task, if one is trustworthy.

    Returns None when unproven or retired — an untrusted procedure is worse than none,
    because it looks like knowledge.
    """
    with _LOCK:
        entry = _load().get(signature(task))
        if not entry or entry.get("retired") or not entry.get("steps"):
            return None
        if entry.get("successes", 0) < _MIN_RUNS_TO_TRUST:
            return None
        return dict(entry)


def guidance(task: str, max_chars: int = 700) -> str:
    """Prompt-ready text for the planner: how NEXI did this successfully before."""
    entry = recall(task)
    if not entry:
        return ""
    rate = entry["successes"] / max(1, entry["runs"])
    lines = [f"You have completed this kind of task {entry['successes']}x "
             f"(success rate {rate:.0%}). The procedure that worked:"]
    lines += [f"  {i}. {s}" for i, s in enumerate(entry["steps"], 1)]
    if entry.get("lessons"):
        lines.append("Known failure modes: " + "; ".join(entry["lessons"][:2]))
    return "\n".join(lines)[:max_chars]


def stats() -> dict:
    with _LOCK:
        mem = _load()
        trusted = [e for e in mem.values()
                   if not e.get("retired") and e.get("successes", 0) >= _MIN_RUNS_TO_TRUST]
        return {
            "procedures": len(mem),
            "trusted": len(trusted),
            "retired": sum(1 for e in mem.values() if e.get("retired")),
            "total_runs": sum(int(e.get("runs", 0)) for e in mem.values()),
        }


def reset() -> None:
    """Tests / manual clear."""
    global _MEM, _LOAD_ERROR
    with _LOCK:
        _MEM = {}
        _LOAD_ERROR = ""
        _save()


def _demo() -> None:
    os.environ["NEXI_WORKFLOW_MEMORY_PATH"] = str(
        Path(os.getenv("TEMP", "/tmp")) / "nexi_wfmem_demo.json")
    reset()
    task = "add a login form to the web app"
    # an unverified run teaches nothing
    record_run(task, ["guessed"], verified=False, outcome="tests failed")
    assert recall(task) is None, "unverified work must never become procedure"
    # two verified runs make it trustworthy
    for _ in range(2):
        record_run(task, ["read the router", "add the form component", "run the tests"],
                   verified=True, cli="opencode")
    got = recall(task)
    assert got and len(got["steps"]) == 3, got
    assert "procedure that worked" in guidance(task)
    # phrasing variants hit the same procedure
    assert recall("please add login form to web app") is not None
    # collapse the success rate -> retired
    for _ in range(6):
        record_run(task, [], verified=False, outcome="broke")
    assert recall(task) is None, "a procedure that stopped working must be retired"
    reset()
    print("workflow_memory._demo OK ->", stats())


if __name__ == "__main__":
    _demo()
