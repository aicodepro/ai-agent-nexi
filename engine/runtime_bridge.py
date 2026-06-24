# runtime_bridge.py
#
# Multiprocessing bridge between the wake/audio process (Process 2) and
# the UI/Eel process (Process 1).
#
# Process 2 posts pickle-safe dict events to a multiprocessing.Queue.
# Process 1 runs a pump thread that consumes events and calls
# allCommands(text) where Eel JS functions are available.
#
# Eel is only touched from the UI pump process when updating UI state.
# No speak(). No network calls. Queue events stay pickle-safe.

from __future__ import annotations

import threading
import time
import os
import json
from dataclasses import asdict, dataclass
from typing import Optional

# Event types
EVENT_COMMAND_TEXT = "command_text"
EVENT_STATUS = "status"
EVENT_WAKE_DETECTED = "wake_detected"
EVENT_LISTENING_STARTED = "listening_started"
EVENT_WAITING_FOR_SPEECH = "waiting_for_speech"
EVENT_SPEECH_STARTED = "speech_started"
EVENT_SPEECH_ENDED = "speech_ended"
EVENT_ASR_STARTED = "asr_started"
EVENT_ASR_RESULT = "asr_result"
EVENT_THINKING_STARTED = "thinking_started"
EVENT_REACT_THINKING = "react_thinking"
EVENT_REACT_TOOL_START = "react_tool_start"
EVENT_REACT_TOOL_END = "react_tool_end"
EVENT_SPEAKING_STARTED = "speaking_started"
EVENT_INTERRUPTED = "interrupted"
EVENT_BARGE_IN_LISTENING_STARTED = "barge_in_listening_started"
EVENT_IDLE = "idle"
EVENT_SLEEPING = "sleeping"
EVENT_ERROR = "error"
EVENT_DASHBOARD_UPDATE = "dashboard_update"
EVENT_DIAGNOSTICS_REQUEST = "diagnostics_request"
EVENT_DIAGNOSTICS_RESULT = "diagnostics_result"
EVENT_TRANSCRIPT = "transcript"

# Status-to-UI-state mapping with source-aware differentiation
STATUS_TO_UI_STATE = {
    EVENT_WAKE_DETECTED: "online",
    EVENT_LISTENING_STARTED: "listening",
    "listening": "listening",
    EVENT_WAITING_FOR_SPEECH: "waiting_for_speech",
    "waiting_for_speech": "waiting_for_speech",
    EVENT_SPEECH_STARTED: "listening",
    EVENT_SPEECH_ENDED: "recognising",
    EVENT_ASR_STARTED: "recognising",
    EVENT_ASR_RESULT: "thinking",
    EVENT_THINKING_STARTED: "thinking",
    EVENT_REACT_THINKING: "thinking",
    EVENT_REACT_TOOL_START: "thinking",
    EVENT_REACT_TOOL_END: "thinking",
    "checking_files": "thinking",
    "running_tool": "thinking",
    "searching": "thinking",
    EVENT_SPEAKING_STARTED: "saying",
    EVENT_INTERRUPTED: "listening",
    EVENT_BARGE_IN_LISTENING_STARTED: "listening",
    "saying": "saying",
    EVENT_IDLE: "sleep",
    EVENT_SLEEPING: "sleep",
    "sleep": "sleep",
    EVENT_ERROR: "error",
    "recognising": "recognising",
    "thinking": "thinking",
}


@dataclass
class BridgeEvent:
    type: str
    source: str = ""
    text: str = ""
    status: str = ""
    error: str = ""
    created_at: float = 0.0
    session_id: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        if not data["created_at"]:
            data["created_at"] = time.time()
        from engine.wake_session_manager import get_session_manager
        sid = data.get("session_id") or get_session_manager().get_session_id()
        if sid:
            data["session_id"] = sid
        return data
   

def _safe_log(msg: str) -> None:
    try:
        from engine.demo_mode import DemoMode
        msg = DemoMode.sanitize_log(msg)
        if not msg:
            return
    except Exception:
        pass
    try:
        from engine.debug_trace import line
        line(msg)
    except Exception:
        print(msg, flush=True)


