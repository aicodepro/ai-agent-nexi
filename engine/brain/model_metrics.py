import threading
import time
from datetime import datetime


class ModelMetrics:
    _routes = []
    _lock = threading.Lock()
    _max_entries = 500
    _enabled = True

    @classmethod
    def record(cls, task_type, preferred_model, selected_model,
               fallback_used, privacy_mode, reason="", duration_ms=0):
        if not cls._enabled:
            return
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task_type": task_type,
            "preferred_model": preferred_model,
            "selected_model": selected_model,
            "fallback_used": fallback_used,
            "privacy_mode": privacy_mode,
            "reason": reason,
            "duration_ms": duration_ms,
        }
        with cls._lock:
            cls._routes.append(entry)
            if len(cls._routes) > cls._max_entries:
                cls._routes.pop(0)

    @classmethod
    def record_decision(cls, decision, duration_ms=0):
        if not cls._enabled:
            return
        cls.record(
            task_type=decision.get("task_type", ""),
            preferred_model=decision.get("preferred_model", ""),
            selected_model=decision.get("selected_model", ""),
            fallback_used=decision.get("fallback_used", False),
            privacy_mode=decision.get("privacy_mode", "normal"),
            reason=decision.get("reason", ""),
            duration_ms=duration_ms,
        )

    @classmethod
    def get_history(cls, limit=50):
        with cls._lock:
            return list(cls._routes[-limit:])

    @classmethod
    def get_summary(cls):
        with cls._lock:
            total = len(cls._routes)
            if total == 0:
                return {"total_routes": 0, "fallback_rate": 0.0,
                        "by_task_type": {}, "by_model": {}}
            fallbacks = sum(1 for r in cls._routes if r.get("fallback_used"))
            by_task_type = {}
            by_model = {}
            for r in cls._routes:
                tt = r.get("task_type", "unknown")
                by_task_type[tt] = by_task_type.get(tt, 0) + 1
                sm = r.get("selected_model", "none")
                by_model[sm] = by_model.get(sm, 0) + 1
            return {
                "total_routes": total,
                "fallback_rate": round(fallbacks / total, 3) if total > 0 else 0.0,
                "by_task_type": by_task_type,
                "by_model": by_model,
            }

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._routes.clear()

    @classmethod
    def set_enabled(cls, enabled):
        cls._enabled = enabled

    @classmethod
    def set_max_entries(cls, max_entries):
        cls._max_entries = max_entries
