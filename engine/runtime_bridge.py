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
import uuid
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
EVENT_BARGE_IN_REQUEST = "barge_in_request"
EVENT_TTS_WATCHDOG_STOP = "tts_watchdog_stop"
CONTROL_FINISH_SESSION = "finish_session"
CONTROL_CAPTURE_FOLLOWUP = "capture_followup"
CONTROL_TTS_STARTED = "tts_started"
CONTROL_TTS_HEARTBEAT = "tts_heartbeat"
CONTROL_TTS_FINISHED = "tts_finished"
CONTROL_TTS_INTERRUPTED = "tts_interrupted"
CONTROL_COOLDOWN_COMPLETE = "cooldown_complete"
CONTROL_GLOBAL_TTS_STARTED = "global_tts_started"
CONTROL_GLOBAL_TTS_HEARTBEAT = "global_tts_heartbeat"
CONTROL_GLOBAL_TTS_FINISHED = "global_tts_finished"
CONTROL_GLOBAL_TTS_INTERRUPTED = "global_tts_interrupted"
CONTROL_GLOBAL_COOLDOWN_COMPLETE = "global_cooldown_complete"
CONTROL_BARGE_IN_ACK = "barge_in_ack"
CONTROL_TURN_PROGRESS = "turn_progress"
CONTROL_TTS_WATCHDOG_ACK = "tts_watchdog_ack"