def _put_event(queue, event: BridgeEvent, *, log_success: str = "") -> bool:
    if queue is None:
        return False
    try:
        queue.put_nowait(event.to_dict())
        if log_success:
            _safe_log(log_success)
        return True
    except Exception as e:
        _safe_log(f"[BRIDGE] error reason={type(e).__name__}")
        return False


# ---------------------------------------------------------------------------
# Posting (called from Process 2 — wake/audio)
# ---------------------------------------------------------------------------

def post_command(queue, text: str, source: str = "hotword", session_id: str = "") -> bool:
    """Post a transcribed command to the bridge queue. Returns True on success."""
    if queue is None or not text or not text.strip():
        return False
    cleaned = text.strip()
    event = BridgeEvent(type=EVENT_COMMAND_TEXT, text=cleaned, source=source, session_id=session_id)
    return _put_event(
        queue,
        event,
        log_success=f"[BRIDGE] posted command_text source={source} chars={len(cleaned)} pid={os.getpid()}",
    )


def post_status(queue, status: str, source: str = "", text: str = "", session_id: str = "") -> bool:
    if queue is None or not status:
        return False
    return _put_event(
        queue,
        BridgeEvent(type=EVENT_STATUS, status=status, source=source, text=(text or "")[:80], session_id=session_id),
        log_success=f"[BRIDGE] posted status={status} source={source} pid={os.getpid()}",
    )


def post_wake_detected(queue, source: str = "hotword", session_id: str = "") -> bool:
    return _put_event(queue, BridgeEvent(type=EVENT_WAKE_DETECTED, source=source, session_id=session_id))


def post_asr_started(queue, source: str = "hotword", session_id: str = "") -> bool:
    return _put_event(queue, BridgeEvent(type=EVENT_ASR_STARTED, source=source, session_id=session_id))


def post_asr_result(queue, text: str, source: str = "hotword", session_id: str = "") -> bool:
    if queue is None:
        return False
    cleaned = (text or "").strip()
    return _put_event(queue, BridgeEvent(type=EVENT_ASR_RESULT, text=cleaned, source=source, session_id=session_id))


def post_error(queue, error: str, source: str = "", session_id: str = "") -> bool:
    if queue is None or not error:
        return False
    return _put_event(queue, BridgeEvent(type=EVENT_ERROR, error=error, source=source, session_id=session_id))


# ---------------------------------------------------------------------------
# Consuming (called in Process 1 — UI/Eel)
# ---------------------------------------------------------------------------

