# workflow_state.py
# Local Workflow Lite (Batch 3): tiny in-memory, single-active conversational
# workflow state. No persistence, no GStack, no agent system.
import time
import threading
from copy import deepcopy

_workflow = None  # dict | None: {name, step, slots, created_at, updated_at}
_lock = threading.RLock()


def start_workflow(name: str, step: str, slots: dict | None = None) -> None:
    """Begin a new workflow, replacing any existing one."""
    global _workflow
    now = time.time()
    with _lock:
        _workflow = {
            "name": name,
            "step": step,
            "slots": deepcopy(slots) if slots else {},
            "created_at": now,
            "updated_at": now,
        }


def get_workflow() -> dict | None:
    """Return the active workflow dict, or None."""
    with _lock:
        return deepcopy(_workflow)


def update_workflow(step: str | None = None, slots: dict | None = None) -> None:
    """Update the active workflow's step and/or merge slots."""
    global _workflow
    with _lock:
        if _workflow is None:
            return
        if step is not None:
            _workflow["step"] = step
        if slots is not None:
            _workflow["slots"].update(deepcopy(slots))
        _workflow["updated_at"] = time.time()


def clear_workflow() -> None:
    """Clear the active workflow (on completion or cancel)."""
    global _workflow
    with _lock:
        _workflow = None


def has_active_workflow() -> bool:
    with _lock:
        return _workflow is not None


def is_expired(timeout_seconds: int = 300) -> bool:
    """True if a workflow exists and has been idle longer than timeout."""
    with _lock:
        if _workflow is None:
            return False
        return (time.time() - _workflow.get("updated_at", 0)) > timeout_seconds
