"""One typed owner for "NEXI asked something and is waiting for the answer".

Conversational state was spread across five process-global stores
(turn_manager, followup_manager, clarification_manager, workflow_state,
workflow_manager). None of them recorded WHICH session or turn the question
belonged to, so a question raised in one session was silently visible in the
next. Live consequence:

    [UI]      create a folder      -> pending folder_name (session: none)
    ... user walks away, session ends ...
    [hotword] "Create a folder"    -> consumed as the ANSWER to the old question
    [WORKFLOW] slot_saved name=folder_name      <- named the folder "Create a folder"

Session binding is the invariant this module exists to enforce: a context
belongs to exactly one session, and a different session can neither see nor
answer it.

This does not delete the old stores. It is introduced alongside them, with
adapters, and workflow families migrate onto it one at a time.
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DialogueStatus(str, Enum):
    NONE = "NONE"
    COLLECTING_INFORMATION = "COLLECTING_INFORMATION"
    AWAITING_USER = "AWAITING_USER"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    READY_TO_EXECUTE = "READY_TO_EXECUTE"
    EXECUTING = "EXECUTING"
    VERIFYING = "VERIFYING"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class CaptureState(str, Enum):
    """Durable replacement for the boolean auto-listen flag.

    A boolean cannot express "requested but not yet acknowledged", so the
    request was cleared while NEXI was still speaking the question and the
    microphone never opened. The request must survive until the audio process
    acknowledges CAPTURE_STARTED.
    """
    NONE = "NONE"
    REQUESTED = "FOLLOWUP_REQUESTED"
    QUEUED = "FOLLOWUP_QUEUED"
    CAPTURE_STARTED = "FOLLOWUP_CAPTURE_STARTED"
    SPEECH_STARTED = "FOLLOWUP_SPEECH_STARTED"
    COMPLETED = "FOLLOWUP_COMPLETED"
    NO_SPEECH = "FOLLOWUP_NO_SPEECH"
    CANCELLED = "FOLLOWUP_CANCELLED"
    FAILED = "FOLLOWUP_FAILED"


#: States after which the capture request is finished and may be dropped.
_CAPTURE_TERMINAL = frozenset({
    CaptureState.COMPLETED, CaptureState.NO_SPEECH,
    CaptureState.CANCELLED, CaptureState.FAILED,
})

#: Statuses that mean the dialogue is over and must not be answered.
_DIALOGUE_TERMINAL = frozenset({
    DialogueStatus.COMPLETED, DialogueStatus.CANCELLED, DialogueStatus.EXPIRED,
})

DEFAULT_TTL_SECONDS = 120.0


@dataclass
class DialogueContext:
    dialogue_id: str
    session_id: str
    turn_id: str = ""
    workflow_id: str = ""
    parent_turn_id: str = ""
    goal: str = ""
    question: str = ""
    required_fields: list[str] = field(default_factory=list)
    collected_fields: dict[str, Any] = field(default_factory=dict)
    expected_response_schema: dict[str, Any] = field(default_factory=dict)
    status: DialogueStatus = DialogueStatus.NONE
    capture_state: CaptureState = CaptureState.NONE
    source: str = ""
    followup_channel: str = "either"  # voice | text | either
    created_at: float = 0.0
    expires_at: float = 0.0
    retry_count: int = 0

    # --- queries -------------------------------------------------------

    def is_expired(self, now: float | None = None) -> bool:
        stamp = time.time() if now is None else now
        return self.expires_at > 0.0 and stamp >= self.expires_at

    def belongs_to(self, session_id: str) -> bool:
        """A question may only be answered inside the session that asked it.

        A context with no session (typed request before a session exists) is
        answerable by the next session that adopts it — see adopt_session.
        """
        if not self.session_id:
            return True
        return self.session_id == (session_id or "")

    def missing_fields(self) -> list[str]:
        return [f for f in self.required_fields if f not in self.collected_fields]

    def is_complete(self) -> bool:
        return not self.missing_fields()

    def is_awaiting(self) -> bool:
        return self.status in (DialogueStatus.AWAITING_USER,
                               DialogueStatus.AWAITING_APPROVAL,
                               DialogueStatus.COLLECTING_INFORMATION)

    def capture_is_pending(self) -> bool:
        """True while a microphone request is outstanding.

        Deliberately includes REQUESTED and QUEUED: the request must NOT be
        dropped merely because NEXI is speaking the question.
        """
        return (self.capture_state is not CaptureState.NONE
                and self.capture_state not in _CAPTURE_TERMINAL)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dialogue_id": self.dialogue_id, "session_id": self.session_id,
            "turn_id": self.turn_id, "workflow_id": self.workflow_id,
            "goal": self.goal, "question": self.question,
            "required_fields": list(self.required_fields),
            "collected_fields": dict(self.collected_fields),
            "status": self.status.value, "capture_state": self.capture_state.value,
            "source": self.source, "followup_channel": self.followup_channel,
            "expires_at": self.expires_at, "retry_count": self.retry_count,
        }


_lock = threading.RLock()
_active: DialogueContext | None = None


def _log(message: str) -> None:
    print(message, flush=True)


def open_dialogue(
    *,
    question: str,
    session_id: str = "",
    turn_id: str = "",
    workflow_id: str = "",
    goal: str = "",
    required_fields: list[str] | None = None,
    expected_response_schema: dict[str, Any] | None = None,
    source: str = "",
    followup_channel: str = "either",
    ttl_seconds: float = DEFAULT_TTL_SECONDS,
    status: DialogueStatus = DialogueStatus.AWAITING_USER,
) -> DialogueContext:
    """Register the one question NEXI is currently waiting on."""
    global _active
    now = time.time()
    ctx = DialogueContext(
        dialogue_id=uuid.uuid4().hex[:12],
        session_id=session_id or "",
        turn_id=turn_id or "",
        workflow_id=workflow_id or "",
        goal=goal or "",
        question=(question or "").strip()[:500],
        required_fields=list(required_fields or []),
        expected_response_schema=dict(expected_response_schema or {}),
        status=status,
        source=source or "",
        followup_channel=followup_channel or "either",
        created_at=now,
        expires_at=now + max(1.0, float(ttl_seconds)),
    )
    with _lock:
        _active = ctx
    _log(f"[DIALOGUE] opened id={ctx.dialogue_id} workflow={ctx.workflow_id or 'none'} "
         f"session={ctx.session_id or 'none'} status={ctx.status.value}")
    return ctx


def get_active(session_id: str | None = None) -> DialogueContext | None:
    """The current dialogue, or None if it is expired or owned elsewhere.

    Passing a session_id enforces ownership. This is the check that stops a new
    wake session from inheriting - and answering - a question raised earlier.
    """
    global _active
    with _lock:
        ctx = _active
        if ctx is None:
            return None
        if ctx.is_expired():
            ctx.status = DialogueStatus.EXPIRED
            _active = None
            _log(f"[DIALOGUE] expired id={ctx.dialogue_id}")
            return None
        if ctx.status in _DIALOGUE_TERMINAL:
            return None
        if session_id is not None and not ctx.belongs_to(session_id):
            _log(f"[DIALOGUE] foreign_session_ignored id={ctx.dialogue_id} "
                 f"owner={ctx.session_id or 'none'} asked_by={session_id or 'none'}")
            return None
        return ctx


def adopt_session(session_id: str) -> bool:
    """Bind a not-yet-owned dialogue to the session that just started for it.

    A typed request opens a dialogue before any voice session exists. When the
    audio process starts a session to capture the answer, that session becomes
    the owner. A dialogue that already has an owner is never re-homed.
    """
    with _lock:
        ctx = _active
        if ctx is None or ctx.session_id or not session_id:
            return False
        ctx.session_id = session_id
        _log(f"[DIALOGUE] adopted id={ctx.dialogue_id} session={session_id}")
        return True


def collect_field(name: str, value: Any, *, session_id: str | None = None) -> DialogueContext | None:
    ctx = get_active(session_id)
    if ctx is None or not name:
        return None
    with _lock:
        ctx.collected_fields[name] = value
        if ctx.is_complete():
            ctx.status = DialogueStatus.READY_TO_EXECUTE
        else:
            ctx.status = DialogueStatus.COLLECTING_INFORMATION
    _log(f"[DIALOGUE] field_collected id={ctx.dialogue_id} name={name} "
         f"missing={len(ctx.missing_fields())}")
    return ctx


def set_capture_state(state: CaptureState, *, reason: str = "") -> DialogueContext | None:
    with _lock:
        ctx = _active
        if ctx is None:
            return None
        ctx.capture_state = state
    _log(f"[DIALOGUE] capture={state.value}{(' reason=' + reason) if reason else ''}")
    return ctx


def capture_is_pending() -> bool:
    with _lock:
        return bool(_active is not None and _active.capture_is_pending())


def close_dialogue(reason: str, *, status: DialogueStatus = DialogueStatus.COMPLETED) -> None:
    global _active
    with _lock:
        ctx = _active
        _active = None
    if ctx is not None:
        _log(f"[DIALOGUE] closed id={ctx.dialogue_id} status={status.value} reason={reason}")


def cancel_dialogue(reason: str = "cancelled") -> None:
    close_dialogue(reason, status=DialogueStatus.CANCELLED)


def on_session_finished(session_id: str) -> None:
    """Drop a dialogue owned by a session that has ended.

    Without this the question outlives its session and the NEXT session picks it
    up - the observed stale-workflow leak.
    """
    global _active
    with _lock:
        ctx = _active
        if ctx is None or not ctx.session_id or ctx.session_id != session_id:
            return
        _active = None
    _log(f"[DIALOGUE] dropped_with_session id={ctx.dialogue_id} session={session_id}")


def reset_for_tests() -> None:
    global _active
    with _lock:
        _active = None