# Status-to-UI-state mapping with source-aware differentiation
STATUS_TO_UI_STATE = {
    EVENT_WAKE_DETECTED: "online",
    EVENT_LISTENING_STARTED: "listening",
    "listening": "listening",
    EVENT_WAITING_FOR_SPEECH: "waiting_for_speech",
    "waiting_for_speech": "waiting_for_speech",
    EVENT_SPEECH_STARTED: "recognising",
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
    session_epoch: float = 0.0
    request_id: str = ""

    def to_dict(self) -> dict:
        data = asdict(self)
        if not data["created_at"]:
            data["created_at"] = time.time()
        from engine.wake_session_manager import get_session_manager
        sid = data.get("session_id") or get_session_manager().get_session_id()
        if sid:
            data["session_id"] = sid
            if not data.get("session_epoch"):
                data["session_epoch"] = get_session_manager().get_session_epoch()
        return data


_bridge_context = threading.local()
_lifecycle_sequence_lock = threading.Lock()
_lifecycle_sequences: dict[str, int] = {}
_session_generation_lock = threading.Lock()
_accepted_session_id = ""
_accepted_session_epoch = 0.0
_latest_session_epoch = 0.0
_closed_session_generations: dict[str, float] = {}
_terminal_session_generations: set[tuple[str, float]] = set()
_barge_in_continuations: dict[tuple[str, float], dict] = {}
_active_command_tokens: dict[tuple[str, float], set[str]] = {}


def current_bridge_session_id() -> str:
    return str(getattr(_bridge_context, "session_id", "") or "")


def current_bridge_session_epoch() -> float:
    return float(getattr(_bridge_context, "session_epoch", 0.0) or 0.0)


def reset_bridge_session_generations() -> None:
    global _accepted_session_id, _accepted_session_epoch, _latest_session_epoch
    with _session_generation_lock:
        _accepted_session_id = ""
        _accepted_session_epoch = 0.0
        _latest_session_epoch = 0.0
        _closed_session_generations.clear()
        _terminal_session_generations.clear()
        _barge_in_continuations.clear()
        _active_command_tokens.clear()


def _continuation_timeout_seconds() -> float:
    try:
        return max(0.01, float(os.getenv("NEXI_BARGE_IN_CONTINUATION_TIMEOUT_SECONDS", "30") or 30))
    except (TypeError, ValueError):
        return 30.0


def _mark_barge_in_session(
    session_id: str,
    session_epoch: float = 0.0,
    request_id: str = "",
) -> str:
    token = uuid.uuid4().hex
    if not session_id:
        return ""
    with _session_generation_lock:
        effective_epoch = float(session_epoch or 0.0)
        if not effective_epoch and session_id == _accepted_session_id:
            effective_epoch = _accepted_session_epoch
        generation = (session_id, effective_epoch)
        _barge_in_continuations[generation] = {
            "token": token,
            "request_id": request_id,
            "original_tokens": set(_active_command_tokens.get(generation, set())),
            "original_finalized": False,
            "followup_token": "",
            "followup_finalized": False,
            "terminal": None,
            "deadline": time.time() + _continuation_timeout_seconds(),
        }
    return token


def _consume_barge_in_session(session_id: str) -> bool:
    with _session_generation_lock:
        return any(key[0] == session_id for key in _barge_in_continuations)


def _has_pending_barge_in(session_id: str) -> bool:
    with _session_generation_lock:
        return bool(session_id and any(key[0] == session_id for key in _barge_in_continuations))


def _register_command_execution(session_id: str, session_epoch: float) -> str:
    command_token = uuid.uuid4().hex
    if not session_id:
        return command_token
    generation = (session_id, float(session_epoch or 0.0))
    with _session_generation_lock:
        _active_command_tokens.setdefault(generation, set()).add(command_token)
        continuation = _barge_in_continuations.get(generation)
        if continuation and command_token not in continuation["original_tokens"]:
            if not continuation["followup_token"]:
                continuation["followup_token"] = command_token
    return command_token


def _complete_command_execution(
    command_token: str,
    session_id: str,
    session_epoch: float,
    *,
    request_terminal: bool,
    source: str,
    reason: str,
) -> tuple[str, float, str, str] | None:
    generation = (session_id, float(session_epoch or 0.0))
    terminal = (session_id, generation[1], source, reason)
    with _session_generation_lock:
        active = _active_command_tokens.get(generation)
        if active is not None:
            active.discard(command_token)
            if not active:
                _active_command_tokens.pop(generation, None)
        continuation = _barge_in_continuations.get(generation)
        if not continuation:
            return terminal if request_terminal else None
        if command_token in continuation["original_tokens"]:
            continuation["original_tokens"].discard(command_token)
            continuation["original_finalized"] = not continuation["original_tokens"]
        elif command_token == continuation["followup_token"]:
            continuation["followup_finalized"] = True
            if request_terminal:
                continuation["terminal"] = terminal
        if continuation["original_finalized"] and continuation["followup_finalized"]:
            resolved = continuation.get("terminal")
            _barge_in_continuations.pop(generation, None)
            return resolved
        return None


def _expire_barge_in_continuations() -> None:
    expired: list[tuple[tuple[str, float], dict]] = []
    now = time.time()
    with _session_generation_lock:
        for generation, continuation in list(_barge_in_continuations.items()):
            if now >= float(continuation.get("deadline") or 0.0):
                expired.append((generation, continuation))
                _barge_in_continuations.pop(generation, None)
    for (session_id, session_epoch), continuation in expired:
        terminal = continuation.get("terminal")
        if terminal:
            _, _, source, reason = terminal
        else:
            source, reason = "ready", "barge_in_continuation_timeout"
        _emit_terminal_sleep(
            session_id,
            session_epoch,
            source=source,
            reason=reason,
        )


def _event_session_epoch(event: dict) -> float:
    try:
        return float(event.get("session_epoch") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _accept_session_generation(event: dict) -> bool:
    global _accepted_session_id, _accepted_session_epoch, _latest_session_epoch
    session_id = str(event.get("session_id") or "")
    epoch = _event_session_epoch(event)
    if not session_id or epoch <= 0.0:
        # An unstamped wake carries no session generation. Mirror the tolerance
        # _is_accepted_session_generation already documents for every OTHER event:
        # accept it only while no authoritative generation has been observed in this
        # UI process. Without this the two guards disagree -- the session-START event
        # is dropped while its followers are admitted, so the UI never receives
        # "online" and the voice state machine never leaves sleeping.
        # Once a real session exists an unstamped wake is genuinely stale, and the
        # `not _accepted_session_id` check still rejects it.
        with _session_generation_lock:
            return not _accepted_session_id
    with _session_generation_lock:
        if session_id == _accepted_session_id and epoch == _accepted_session_epoch:
            return True
        if epoch <= _latest_session_epoch:
            return False
        if _accepted_session_id:
            _closed_session_generations[_accepted_session_id] = _accepted_session_epoch
        _accepted_session_id = session_id
        _accepted_session_epoch = epoch
        _latest_session_epoch = epoch
        return True


def _is_accepted_session_generation(event: dict) -> bool:
    session_id = str(event.get("session_id") or "")
    epoch = _event_session_epoch(event)
    with _session_generation_lock:
        if session_id and session_id in _closed_session_generations:
            return False
        if not _accepted_session_id:
            # Legacy/test events without an epoch remain compatible only while no
            # authoritative generation has been observed in this UI process.
            return epoch <= 0.0
        return session_id == _accepted_session_id and (
            epoch <= 0.0 or epoch == _accepted_session_epoch
        )


def current_control_queue():
    return _control_queue


def configure_control_queue(control_queue) -> None:
    global _control_queue
    _control_queue = control_queue

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


def post_barge_in_request(
    queue,
    session_id: str,
    source: str = "hotword",
    session_epoch: float = 0.0,
) -> str:
    if queue is None or not session_id:
        return ""
    request_id = uuid.uuid4().hex[:12]
    event = BridgeEvent(
        type=EVENT_BARGE_IN_REQUEST,
        source=source or "hotword",
        session_id=session_id,
        session_epoch=float(session_epoch or 0.0),
        request_id=request_id,
    )
    return request_id if _put_event(queue, event) else ""


def post_session_finish(
    control_queue,
    session_id: str,
    reason: str = "complete",
    *,
    force: bool = False,
) -> bool:
    if control_queue is None or not session_id:
        return False
    try:
        control_queue.put_nowait({
            "type": CONTROL_FINISH_SESSION,
            "session_id": session_id,
            "reason": reason or "complete",
            "force": bool(force),
            "created_at": time.time(),
        })
        return True
    except Exception as exc:
        _safe_log(f"[SESSION] finish_enqueue_failed id={session_id} reason={type(exc).__name__}")
        return False


def post_turn_progress(control_queue, session_id: str) -> bool:
    if control_queue is None or not session_id:
        return False
    try:
        control_queue.put_nowait({
            "type": CONTROL_TURN_PROGRESS,
            "session_id": session_id,
            "created_at": time.time(),
        })
        return True
    except Exception:
        return False


def _turn_progress_loop(stop_event: threading.Event, session_id: str) -> None:
    try:
        interval = float(os.getenv("NEXI_TURN_HEARTBEAT_SECONDS", "10") or 10)
    except (TypeError, ValueError):
        interval = 10.0
    interval = min(30.0, max(0.01, interval))
    post_turn_progress(_control_queue, session_id)
    while not stop_event.wait(interval):
        post_turn_progress(_control_queue, session_id)


def _post_tts_lifecycle(
    control_queue,
    event_type: str,
    session_id: str,
    producer_id: str = "",
) -> bool:
    if control_queue is None or not session_id:
        return False
    with _lifecycle_sequence_lock:
        sequence = _lifecycle_sequences.get(session_id, 0) + 1
        try:
            control_queue.put_nowait({
                "type": event_type,
                "session_id": session_id,
                "producer_id": producer_id,
                "sequence": sequence,
                "created_at": time.time(),
            })
        except Exception:
            return False
        _lifecycle_sequences[session_id] = sequence
        return True


def _post_global_tts_lifecycle(control_queue, event_type: str, lease_id: str) -> bool:
    if control_queue is None or not lease_id:
        return False
    sequence_key = f"global:{lease_id}"
    with _lifecycle_sequence_lock:
        sequence = _lifecycle_sequences.get(sequence_key, 0) + 1
        try:
            control_queue.put_nowait({
                "type": event_type,
                "session_id": "",
                "lease_id": lease_id,
                "sequence": sequence,
                "created_at": time.time(),
            })
        except Exception:
            return False
        _lifecycle_sequences[sequence_key] = sequence
        return True


def post_tts_started(control_queue, session_id: str, producer_id: str = "") -> bool:
    return _post_tts_lifecycle(control_queue, CONTROL_TTS_STARTED, session_id, producer_id)


def post_tts_finished(control_queue, session_id: str, producer_id: str = "") -> bool:
    return _post_tts_lifecycle(control_queue, CONTROL_TTS_FINISHED, session_id, producer_id)


def post_tts_heartbeat(control_queue, session_id: str, producer_id: str = "") -> bool:
    return _post_tts_lifecycle(control_queue, CONTROL_TTS_HEARTBEAT, session_id, producer_id)


def post_tts_interrupted(control_queue, session_id: str, producer_id: str = "") -> bool:
    return _post_tts_lifecycle(control_queue, CONTROL_TTS_INTERRUPTED, session_id, producer_id)


def post_cooldown_complete(control_queue, session_id: str, producer_id: str = "") -> bool:
    return _post_tts_lifecycle(control_queue, CONTROL_COOLDOWN_COMPLETE, session_id, producer_id)


def notify_tts_started(session_id: str = "", producer_id: str = "") -> bool:
    return post_tts_started(_control_queue, session_id or current_bridge_session_id(), producer_id)


def notify_tts_finished(session_id: str = "", producer_id: str = "") -> bool:
    return post_tts_finished(_control_queue, session_id or current_bridge_session_id(), producer_id)


def notify_tts_heartbeat(session_id: str = "", producer_id: str = "") -> bool:
    return post_tts_heartbeat(_control_queue, session_id or current_bridge_session_id(), producer_id)


def notify_tts_interrupted(session_id: str = "", producer_id: str = "") -> bool:
    return post_tts_interrupted(_control_queue, session_id or current_bridge_session_id(), producer_id)


def notify_cooldown_complete(session_id: str = "", producer_id: str = "") -> bool:
    return post_cooldown_complete(_control_queue, session_id or current_bridge_session_id(), producer_id)


def post_global_tts_started(control_queue, lease_id: str) -> bool:
    return _post_global_tts_lifecycle(control_queue, CONTROL_GLOBAL_TTS_STARTED, lease_id)


def post_global_tts_heartbeat(control_queue, lease_id: str) -> bool:
    return _post_global_tts_lifecycle(control_queue, CONTROL_GLOBAL_TTS_HEARTBEAT, lease_id)


def post_global_tts_finished(control_queue, lease_id: str) -> bool:
    return _post_global_tts_lifecycle(control_queue, CONTROL_GLOBAL_TTS_FINISHED, lease_id)


def post_global_tts_interrupted(control_queue, lease_id: str) -> bool:
    return _post_global_tts_lifecycle(control_queue, CONTROL_GLOBAL_TTS_INTERRUPTED, lease_id)


def post_global_cooldown_complete(control_queue, lease_id: str) -> bool:
    return _post_global_tts_lifecycle(control_queue, CONTROL_GLOBAL_COOLDOWN_COMPLETE, lease_id)


def post_barge_in_ack(
    control_queue,
    session_id: str,
    session_epoch: float,
    request_id: str,
    *,
    accepted: bool,
    continuation_token: str = "",
) -> bool:
    if control_queue is None or not session_id or not request_id:
        return False
    try:
        control_queue.put_nowait({
            "type": CONTROL_BARGE_IN_ACK,
            "session_id": session_id,
            "session_epoch": float(session_epoch or 0.0),
            "request_id": request_id,
            "accepted": bool(accepted),
            "continuation_token": continuation_token if accepted else "",
            "created_at": time.time(),
        })
        return True
    except Exception as exc:
        _safe_log(f"[BARGE_IN] ack_enqueue_failed id={session_id} reason={type(exc).__name__}")
        return False


def post_tts_watchdog_ack(control_queue, request: dict, *, stopped: bool) -> bool:
    if control_queue is None or not request.get("request_id"):
        return False
    try:
        control_queue.put_nowait({
            "type": CONTROL_TTS_WATCHDOG_ACK,
            "scope": str(request.get("scope") or "voice"),
            "session_id": str(request.get("session_id") or ""),
            "session_epoch": float(request.get("session_epoch") or 0.0),
            "lease_id": str(request.get("lease_id") or ""),
            "producer_id": str(request.get("producer_id") or ""),
            "request_id": str(request.get("request_id") or ""),
            "stopped": bool(stopped),
            "created_at": time.time(),
        })
        return True
    except Exception:
        return False


def notify_global_tts_started() -> str:
    lease_id = uuid.uuid4().hex[:12]
    return lease_id if post_global_tts_started(_control_queue, lease_id) else ""


def notify_global_tts_heartbeat(lease_id: str) -> bool:
    return post_global_tts_heartbeat(_control_queue, lease_id)


def notify_global_tts_finished(lease_id: str) -> bool:
    return post_global_tts_finished(_control_queue, lease_id)


def notify_global_tts_interrupted(lease_id: str) -> bool:
    return post_global_tts_interrupted(_control_queue, lease_id)


def notify_global_cooldown_complete(lease_id: str) -> bool:
    return post_global_cooldown_complete(_control_queue, lease_id)


def post_followup_capture(
    control_queue,
    session_id: str,
    *,
    source: str,
    reason: str,
    delay_ms: int = 0,
) -> bool:
    if control_queue is None:
        return False
    try:
        control_queue.put_nowait({
            "type": CONTROL_CAPTURE_FOLLOWUP,
            "session_id": session_id,
            # A typed request has no voice session, so current_bridge_session_id()
            # is empty and this used to return False - NEXI asked a question and
            # then could never open the microphone to hear the answer. A typed
            # request is still a NEXI turn: ask the audio process to start a
            # session for the capture instead of dropping it.
            "start_session": not session_id,
            "source": (source or "voice").strip() or "voice",
            "reason": (reason or "assistant_question").strip() or "assistant_question",
            "not_before": time.time() + (max(0, int(delay_ms)) / 1000.0),
            "created_at": time.time(),
        })
        return True
    except Exception:
        return False


def request_followup_capture(*, source: str, reason: str) -> bool:
    try:
        from engine.post_tts_cleanup import get_cooldown_remaining_ms
        delay_ms = get_cooldown_remaining_ms()
    except Exception:
        delay_ms = 0
    if delay_ms > 0:
        delay_ms += 50
    return post_followup_capture(
        _control_queue,
        current_bridge_session_id(),
        source=source,
        reason=reason,
        delay_ms=delay_ms,
    )


# ---------------------------------------------------------------------------
# Consuming (called in Process 1 — UI/Eel)
# ---------------------------------------------------------------------------

def handle_bridge_event(event: dict) -> None:
    """Dispatch a single bridge event. Runs in Process 1 where Eel lives."""
    event_session_id = event.get("session_id", "")
    etype = event.get("type", "")
    status = str(event.get("status") or "")
    if etype == EVENT_WAKE_DETECTED or (etype == EVENT_STATUS and status == EVENT_WAKE_DETECTED):
        if not _accept_session_generation(event):
            _safe_log(f"[BRIDGE] stale_session_start_ignored id={event_session_id}")
            return
        # A new conversation began. A question left over from an earlier one must
        # not consume this session's first command - that is how "Create a
        # folder" became the previous question's ANSWER, and the folder's name.
        try:
            from engine.followup_manager import on_session_started
            on_session_started(event_session_id)
        except Exception:
            pass
        try:
            # An unowned dialogue is adopted ONLY when a microphone request is
            # outstanding for it - that is the typed-request path, where this
            # session exists precisely to hear the answer. A dialogue owned by
            # another session needs no action: get_active() already refuses to
            # return it to a session that does not own it.
            from engine import dialogue_context as _dc
            if _dc.capture_is_pending():
                _dc.adopt_session(event_session_id)
        except Exception:
            pass
    if etype == EVENT_COMMAND_TEXT:
        source = str(event.get("source") or "bridge")
        is_voice_source = source in {"hotword", "clap", "double_clap", "hotkey", "ui_button", "mic_button", "voice"}
        if event_session_id or is_voice_source:
            if not _is_accepted_session_generation(event):
                _safe_log(f"[BRIDGE] stale_command_ignored id={event_session_id}")
                return
    if etype == EVENT_TTS_WATCHDOG_STOP:
        scope = str(event.get("scope") or "voice")
        if scope == "voice" and not _is_accepted_session_generation(event):
            _safe_log(f"[TTS] stale_watchdog_stop_ignored id={event_session_id}")
            post_tts_watchdog_ack(_control_queue, event, stopped=False)
            return
        try:
            from engine.interrupt_controller import request_interrupt
            request_interrupt("tts_watchdog", str(event.get("reason") or "tts_lease_expired"))
        except Exception:
            pass
        try:
            from engine import groq_tts
            groq_tts.stop()
        except Exception:
            pass
        try:
            from engine.voice.speech_controller import stop_speaking
            stop_speaking(reason="tts_watchdog")
        except Exception:
            pass
        post_tts_watchdog_ack(_control_queue, event, stopped=True)
        if scope == "global":
            lease_id = str(event.get("lease_id") or "")
            terminal_posted = post_global_tts_interrupted(_control_queue, lease_id)
            cooldown_callback = lambda: post_global_cooldown_complete(_control_queue, lease_id)
        else:
            producer_id = str(event.get("producer_id") or "")
            terminal_posted = post_tts_interrupted(_control_queue, event_session_id, producer_id)
            cooldown_callback = lambda: post_cooldown_complete(_control_queue, event_session_id, producer_id)
        if terminal_posted:
            try:
                from engine.post_tts_cleanup import post_tts_cleanup
                post_tts_cleanup(on_complete=cooldown_callback)
            except Exception:
                cooldown_callback()
        return
    if etype == EVENT_BARGE_IN_REQUEST:
        request_id = str(event.get("request_id") or "")
        source = str(event.get("source") or "hotword")
        session_epoch = _event_session_epoch(event)
        if not _is_accepted_session_generation(event):
            _safe_log(f"[BARGE_IN] stale_request_ignored id={event_session_id}")
            post_barge_in_ack(
                _control_queue,
                event_session_id,
                session_epoch,
                request_id,
                accepted=False,
            )
            return
        accepted = False
        continuation_token = ""
        try:
            from engine.barge_in_manager import interrupt
            result = interrupt(source=source, reason="hotword_during_speaking")
            accepted = bool(result.interrupted)
            if accepted:
                continuation_token = _mark_barge_in_session(
                    event_session_id,
                    session_epoch,
                    request_id,
                )
        except Exception as exc:
            _safe_log(f"[BARGE_IN] ui_interrupt_failed reason={type(exc).__name__}")
        post_barge_in_ack(
            _control_queue,
            event_session_id,
            session_epoch,
            request_id,
            accepted=accepted,
            continuation_token=continuation_token,
        )
    elif etype == EVENT_COMMAND_TEXT:
        text = (event.get("text") or "").strip()
        source = event.get("source", "bridge")
        if not text:
            return
        _safe_log(f"[BRIDGE] received command_text source={source} chars={len(text)} pid={os.getpid()}")
        previous_session_id = current_bridge_session_id()
        previous_session_epoch = current_bridge_session_epoch()
        event_session_epoch = _event_session_epoch(event)
        _bridge_context.session_id = event_session_id
        _bridge_context.session_epoch = event_session_epoch
        command_token = _register_command_execution(event_session_id, event_session_epoch)
        command_completed = False

        def _resolve_command(*, request_terminal: bool, reason: str) -> None:
            nonlocal command_completed
            if command_completed:
                return
            command_completed = True
            terminal = _complete_command_execution(
                command_token,
                event_session_id,
                event_session_epoch,
                request_terminal=request_terminal,
                source="ready",
                reason=reason,
            )
            if terminal:
                terminal_session_id, terminal_epoch, terminal_source, terminal_reason = terminal
                _emit_terminal_sleep(
                    terminal_session_id,
                    terminal_epoch,
                    source=terminal_source,
                    reason=terminal_reason,
                )
        try:
            _set_ui_state("thinking", source=source, text=text[:80], status=EVENT_THINKING_STARTED, session_id=event_session_id, session_epoch=event_session_epoch)
            _safe_log("[BRIDGE] dispatch command_bus started")
            from engine.command_bus import submit_user_command
            mode = "voice" if source in {"hotword", "clap", "double_clap", "hotkey", "ui_button", "mic_button", "voice"} else "typed"
            progress_stop = threading.Event()
            progress_thread = None
            if mode == "voice" and event_session_id:
                progress_thread = threading.Thread(
                    target=_turn_progress_loop,
                    args=(progress_stop, event_session_id),
                    name=f"TurnProgress-{event_session_id[:8]}",
                    daemon=True,
                )
                progress_thread.start()
            try:
                result = submit_user_command(text, source=source, mode=mode)
            finally:
                progress_stop.set()
                if progress_thread is not None:
                    progress_thread.join(timeout=0.2)
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
                auto_followup = (os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "true") or "").strip().lower() in {"1", "true", "yes", "on"}
                from engine.followup_manager import has_pending_followup
                from engine.clarification_manager import has_pending_clarification
                if auto_followup and (has_pending_followup() or has_pending_clarification()):
                    _safe_log("[BRIDGE] followup_capture_pending owner=audio_process")
                    _resolve_command(request_terminal=False, reason="followup_pending")
                else:
                    _resolve_command(request_terminal=True, reason="complete")
            except Exception:
                _resolve_command(request_terminal=True, reason="completion_error")
        except Exception as e:
            _safe_log(f"[BRIDGE] error reason={type(e).__name__}")
            _set_ui_state("error", source=source, text=type(e).__name__, status=EVENT_ERROR, session_id=event_session_id, session_epoch=event_session_epoch)
            _resolve_command(request_terminal=True, reason="command_error")
        finally:
            if not command_completed:
                _resolve_command(request_terminal=False, reason="abandoned")
            _bridge_context.session_id = previous_session_id
            _bridge_context.session_epoch = previous_session_epoch
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
        _set_ui_state("online", source=source, status=EVENT_WAKE_DETECTED, session_id=event_session_id, session_epoch=_event_session_epoch(event))
    elif etype == EVENT_ASR_STARTED:
        _safe_log(f"[BRIDGE] asr_started source={event.get('source', '')}")
        _set_ui_state("transcribing", source=event.get("source", ""), status=EVENT_ASR_STARTED, session_id=event_session_id, session_epoch=_event_session_epoch(event))
    elif etype == EVENT_ASR_RESULT:
        text = (event.get("text") or "").strip()
        _safe_log(f"[BRIDGE] asr_result source={event.get('source', '')} chars={len(text)}")
        if text:
            _set_ui_state("transcribing", source=event.get("source", ""), text=text[:80], status=EVENT_ASR_RESULT, session_id=event_session_id, session_epoch=_event_session_epoch(event))
            try:
                import eel
                eel.senderText(text)
            except Exception:
                pass
        else:
            _safe_log("[BRIDGE] asr_result empty — no speech captured")
            _append_log("warn", "SYS: No speech detected. Please try again.")
            _emit_terminal_sleep(
                event_session_id,
                _event_session_epoch(event),
                source=event.get("source", ""),
                reason="asr_empty",
            )
    elif etype == EVENT_ERROR:
        _safe_log(f"[BRIDGE] error reason={event.get('error', '')}")
        _set_ui_state("error", source=event.get("source", "system"), text=event.get("error", ""), status=EVENT_ERROR, session_id=event_session_id, session_epoch=_event_session_epoch(event))
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
    session_epoch = _event_session_epoch(event)
    _safe_log(f"[BRIDGE] received status={status} source={source}")
    if status in {EVENT_IDLE, EVENT_SLEEPING} and session_id:
        _emit_terminal_sleep(
            session_id,
            session_epoch,
            source=source,
            reason=status,
        )
        return
    if status == EVENT_ASR_RESULT:
        if text:
            _safe_log(f"You: {text[:80]}")
            _set_ui_state("recognising", source=source, text=text, status=status, session_id=session_id, session_epoch=session_epoch)
            _sender_text(text)
            _safe_log("SYS: Thinking...")
            _set_ui_state("thinking", source=source, text=text, status=EVENT_THINKING_STARTED, session_id=session_id, session_epoch=session_epoch)
        else:
            _safe_log("[BRIDGE] asr_result empty — saving to artifacts/last_empty_asr.wav if applicable")
            _append_log("warn", "SYS: No speech detected. Please try again.")
            _emit_terminal_sleep(
                session_id,
                session_epoch,
                source=source,
                reason="asr_empty",
            )
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
    _set_ui_state(state, source=source, text=text, status=status, session_id=session_id, session_epoch=session_epoch)


def _sender_text(text: str) -> bool:
    try:
        import eel
        eel.senderText(text)
        return True
    except Exception:
        return False


def _emit_terminal_sleep(
    session_id: str,
    session_epoch: float,
    *,
    source: str,
    reason: str,
) -> bool:
    global _accepted_session_id, _accepted_session_epoch
    if not session_id:
        _set_ui_state(
            "sleep",
            source=source or "ready",
            status=EVENT_IDLE,
        )
        return True
    generation = (session_id, float(session_epoch or 0.0))
    with _session_generation_lock:
        if generation in _terminal_session_generations:
            return False
        _terminal_session_generations.add(generation)
        _closed_session_generations[session_id] = generation[1]
        if _accepted_session_id == session_id and (
            not session_epoch or _accepted_session_epoch == session_epoch
        ):
            _accepted_session_id = ""
            _accepted_session_epoch = 0.0
    _set_ui_state(
        "sleep",
        source=source or "ready",
        status=EVENT_IDLE,
        session_id=session_id,
        session_epoch=session_epoch,
    )
    _finish_session(session_id, reason=reason)
    return True


def _finish_session(session_id: str = "", *, reason: str = "complete") -> None:
    post_session_finish(_control_queue, session_id, reason=reason)


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


def _set_ui_state(state: str, *, source: str = "system", text: str = "", status: str = "", session_id: str = "", session_epoch: float = 0.0) -> bool:
    try:
        from engine.ui_state_manager import emit_state
        effective_epoch = session_epoch or (
            current_bridge_session_epoch() if session_id and session_id == current_bridge_session_id() else 0.0
        )
        emitted = emit_state(state, source=source or "system", text=text or "", status=status or state, session_id=session_id or "", session_epoch=effective_epoch)
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
_control_queue = None


def start_ui_bridge_pump(queue, stop_event=None, control_queue=None) -> None:
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

    configure_control_queue(control_queue)
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
                _expire_barge_in_continuations()
                continue
            try:
                if isinstance(event, dict) and event.get("type") == EVENT_COMMAND_TEXT:
                    def _dispatch_command(command_event=event):
                        try:
                            handle_bridge_event(command_event)
                        except Exception as exc:
                            _safe_log(f"[BRIDGE] command handling error reason={type(exc).__name__}")

                    threading.Thread(
                        target=_dispatch_command,
                        daemon=True,
                        name="bridge-command-dispatch",
                    ).start()
                else:
                    handle_bridge_event(event)
            except Exception as e:
                _safe_log(f"[BRIDGE] event handling error reason={type(e).__name__}")
            _expire_barge_in_continuations()
        _safe_log("[BRIDGE] ui pump stopped")

    _pump_thread = threading.Thread(target=_pump, daemon=True, name="bridge-pump")
    _pump_thread.start()


def stop_ui_bridge_pump() -> None:
    global _pump_running
    _pump_running = False
