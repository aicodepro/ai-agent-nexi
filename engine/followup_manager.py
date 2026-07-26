from __future__ import annotations

import time

_pending: dict = {}
_TTL_SECONDS = 60

_CANCEL = {"cancel", "stop", "sleep", "never mind", "nevermind", "forget it"}
_SWITCH_STARTS = (
    "open ", "create ", "make ", "search ", "play ", "close ", "what is ", "who is ",
    "tell me about ", "give me ", "write ", "start ", "launch ",
)

_WEBSITE_ANSWERS = {"youtube", "gmail", "github"}


def _current_session_id() -> str:
    try:
        from engine.runtime_bridge import current_bridge_session_id
        return str(current_bridge_session_id() or "")
    except Exception:
        return ""


def set_pending_followup(question: str, followup_type: str, source: str) -> None:
    global _pending
    _pending = {
        "waiting": True,
        "question": (question or "").strip(),
        "followup_type": (followup_type or "generic").strip() or "generic",
        "source": (source or "assistant").strip() or "assistant",
        "created_at": time.time(),
        "ttl_seconds": _TTL_SECONDS,
        # Which session asked. Without this a question raised in one session was
        # visible - and answerable - in the next, so a fresh "Create a folder"
        # was consumed as the ANSWER to a question asked before the user walked
        # away, and became the folder's name.
        "session_id": _current_session_id(),
        # A typed request opens the question before any session exists. Only a
        # question with an outstanding microphone request may be adopted by the
        # session that starts to capture it; anything else is stale.
        "capture_requested": False,
    }
    print(f"[FOLLOWUP] set type={_pending['followup_type']}", flush=True)


def mark_capture_requested() -> None:
    """The microphone has been asked for on behalf of this question."""
    if _pending:
        _pending["capture_requested"] = True


def on_session_started(session_id: str) -> None:
    """A new session began. Adopt the pending question or discard it.

    Adopt only when a capture was requested for it - that is the typed-request
    path, where the session exists precisely to hear this answer. Otherwise the
    question belongs to a conversation the user has already left.
    """
    if not _pending or not session_id:
        return
    owner = str(_pending.get("session_id") or "")
    if owner == session_id:
        return
    if not owner and _pending.get("capture_requested"):
        _pending["session_id"] = session_id
        print(f"[FOLLOWUP] adopted_by_session id={session_id}", flush=True)
        return
    clear_followup(f"stale_for_session:{session_id}")


def _owned_by_current_session() -> bool:
    owner = str(_pending.get("session_id") or "")
    if not owner:
        return True  # not yet owned; a capture may still adopt it
    current = _current_session_id()
    if not current:
        return True  # no session context available (typed turn) - do not block
    return owner == current


def _expired() -> bool:
    if not _pending:
        return True
    return time.time() - float(_pending.get("created_at", 0)) > float(_pending.get("ttl_seconds", _TTL_SECONDS))


def has_pending_followup() -> bool:
    if _expired():
        clear_followup("expired")
        return False
    if not _owned_by_current_session():
        print("[FOLLOWUP] foreign_session_ignored", flush=True)
        return False
    return bool(_pending.get("waiting"))


def peek_pending_followup() -> dict:
    if not has_pending_followup():
        return {}
    return dict(_pending)


def clear_followup(reason: str = "") -> None:
    global _pending
    if _pending:
        print(f"[FOLLOWUP] cleared reason={(reason or '').strip()}", flush=True)
    _pending = {}


#: A wrong-typed answer is re-asked rather than accepted, but not forever - an
#: endless reprompt loop is its own failure mode.
_MAX_SCHEMA_RETRIES = 2


def _validate_against_schema(schema_name: str, value: str):
    """None when no schema applies, else a ValidationResult."""
    try:
        from engine.response_schemas import get_schema, validate_answer
        if get_schema(schema_name) is None:
            return None
        return validate_answer(schema_name, value)
    except Exception:
        return None


