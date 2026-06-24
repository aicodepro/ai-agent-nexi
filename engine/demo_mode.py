from __future__ import annotations

import os


_TRUTHY = {"1", "true", "yes", "on"}


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in _TRUTHY


class DemoMode:
    """Opt-in safeguards for presentations and live demos."""

    SAFE_RESPONSES = {
        "router_fail": "Let me check that for you.",
        "asr_empty": "I didn't quite catch that. Could you repeat it?",
        "api_timeout": "I'm processing your request. One moment please.",
        "brain_fail": "I'm not sure about that right now.",
        "fallback": "I'm ready.",
    }

    NOISY_LOG_PREFIXES = (
        "[CONTEXT]",
        "[WORKING_MEMORY]",
        "[REFLECTION]",
        "[CONFIDENCE]",
    )

    @staticmethod
    def is_active() -> bool:
        return _env_bool("NEXI_DEMO_MODE", False)

    @classmethod
    def should_suppress_followup(cls) -> bool:
        return cls.is_active() and _env_bool("NEXI_DEMO_DISABLE_AUTO_FOLLOWUP", True)

    @classmethod
    def use_local_tts(cls) -> bool:
        return cls.is_active() and _env_bool("NEXI_DEMO_USE_LOCAL_TTS", True)

    @classmethod
    def reduce_logs(cls) -> bool:
        return cls.is_active() and _env_bool("NEXI_DEMO_REDUCE_LOGS", True)

    @classmethod
    def safe_response(cls, key: str = "fallback") -> str:
        return cls.SAFE_RESPONSES.get(key, cls.SAFE_RESPONSES["fallback"])

    @classmethod
    def sanitize_log(cls, line: str) -> str:
        value = str(line or "")
        if not cls.reduce_logs():
            return value
        stripped = value.strip()
        if any(stripped.startswith(prefix) for prefix in cls.NOISY_LOG_PREFIXES):
            return ""
        return value


def is_demo_mode() -> bool:
    return DemoMode.is_active()