def handle_bridge_event(event: dict) -> None:
    """Dispatch a single bridge event. Runs in Process 1 where Eel lives."""
    from engine.wake_session_manager import ignore_if_stale
    event_session_id = event.get("session_id", "")
    if event_session_id and ignore_if_stale(event_session_id):
        return
    etype = event.get("type", "")
    if etype == EVENT_COMMAND_TEXT:
        text = (event.get("text") or "").strip()
        source = event.get("source", "bridge")
        if not text:
            return
        _safe_log(f"[BRIDGE] received command_text source={source} chars={len(text)} pid={os.getpid()}")
        try:
            _set_ui_state("thinking", source=source, text=text[:80], status=EVENT_THINKING_STARTED, session_id=event_session_id)
            _safe_log("[BRIDGE] dispatch command_bus started")
            from engine.command_bus import submit_user_command
            mode = "voice" if source in {"hotword", "clap", "double_clap", "hotkey", "ui_button", "mic_button", "voice"} else "typed"
            result = submit_user_command(text, source=source, mode=mode)
            _safe_log("[BRIDGE] dispatch command_bus finished")
            if not result:
                _safe_log("[BRIDGE] command_bus returned False — no handler matched")
                _safe_log("NEXI: I heard you, but I could not complete that command.")
                try:
                    from engine.command import speak
                    speak("I heard you, but I could not complete that command.")
                except Exception as speak_err:
                    _safe_log(f"[BRIDGE] fallback_speak_failed reason={type(speak_err).__name__}")
            try:
                auto_followup = (os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "false") or "").strip().lower() in {"1", "true", "yes", "on"}
                from engine.followup_manager import has_pending_followup
                from engine.clarification_manager import has_pending_clarification
                if auto_followup and (has_pending_followup() or has_pending_clarification()):
                    _set_ui_state("listening", source="clarification", status="auto_followup", session_id=event_session_id)
                else:
                    _set_ui_state("sleep", source="ready", status=EVENT_IDLE, session_id=event_session_id)
                    _finish_session()
            except Exception:
                _set_ui_state("sleep", source="ready", status=EVENT_IDLE, session_id=event_session_id)
                _finish_session()
        except Exception as e:
            _safe_log(f"[BRIDGE] error reason={type(e).__name__}")
            _set_ui_state("error", source=source, text=type(e).__name__, status=EVENT_ERROR, session_id=event_session_id)
            _set_ui_state("sleep", source="ready", status=EVENT_IDLE, session_id=event_session_id)
            _finish_session()
    elif etype == EVENT_STATUS:
        _handle_status_event(event)
    elif etype == EVENT_WAKE_DETECTED:
        source = event.get("source", "")
        _safe_log(f"[BRIDGE] wake_detected source={source}")
        _safe_log("[FOLLOWUP] cleared reason=new_wake")
        try:
            from engine.followup_manager import clear_followup
            clear_followup("new_wake")
        except Exception:
            pass
        _set_ui_state("online", source=source, status=EVENT_WAKE_DETECTED, session_id=event_session_id)
    elif etype == EVENT_ASR_STARTED:
        _safe_log(f"[BRIDGE] asr_started source={event.get('source', '')}")
        _set_ui_state("transcribing", source=event.get("source", ""), status=EVENT_ASR_STARTED, session_id=event_session_id)
    elif etype == EVENT_ASR_RESULT:
        text = (event.get("text") or "").strip()
        _safe_log(f"[BRIDGE] asr_result source={event.get('source', '')} chars={len(text)}")
        if text:
            _set_ui_state("transcribing", source=event.get("source", ""), text=text[:80], status=EVENT_ASR_RESULT, session_id=event_session_id)
            try:
                import eel
                eel.senderText(text)
            except Exception:
                pass
        else:
            _safe_log("[BRIDGE] asr_result empty — no speech captured")
            _append_log("warn", "SYS: No speech detected. Please try again.")
            _set_ui_state("sleep", source=event.get("source", ""), status=EVENT_IDLE, session_id=event_session_id)
    elif etype == EVENT_ERROR:
        _safe_log(f"[BRIDGE] error reason={event.get('error', '')}")
        _set_ui_state("error", source=event.get("source", "system"), text=event.get("error", ""), status=EVENT_ERROR, session_id=event_session_id)
    elif etype == EVENT_DASHBOARD_UPDATE:
        _send_dashboard_update(event)
    elif etype == EVENT_DIAGNOSTICS_REQUEST:
        _send_diagnostics_result()
    elif etype == EVENT_DIAGNOSTICS_RESULT:
        _send_diagnostics_result(event.get("payload") or event.get("data") or event)
    elif etype == EVENT_TRANSCRIPT:
        _send_transcript(event.get("payload") or event)


def _handle_status_event(event: dict) -> None:
    status = (event.get("status") or "").strip()
    source = event.get("source", "system")
    text = (event.get("text") or "").strip()
    session_id = event.get("session_id", "")
    _safe_log(f"[BRIDGE] received status={status} source={source}")
    if status == EVENT_ASR_RESULT:
        if text:
            _safe_log(f"You: {text[:80]}")
            _set_ui_state("recognising", source=source, text=text, status=status, session_id=session_id)
            _sender_text(text)
            _safe_log("SYS: Thinking...")
            _set_ui_state("thinking", source=source, text=text, status=EVENT_THINKING_STARTED, session_id=session_id)
        else:
            _safe_log("[BRIDGE] asr_result empty — saving to artifacts/last_empty_asr.wav if applicable")
            _append_log("warn", "SYS: No speech detected. Please try again.")
            _set_ui_state("sleep", source=source, status=EVENT_IDLE, session_id=session_id)
        return
    state = STATUS_TO_UI_STATE.get(status, "idle")
    if state == "online":
        if source == "hotword":
            _safe_log("WAKE: Hotword detected")
        elif source in {"clap", "double_clap", "double-clap", "double clap"}:
            _safe_log("WAKE: Double clap detected")
        else:
            _safe_log("WAKE: Wake detected")
    elif state == "saying":
        _safe_log("SYS: Saying...")
    elif state == "sleep":
        _safe_log("SYS: Sleep mode")
    elif state == "listening":
        _safe_log("SYS: Listening...")
    elif state == "waiting_for_speech":
        _safe_log("SYS: Waiting for speech...")
    elif state == "recognising":
        _safe_log("SYS: Recognising speech...")
    elif state == "thinking":
        _safe_log("SYS: Thinking...")
    _set_ui_state(state, source=source, text=text, status=status, session_id=session_id)


