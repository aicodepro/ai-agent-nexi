from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass
from typing import Any


_STARTED_AT = time.time()
_CACHE_TTL_SECONDS = 5.0
_cache: tuple[float, dict[str, "ComponentStatus"]] | None = None


@dataclass
class ComponentStatus:
    name: str
    status: str
    detail: str = ""
    last_check: float = 0.0
    latency_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_bool(key: str, default: bool) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _status(name: str, status: str, detail: str, started: float) -> ComponentStatus:
    return ComponentStatus(
        name=name,
        status=status,
        detail=detail,
        last_check=time.time(),
        latency_ms=max(0, int((time.time() - started) * 1000)),
    )


class Diagnostics:
    """Read-only component health checks for Nexi runtime."""

    @classmethod
    def check_all(cls, *, force: bool = False) -> dict[str, ComponentStatus]:
        global _cache
        now = time.time()
        if not force and _cache is not None and now - _cache[0] < _CACHE_TTL_SECONDS:
            return dict(_cache[1])
        checks = {
            "microphone": cls.check_microphone(),
            "hotword": cls.check_hotword(),
            "clap": cls.check_clap(),
            "asr": cls.check_asr(),
            "brain": cls.check_brain(),
            "tts": cls.check_tts(),
            "memory": cls.check_memory(),
            "tools": cls.check_tools(),
        }
        _cache = (now, checks)
        return dict(checks)

    @staticmethod
    def check_microphone() -> ComponentStatus:
        started = time.time()
        try:
            import sounddevice as sd
            devices = sd.query_devices()
            count = 0
            for device in devices:
                if isinstance(device, dict) and int(device.get("max_input_channels", 0)) > 0:
                    count += 1
            if count:
                return _status("Microphone", "active", f"{count} input device(s)", started)
            return _status("Microphone", "disabled", "no input devices reported", started)
        except ImportError:
            return _status("Microphone", "disabled", "sounddevice not installed", started)
        except Exception as exc:
            return _status("Microphone", "error", type(exc).__name__, started)

    @staticmethod
    def check_hotword() -> ComponentStatus:
        started = time.time()
        enabled = _env_bool("NEXI_HOTWORD_ENABLED", True) and _env_bool("OPENWAKEWORD_ENABLED", True)
        backend = os.getenv("VOICE_WAKE_BACKEND", "openwakeword")
        if not enabled:
            return _status("Hotword", "disabled", f"backend={backend}", started)
        threshold = os.getenv("OPENWAKEWORD_SCORE_THRESHOLD", "0.35")
        return _status("Hotword", "active", f"backend={backend} threshold={threshold}", started)

    @staticmethod
    def check_clap() -> ComponentStatus:
        started = time.time()
        enabled = _env_bool("NEXI_CLAP_ENABLED", True) or _env_bool("CLAP_DETECTION_ENABLED", False)
        primary = os.getenv("NEXI_CLAP_PRIMARY", "dsp_clap")
        status = "active" if enabled else "disabled"
        return _status("Clap", status, f"primary={primary}", started)

    @staticmethod
    def check_asr() -> ComponentStatus:
        started = time.time()
        provider = os.getenv("ASR_PROVIDER", "groq")
        if provider.lower() == "groq" and not os.getenv("GROQ_API_KEY"):
            return _status("ASR", "disabled", "Groq key not configured", started)
        model = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
        return _status("ASR", "ready", f"provider={provider} model={model}", started)

    @staticmethod
    def check_brain() -> ComponentStatus:
        started = time.time()
        groq = bool(os.getenv("GROQ_API_KEY"))
        gemini = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
        if groq or gemini:
            providers = ",".join(name for name, ok in (("groq", groq), ("gemini", gemini)) if ok)
            return _status("Brain", "ready", f"providers={providers}", started)
        return _status("Brain", "disabled", "no cloud brain key configured", started)

    @staticmethod
    def check_tts() -> ComponentStatus:
        started = time.time()
        if not _env_bool("TTS_ENABLED", True):
            return _status("TTS", "disabled", "TTS_ENABLED=false", started)
        local_ok = False
        try:
            import pyttsx3  # noqa: F401
            local_ok = True
        except Exception:
            local_ok = False
        groq_ready = bool(os.getenv("GROQ_API_KEY")) and _env_bool("GROQ_TTS_ENABLED", True)
        if groq_ready and local_ok:
            return _status("TTS", "ready", "Groq + pyttsx3 fallback", started)
        if groq_ready:
            return _status("TTS", "ready", "Groq configured", started)
        if local_ok:
            return _status("TTS", "ready", "pyttsx3 fallback", started)
        return _status("TTS", "error", "no TTS provider available", started)

    @staticmethod
    def check_memory() -> ComponentStatus:
        started = time.time()
        try:
            from engine import memory_store
            path = getattr(memory_store, "MEMORY_PATH", "")
            return _status("Memory", "ready", f"path={path}", started)
        except Exception as exc:
            return _status("Memory", "error", type(exc).__name__, started)

    @staticmethod
    def check_tools() -> ComponentStatus:
        started = time.time()
        try:
            from engine.tool_registry import registered_tool_names
            count = len(registered_tool_names())
            return _status("Tools", "ready", f"{count} registered", started)
        except Exception as exc:
            return _status("Tools", "error", type(exc).__name__, started)

    @staticmethod
    def get_uptime() -> str:
        seconds = max(0, int(time.time() - _STARTED_AT))
        hours, rem = divmod(seconds, 3600)
        minutes, secs = divmod(rem, 60)
        if hours:
            return f"{hours}h {minutes}m {secs}s"
        if minutes:
            return f"{minutes}m {secs}s"
        return f"{secs}s"


def check_all(*, force: bool = False) -> dict[str, ComponentStatus]:
    return Diagnostics.check_all(force=force)


def check_all_dict(*, force: bool = False) -> dict[str, dict[str, Any]]:
    return {key: value.to_dict() for key, value in Diagnostics.check_all(force=force).items()}
