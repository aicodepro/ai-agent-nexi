from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Tone(Enum):
    CALM = "calm"
    URGENT = "urgent"
    FOCUSED = "focused"
    FRIENDLY = "friendly"
    TECHNICAL = "technical"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class ToneConfig:
    mode: Tone = Tone.CALM
    voice_style: str = "default"
    ui_color_class: str = "tone-calm"
    response_prefix: str = ""
    tts_rate_delta: int = 0


@dataclass(frozen=True)
class ToneContext:
    route: str = ""
    confidence: float = 1.0
    risk_level: str = "none"
    is_error: bool = False
    is_tool: bool = False
    is_greeting: bool = False
    is_low_confidence: bool = False
    handler_reason: str = ""


class ToneManager:
    TONE_MAP = {
        Tone.CALM: ToneConfig(Tone.CALM, "default", "tone-calm", "", 0),
        Tone.URGENT: ToneConfig(Tone.URGENT, "firm", "tone-urgent", "", 20),
        Tone.FOCUSED: ToneConfig(Tone.FOCUSED, "neutral", "tone-focused", "", -10),
        Tone.FRIENDLY: ToneConfig(Tone.FRIENDLY, "warm", "tone-friendly", "", 10),
        Tone.TECHNICAL: ToneConfig(Tone.TECHNICAL, "flat", "tone-technical", "", -20),
        Tone.LOW_CONFIDENCE: ToneConfig(Tone.LOW_CONFIDENCE, "softer", "tone-uncertain", "I think ", -15),
    }

    @classmethod
    def select_tone(cls, context: ToneContext) -> ToneConfig:
        reason = (context.handler_reason or "").strip().lower()
        route = (context.route or reason or "").strip().lower()
        risk = (context.risk_level or "none").strip().lower()
        if context.is_error or route in {"error", "reject"} or risk in {"high", "critical", "blocked"}:
            tone = Tone.URGENT
        elif context.is_low_confidence or context.confidence < 0.65 or route == "clarify":
            tone = Tone.LOW_CONFIDENCE
        elif context.is_greeting or route in {"greeting", "identity", "system"}:
            tone = Tone.FRIENDLY
        elif route in {"tool", "workflow", "react", "missing_slot"} or context.is_tool:
            tone = Tone.FOCUSED
        elif route in {"output", "technical"}:
            tone = Tone.TECHNICAL
        else:
            tone = Tone.CALM
        config = cls.TONE_MAP[tone]
        try:
            from engine.presence_state import get_presence
            get_presence().set_tone(config.mode.value)
        except Exception:
            pass
        return config

    @classmethod
    def wrap_response(cls, text: str, tone: ToneConfig) -> str:
        value = str(text or "").strip()
        prefix = tone.response_prefix or ""
        if prefix and value and not value.lower().startswith(prefix.lower()):
            return f"{prefix}{value[:1].lower()}{value[1:]}"
        return value

    @classmethod
    def apply_tts_style(cls, text: str, tone: ToneConfig) -> str:
        return str(text or "")


def tone_for_reason(handler_reason: str = "", *, confidence: float = 1.0, route: str = "", risk_level: str = "none") -> ToneConfig:
    return ToneManager.select_tone(ToneContext(route=route, confidence=confidence, risk_level=risk_level, handler_reason=handler_reason))