def _sender_text(text: str) -> bool:
    try:
        import eel
        eel.senderText(text)
        return True
    except Exception:
        return False


def _finish_session() -> None:
    try:
        from engine.wake_session_manager import finish_session
        finish_session("complete")
    except Exception:
        pass


def _append_log(level: str, message: str) -> bool:
    try:
        import eel
        eel.appendLog(level, message)
        return True
    except Exception:
        return False


def _send_transcript(payload: dict) -> bool:
    try:
        import eel
        eel.updateTranscript(json.dumps(payload or {}))
        return True
    except Exception:
        return False


def _send_dashboard_update(payload: dict | None = None) -> bool:
    try:
        import eel
        if payload and payload.get("panels"):
            eel.updateDashboard(payload)
        else:
            from engine.world_monitor_dashboard import get_dashboard_state
            eel.updateDashboard(get_dashboard_state())
        return True
    except Exception:
        return False


def _send_diagnostics_result(payload: dict | None = None) -> bool:
    try:
        import eel
        if payload and payload.get("checks"):
            eel.diagnosticsResult(payload)
        else:
            from engine.diagnostics import check_all_dict
            eel.diagnosticsResult({"checks": check_all_dict(force=True)})
        return True
    except Exception:
        return False


_ui_failure_logged: dict = {}


def _set_ui_state(state: str, *, source: str = "system", text: str = "", status: str = "", session_id: str = "") -> bool:
    try:
        from engine.ui_state_manager import emit_state
        emitted = emit_state(state, source=source or "system", text=text or "", status=status or state, session_id=session_id or "")
        return emitted is not None
    except AttributeError:
        if "updateNexiState" not in _ui_failure_logged:
            _ui_failure_logged["updateNexiState"] = True
            _safe_log("[UI] updateNexiState missing — Mark UI must call eel.expose(updateNexiState)")
        return False
    except Exception as e:
        key = type(e).__name__
        if key not in _ui_failure_logged:
            _ui_failure_logged[key] = True
            _safe_log(f"[UI] state_update_failed reason={key}")
        return False


_pump_thread: Optional[threading.Thread] = None
_pump_running = False


def start_ui_bridge_pump(queue, stop_event=None) -> None:
    """Start a daemon thread in the UI process that consumes bridge events.

    Must be called BEFORE eel.start(). The thread is a daemon so it dies
    when the process exits; no explicit join needed.
    """
    global _pump_thread, _pump_running
    if queue is None:
        _safe_log("[BRIDGE] no queue provided — pump not started")
        return
    if _pump_running:
        return

    _pump_running = True
    _safe_log(f"[BRIDGE] ui pump started pid={os.getpid()} queue=yes")

    def _pump():
        global _pump_running
        while _pump_running:
            if stop_event is not None and stop_event.is_set():
                break
            try:
                event = queue.get(timeout=0.25)
            except Exception:
                continue
            try:
                handle_bridge_event(event)
            except Exception as e:
                _safe_log(f"[BRIDGE] event handling error reason={type(e).__name__}")
        _safe_log("[BRIDGE] ui pump stopped")

    _pump_thread = threading.Thread(target=_pump, daemon=True, name="bridge-pump")
    _pump_thread.start()


def stop_ui_bridge_pump() -> None:
    global _pump_running
    _pump_running = False
