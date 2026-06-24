import os
from datetime import datetime
import uuid

from src.orin.memory.local_memory import LocalMemoryStore
from src.orin.memory.memory_policy import classify_key_value, sensitivity_for
from src.orin.memory.memory_redaction import redact_sensitive, sanitize_for_summary

_DEFAULT_PREFS_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..",
                 "data", "memory", "preferences.json")
)


def _make_memory_item(key, value, source, decision):
    return {
        "id": str(uuid.uuid4()),
        "type": "preference",
        "key": key,
        "value": value,
        "source": source or "user",
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "sensitivity": sensitivity_for(decision),
        "requires_confirmation": decision == "REQUIRE_CONFIRMATION",
    }


def _result(ok, message, data=None, error=None):
    return {
        "ok": ok,
        "message": message,
        "data": data or {},
        "error": error,
    }


class PreferenceStore:
    def __init__(self, filepath=None):
        self._store = LocalMemoryStore(filepath or _DEFAULT_PREFS_PATH, _skip_validation=True)

    def remember(self, key, value, source=""):
        decision, reason = classify_key_value(key, value)
        if decision == "REJECT":
            return _result(
                False,
                "Cannot store this memory. Sensitive content blocked.",
                error={"code": "REJECTED", "message": reason},
            )
        item = _make_memory_item(key, value, source, decision)
        self._store.set(key, item)
        msg = f"Remembered: {key}"
        if decision == "REQUIRE_CONFIRMATION":
            msg += " (requires confirmation before use)"
        return _result(True, msg, data={"item": item})

    def update(self, key, value):
        existing = self._store.get(key)
        if existing is None:
            return _result(False, f"No memory found for key: {key}",
                           error={"code": "NOT_FOUND", "message": "Key not found"})
        decision, reason = classify_key_value(key, value)
        if decision == "REJECT":
            return _result(False, "Cannot update. Sensitive content.",
                           error={"code": "REJECTED", "message": reason})
        existing["value"] = value
        existing["updated_at"] = datetime.now().isoformat()
        existing["sensitivity"] = sensitivity_for(decision)
        existing["requires_confirmation"] = decision == "REQUIRE_CONFIRMATION"
        self._store.set(key, existing)
        return _result(True, f"Updated: {key}", data={"item": existing})

    def forget(self, key):
        existed = self._store.delete(key)
        if not existed:
            return _result(False, f"No memory found for key: {key}",
                           error={"code": "NOT_FOUND", "message": "Key not found"})
        return _result(True, f"Forgotten: {key}")

    def get(self, key):
        item = self._store.get(key)
        if item is None:
            return _result(False, f"No memory found for key: {key}",
                           error={"code": "NOT_FOUND", "message": "Key not found"})
        return _result(True, f"Found: {key}", data={"item": item})

    def summarize(self):
        all_items = self._store.all()
        if not all_items:
            return _result(True, "No memories stored.",
                           data={"memories": [], "count": 0})
        safe_items = []
        for key, item in all_items.items():
            safe = sanitize_for_summary(item)
            safe_items.append(safe)
        return _result(True, f"{len(safe_items)} memory items",
                       data={"memories": safe_items, "count": len(safe_items)})

    def count(self):
        return self._store.size()
