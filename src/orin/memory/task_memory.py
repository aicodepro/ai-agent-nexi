import os
from datetime import datetime
import uuid

from src.orin.memory.local_memory import LocalJsonlStore
from src.orin.memory.memory_policy import classify_memory_text, sensitivity_for
from src.orin.memory.memory_redaction import redact_sensitive

_DEFAULT_TASKS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "data", "memory", "task_summaries.jsonl")
)

ALLOWED_TASK_KEYS = {"task_type", "summary", "status", "duration_ms",
                     "intent", "function", "risk_level"}


def _result(ok, message, data=None, error=None):
    return {
        "ok": ok,
        "message": message,
        "data": data or {},
        "error": error,
    }


class TaskMemory:
    def __init__(self, filepath=None):
        self._store = LocalJsonlStore(filepath or _DEFAULT_TASKS_PATH, _skip_validation=True)

    def append(self, task_summary):
        if not isinstance(task_summary, dict):
            return _result(False, "Task summary must be a dict",
                           error={"code": "INVALID", "message": "Expected dict"})
        combined_text = " ".join(str(v) for v in task_summary.values())
        decision, reason = classify_memory_text(combined_text)
        if decision == "REJECT":
            return _result(False, "Cannot store sensitive task summary",
                           error={"code": "REJECTED", "message": reason})
        safe_entry = {"id": str(uuid.uuid4())}
        for key in ALLOWED_TASK_KEYS:
            if key in task_summary:
                value = task_summary[key]
                safe_entry[key] = redact_sensitive(str(value)) if isinstance(value, str) else value
        safe_entry["sensitivity"] = sensitivity_for(decision)
        safe_entry["requires_confirmation"] = decision == "REQUIRE_CONFIRMATION"
        safe_entry["_stored_at"] = datetime.now().isoformat()
        self._store.append(safe_entry)
        msg = "Task summary stored"
        if decision == "REQUIRE_CONFIRMATION":
            msg += " (marked for review)"
        return _result(True, msg, data={"entry": safe_entry})

    def recent(self, limit=10):
        entries = self._store.read_recent(limit)
        safe_entries = []
        for entry in entries:
            safe = {}
            for k, v in entry.items():
                if isinstance(v, str):
                    safe[k] = redact_sensitive(v)
                else:
                    safe[k] = v
            safe_entries.append(safe)
        return _result(True, f"{len(safe_entries)} recent tasks",
                       data={"tasks": safe_entries, "count": len(safe_entries)})

    def count(self):
        return self._store.size()
