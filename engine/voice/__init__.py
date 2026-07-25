from engine.voice.response_style import ResponseStyle
from engine.voice.voice_personality import VoicePersonality
from engine.voice.voice_orchestrator import VoiceOrchestrator

from engine.voice.speech_interrupt import (
    is_stop_speaking_command,
    is_emergency_stop_command,
    classify_stop_command,
    classify_speech_control,
    normalize_stop_text,
)

from engine.voice.speech_controller import (
    speak,
    stop_speaking,
    clear_queue,
    is_speaking,
    get_state,
    shutdown,
    reset_stop_flag,
)


def compose_response(intent_result):
    return VoiceOrchestrator.compose(intent_result)


def compose_error(error_message, language="en"):
    return VoiceOrchestrator.compose_error(error_message, language)
