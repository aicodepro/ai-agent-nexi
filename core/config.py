"""Centralized configuration — single source of truth for all settings."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

BASE_DIR = Path(__file__).resolve().parent.parent
__version__ = "1.0.0"

ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Nexi")


def env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class NexiConfig:
    # Identity
    name: str = ASSISTANT_NAME

    @property
    def version(self) -> str:
        return __version__

    # Wake
    hotword_enabled: bool = field(default_factory=lambda: env_bool("NEXI_HOTWORD_ENABLED", True))
    clap_enabled: bool = field(default_factory=lambda: env_bool("NEXI_CLAP_ENABLED", True))
    hotkey_enabled: bool = field(default_factory=lambda: env_bool("NEXI_HOTKEY_WAKE_ENABLED", False))
    wake_cooldown_ms: int = field(default_factory=lambda: env_int("NEXI_WAKE_COOLDOWN_MS", 1800))
    wake_backend: str = field(default_factory=lambda: os.getenv("VOICE_WAKE_BACKEND", "openwakeword").strip().lower())

    # Audio
    sample_rate: int = field(default_factory=lambda: env_int("AUDIO_SAMPLE_RATE", 16000))
    frame_ms: int = field(default_factory=lambda: env_int("AUDIO_FRAME_MS", 80))
    channels: int = 1

    # ASR
    asr_provider: str = field(default_factory=lambda: os.getenv("ASR_PROVIDER", "groq").strip().lower())
    groq_whisper_model: str = field(default_factory=lambda: os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo"))
    groq_asr_language: str = field(default_factory=lambda: os.getenv("GROQ_ASR_LANGUAGE", "en"))
    groq_asr_timeout: int = field(default_factory=lambda: env_int("GROQ_TIMEOUT_SECONDS", 10))

    # Brain
    brain_provider: str = field(default_factory=lambda: os.getenv("BRAIN_PROVIDER", "gemini").strip().lower())
    gemini_model_primary: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.5-flash"))
    gemini_model_fallback: str = field(default_factory=lambda: os.getenv("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash-lite"))
    gemini_temperature: float = field(default_factory=lambda: env_float("GEMINI_TEMPERATURE", 0.35))
    gemini_max_tokens: int = field(default_factory=lambda: env_int("GEMINI_MAX_OUTPUT_TOKENS", 512))

    # TTS
    tts_provider_order: str = field(default_factory=lambda: os.getenv("TTS_PROVIDER_ORDER", "groq,pyttsx3"))
    groq_tts_voice: str = field(default_factory=lambda: os.getenv("GROQ_TTS_VOICE", "Fritz-PlayAI"))
    groq_tts_model: str = field(default_factory=lambda: os.getenv("GROQ_TTS_MODEL", "playai-tts"))
    tts_summarize: bool = field(default_factory=lambda: env_bool("TTS_SUMMARIZE_LONG_OUTPUT", True))

    # UI
    ui_mode: str = field(default_factory=lambda: os.getenv("NEXI_UI_MODE", "mark").strip().lower())
    fullscreen: bool = field(default_factory=lambda: env_bool("NEXI_FULLSCREEN", True))
    window_mode: str = field(default_factory=lambda: os.getenv("NEXI_WINDOW_MODE", "fullscreen").strip().lower())

    # Safety
    safety_gate_enabled: bool = field(default_factory=lambda: env_bool("SAFETY_GATE_ENABLED", True))

    # Follow-up
    auto_listen_after_question: bool = field(default_factory=lambda: env_bool("AUTO_LISTEN_AFTER_QUESTION", True))
    barge_in_enabled: bool = field(default_factory=lambda: env_bool("BARGE_IN_ENABLED", True))

    # Intent
    intent_brain_threshold: float = field(default_factory=lambda: env_float("INTENT_BRAIN_THRESHOLD", 0.45))

    # API Keys
    @property
    def gemini_api_key(self) -> str:
        return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")

    @property
    def groq_api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    @property
    def gemini_model_chain(self) -> list:
        env = os.getenv("GEMINI_MODEL_CHAIN", "").strip()
        if env:
            return [m.strip() for m in env.split(",") if m.strip()]
        return [self.gemini_model_primary, self.gemini_model_fallback]

    @property
    def tts_providers(self) -> list:
        return [p.strip() for p in self.tts_provider_order.split(",") if p.strip()]

    # Jarvis integration
    jarvis: "NexiJarvisConfig" = field(default_factory=lambda: NexiJarvisConfig())


@dataclass
class NexiJarvisConfig:
    jarvis_enabled: bool = field(default_factory=lambda: env_bool("JARVIS_ENABLED", True))
    jarvis_tool_calling: bool = field(default_factory=lambda: env_bool("JARVIS_TOOL_CALLING", True))
    jarvis_max_tool_steps: int = field(default_factory=lambda: env_int("JARVIS_MAX_TOOL_STEPS", 10))
    jarvis_memory_type: str = field(default_factory=lambda: os.getenv("JARVIS_MEMORY_TYPE", "unified").strip())
    jarvis_training_enabled: bool = field(default_factory=lambda: env_bool("JARVIS_TRAINING_ENABLED", False))
    jarvis_brain_provider: str = field(default_factory=lambda: os.getenv("JARVIS_BRAIN_PROVIDER", "gemini").strip())
    jarvis_brain_api_key: str = field(default_factory=lambda: (os.getenv("JARVIS_BRAIN_API_KEY") or "").strip())


cfg = NexiConfig()
