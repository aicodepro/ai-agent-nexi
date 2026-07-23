import threading
import time
from datetime import datetime


class EmergencyStop:
    _engaged = False
    _reason = ""
    _lock = threading.Lock()

    @classmethod
    def engage(cls, reason=""):
        with cls._lock:
            cls._engaged = True
            cls._reason = reason

    @classmethod
    def clear(cls):
        with cls._lock:
            cls._engaged = False
            cls._reason = ""

    @classmethod
    def is_engaged(cls):
        with cls._lock:
            return cls._engaged

    @classmethod
    def reason(cls):
        with cls._lock:
            return cls._reason


class SandboxPolicy:
    RISK_LEVELS = {"SAFE", "MEDIUM", "HIGH", "CRITICAL"}

    CRITICAL_ACTIONS = {
        "delete_files", "run_terminal_commands", "install_software",
        "change_system_settings", "access_passwords", "access_cookies",
        "access_api_keys"
    }

    BLOCKED_ACTIONS = {
        "delete_files", "run_terminal_commands", "install_software",
        "change_system_settings", "access_passwords", "access_cookies",
        "access_api_keys"
    }

    @classmethod
    def is_allowed(cls, risk_level, action_name):
        if EmergencyStop.is_engaged():
            return False, "Emergency stop is engaged"
        if risk_level == "CRITICAL" or action_name in cls.BLOCKED_ACTIONS:
            return False, f"Action '{action_name}' is CRITICAL and blocked by sandbox policy"
        return True, ""

    @classmethod
    def requires_confirmation(cls, risk_level):
        return risk_level in ("HIGH", "CRITICAL")


class AuditLog:
    _entries = []
    _lock = threading.Lock()
    _enabled = True

    @classmethod
    def log(cls, action_name, entities=None, result=None):
        if not cls._enabled:
            return
        with cls._lock:
            cls._entries.append({
                "timestamp": datetime.now().isoformat(),
                "action": action_name,
                "entities": entities or {},
                "result": result.to_dict() if result else None
            })

    @classmethod
    def get_log(cls, limit=50):
        with cls._lock:
            return list(cls._entries[-limit:])

    @classmethod
    def clear_log(cls):
        with cls._lock:
            cls._entries.clear()

    @classmethod
    def set_enabled(cls, enabled):
        cls._enabled = enabled
