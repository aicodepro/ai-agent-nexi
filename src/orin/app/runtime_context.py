import threading

from src.orin.memory.conversation_buffer import ConversationBuffer
from src.orin.vision.screen_trust import ScreenTrust

_lock = threading.Lock()
_conversation_buffer = None


def get_conversation_buffer(max_turns=5):
    global _conversation_buffer
    if _conversation_buffer is None:
        with _lock:
            if _conversation_buffer is None:
                _conversation_buffer = ConversationBuffer(max_turns=max_turns)
    return _conversation_buffer


def get_screen_trust():
    return ScreenTrust


def get_speech_controller():
    import src.orin.voice.speech_controller as sc
    return sc


def reset_runtime():
    global _conversation_buffer
    with _lock:
        _conversation_buffer = None
        ScreenTrust.reset_to_ask()