def _close_dialogue(reason: str, *, cancelled: bool) -> None:
    """Keep the new DialogueContext in step with the legacy follow-up store.

    Both exist during the migration; letting them disagree would recreate the
    ownership bug this work is fixing.
    """
    try:
        from engine import dialogue_context as dc
        if cancelled:
            dc.cancel_dialogue(reason)
        else:
            dc.close_dialogue(reason)
    except Exception:
        pass


def _slot_for_followup_type(followup_type: str) -> str:
    try:
        from engine.clarification_manager import slot_for_followup_type
        return slot_for_followup_type(followup_type)
    except Exception:
        return ""


def _route_pending_answer(followup_type: str, value: str) -> tuple[str, str]:
    lower = value.lower().rstrip(".?!")
    if followup_type == "open_app":
        if lower in _WEBSITE_ANSWERS or "." in lower:
            return f"open {value}", "local_skill"
        return f"open {value}", "local_skill"
    if followup_type == "open_website":
        return f"open {value}", "local_skill"
    if followup_type == "web_search":
        return f"search {value}", "local_skill"
    if followup_type == "essay_topic":
        return f"write an essay about {value}", "brain_continuation"
    if followup_type == "nexi_start_studio_build":
        return f"let's build {value}", "workflow"
    return value, "workflow"


def consume_followup_answer(text: str, source: str) -> dict:
    value = (text or "").strip()
    if not has_pending_followup():
        return {"handled": False, "text": value, "route": "none"}
    pending = dict(_pending)
    ftype = pending.get("followup_type", "generic")
    lower = value.lower().rstrip(".?!")
    print(f"[FOLLOWUP] answer_received type={ftype}", flush=True)
    slot = _slot_for_followup_type(ftype)
    if slot:
        print(f"[FOLLOWUP] answer_received slot={slot} value={value[:80]}", flush=True)
    if lower in _CANCEL:
        clear_followup("cancel")
        _close_dialogue("user_cancelled", cancelled=True)
        return {"handled": True, "cancelled": True, "text": value, "route": "cancel", "followup_type": ftype}
    if lower.startswith(_SWITCH_STARTS) and ftype not in {"generic", "confirmation"}:
        clear_followup("switch")
        _close_dialogue("switch", cancelled=True)
        route = lower.split(" ", 1)[0]
        print(f"[FOLLOWUP] switch_detected to={route}", flush=True)
        return {"handled": False, "text": value, "route": "switch", "followup_type": ftype}

    # The reply must be the KIND of thing that was asked for. Without this a
    # pending question accepted whatever arrived next, which is how
    # "show me your diagnostics" was stored as a folder name.
    slot_schema = slot or ftype
    validation = _validate_against_schema(slot_schema, value)
    if validation is not None and not validation.ok:
        retries = int(_pending.get("retries", 0)) + 1
        if retries <= _MAX_SCHEMA_RETRIES:
            _pending["retries"] = retries
            _pending["created_at"] = time.time()  # the user is engaged; keep waiting
            from engine.response_schemas import reprompt_for
            question = reprompt_for(slot_schema)
            print(f"[FOLLOWUP] answer_rejected slot={slot_schema} "
                  f"reason={validation.error} retry={retries}", flush=True)
            return {"handled": True, "cancelled": False, "reprompt": True,
                    "text": question, "answer": value, "route": "clarify",
                    "followup_type": ftype, "question": question}
        clear_followup("schema_retries_exhausted")
        _close_dialogue("schema_retries_exhausted", cancelled=True)
        print(f"[FOLLOWUP] answer_rejected slot={slot_schema} reason=retries_exhausted", flush=True)
        return {"handled": False, "text": value, "route": "none", "followup_type": ftype}

    if validation is not None and validation.value is not None:
        value = validation.value if isinstance(validation.value, str) else value

    clear_followup("consumed")
    _close_dialogue("consumed", cancelled=False)
    routed, route = _route_pending_answer(ftype, value)
    print(f"[FOLLOWUP] consumed type={ftype}", flush=True)
    return {
        "handled": True,
        "cancelled": False,
        "text": routed,
        "answer": value,
        "route": route,
        "followup_type": ftype,
        "question": pending.get("question", ""),
        "source": pending.get("source", ""),
    }
