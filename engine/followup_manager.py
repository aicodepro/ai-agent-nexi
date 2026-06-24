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


def set_pending_followup(question: str, followup_type: str, source: str) -> None:
    global _pending
    _pending = {
        "waiting": True,
        "question": (question or "").strip(),
        "followup_type": (followup_type or "generic").strip() or "generic",
        "source": (source or "assistant").strip() or "assistant",
        "created_at": time.time(),
        "ttl_seconds": _TTL_SECONDS,
    }
    print(f"[FOLLOWUP] set type={_pending['followup_type']}", flush=True)


def _expired() -> bool:
    if not _pending:
        return True
    return time.time() - float(_pending.get("created_at", 0)) > float(_pending.get("ttl_seconds", _TTL_SECONDS))


def has_pending_followup() -> bool:
    if _expired():
        clear_followup("expired")
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
        return {"handled": True, "cancelled": True, "text": value, "route": "cancel", "followup_type": ftype}
    if lower.startswith(_SWITCH_STARTS) and ftype not in {"generic", "confirmation"}:
        clear_followup("switch")
        route = lower.split(" ", 1)[0]
        print(f"[FOLLOWUP] switch_detected to={route}", flush=True)
        return {"handled": False, "text": value, "route": "switch", "followup_type": ftype}
    clear_followup("consumed")
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
