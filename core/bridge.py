"""Multiprocessing bridge — Process 2 (audio) → Process 1 (UI/commands)."""

import threading
import time
import os
import json
from dataclasses import dataclass, field, asdict
from typing import Optional

EVENT_COMMAND_TEXT = "command_text"
EVENT_STATUS = "status"
EVENT_WAKE_DETECTED = "wake_detected"
EVENT_ASR_STARTED = "asr_started"
EVENT_ASR_RESULT = "asr_result"
EVENT_ERROR = "error"

STATUS_TO_UI = {
    "listening_started": "listening", "hearing_speech": "listening",
    "recognising": "recognising", "transcribing": "recognising",
    "thinking": "thinking", "speaking": "saying",
    "sleeping": "sleep", "wake_detected": "wake_detected",
    "error": "error",
}


@dataclass
class BridgeEvent:
    type: str
    source: str = ""
    text: str = ""
    status: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


# --- Process 2 side: posting events ---

def _put(queue, event: BridgeEvent):
    if queue is None:
        return
    try:
        queue.put_nowait(event.to_dict())
    except Exception as e:
        print(f"[BRIDGE] put_failed type={event.type} reason={type(e).__name__}", flush=True)


def post_command(queue, text: str, source: str = "voice"):
    _put(queue, BridgeEvent(type=EVENT_COMMAND_TEXT, text=text, source=source))


def post_status(queue, status: str, source: str = "", text: str = ""):
    _put(queue, BridgeEvent(type=EVENT_STATUS, status=status, source=source, text=text))


def post_wake_detected(queue, source: str = "hotword"):
    _put(queue, BridgeEvent(type=EVENT_WAKE_DETECTED, source=source))


def post_asr_started(queue, source: str = "voice"):
    _put(queue, BridgeEvent(type=EVENT_ASR_STARTED, source=source))


def post_asr_result(queue, text: str, source: str = "voice"):
    _put(queue, BridgeEvent(type=EVENT_ASR_RESULT, text=text, source=source))


def post_error(queue, error: str, source: str = ""):
    _put(queue, BridgeEvent(type=EVENT_ERROR, error=error, source=source))


# --- Process 1 side: consuming events ---

_pump_running = False
_pump_thread: Optional[threading.Thread] = None


def handle_bridge_event(event: dict) -> None:
    etype = event.get("type", "")
    source = event.get("source", "")
    text = event.get("text", "")

    if etype == EVENT_COMMAND_TEXT and text.strip():
        try:
            from core.dispatcher import submit_user_command
            submit_user_command(text.strip(), source=source or "voice")
        except Exception as e:
            print(f"[BRIDGE] dispatch_failed reason={type(e).__name__}", flush=True)

    elif etype == EVENT_STATUS:
        status = event.get("status", "")
        ui_state = STATUS_TO_UI.get(status, "")
        if ui_state:
            try:
                from core.ui_state import emit_state
                emit_state(ui_state, source=source, text=text)
            except Exception:
                pass

    elif etype == EVENT_WAKE_DETECTED:
        try:
            from core.ui_state import emit_state
            emit_state("wake_detected", source=source)
        except Exception:
            pass

    elif etype == EVENT_ASR_RESULT and text.strip():
        try:
            from core.ui_state import safe_eel_call
            safe_eel_call("senderText", text.strip())
        except Exception:
            pass

    elif etype == EVENT_ERROR:
        print(f"[BRIDGE] error source={source} msg={event.get('error', '')}", flush=True)


def start_ui_bridge_pump(queue, stop_event=None) -> None:
    global _pump_running, _pump_thread
    if _pump_running:
        return

    _pump_running = True

    def _pump():
        global _pump_running
        while _pump_running:
            if stop_event and stop_event.is_set():
                break
            try:
                event = queue.get(timeout=0.1)
                handle_bridge_event(event)
            except Exception:
                pass

    _pump_thread = threading.Thread(target=_pump, daemon=True, name="bridge-pump")
    _pump_thread.start()
    print(f"[BRIDGE] pump started pid={os.getpid()}", flush=True)


def stop_ui_bridge_pump() -> None:
    global _pump_running
    _pump_running = False
