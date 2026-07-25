import threading


VALID_MODES = (
    "denied",
    "ask_each_time",
    "trusted_session_read_only",
    "trusted_local_read_only",
)

_DEFAULT_MODE = "ask_each_time"


class ScreenTrust:
    _mode = _DEFAULT_MODE
    _owner_trusted = True
    _lock = threading.Lock()

    @classmethod
    def get_mode(cls):
        with cls._lock:
            return cls._mode

    @classmethod
    def set_mode(cls, mode):
        if mode not in VALID_MODES:
            import logging
            logging.warning(f"Invalid screen trust mode: {mode}. Keeping current mode: {cls._mode}")
            return False
        with cls._lock:
            cls._mode = mode
        return True

    @classmethod
    def is_trusted(cls):
        from engine.control.safety import EmergencyStop
        if EmergencyStop.is_engaged():
            return False
        with cls._lock:
            return cls._mode in ("trusted_session_read_only", "trusted_local_read_only")

    @classmethod
    def is_owner_trusted(cls):
        from engine.control.safety import EmergencyStop
        if EmergencyStop.is_engaged():
            return False
        with cls._lock:
            return cls._owner_trusted

    @classmethod
    def set_owner_trusted(cls, enabled):
        with cls._lock:
            cls._owner_trusted = bool(enabled)

    @classmethod
    def reset_to_ask(cls):
        with cls._lock:
            cls._mode = _DEFAULT_MODE

    @classmethod
    def reset(cls):
        cls.reset_to_ask()

    @classmethod
    def reset_all(cls):
        with cls._lock:
            cls._mode = _DEFAULT_MODE
            cls._owner_trusted = True

    @classmethod
    def to_dict(cls):
        from engine.control.safety import EmergencyStop
        with cls._lock:
            is_t = cls._mode in ("trusted_session_read_only", "trusted_local_read_only")
            return {
                "mode": cls._mode,
                "is_trusted": is_t,
                "owner_trusted": cls._owner_trusted and not EmergencyStop.is_engaged(),
                "emergency_stop_active": EmergencyStop.is_engaged(),
            }
