from __future__ import annotations

from engine.assistant_response import make_response


_pending: dict = {}

_SLOT_BY_FOLLOWUP_TYPE = {
    "open_app": "app_name",
    "open_website": "url",
    "web_search": "query",
    "essay_topic": "topic",
    "folder_name": "folder_name",
    "file_name": "file_name",
    "save_latest_output": "file_name",
    "camera_mode": "mode",
    "confirmation": "confirmation",
}


def clarification_for_text(text: str, reason: str = "clarify") -> dict:
    q = (text or "").strip().lower().rstrip(".?!")
    if q in {"open", "launch", "start"}:
        question = "Which app should I open?"
        followup_type = "open_app"
    elif q in {"search", "google", "search web", "search the web"}:
        question = "What should I search for?"
        followup_type = "web_search"
    elif q in {"write essay", "write an essay", "essay"}:
        question = "Which topic, sir?"
        followup_type = "essay_topic"
    elif q in {"create folder", "create a folder", "make folder"}:
        question = "What should I name it?"
        followup_type = "folder_name"
    elif q in {"start camera control", "start hand gesture control", "start hand control", "start eye mouse"}:
        question = "Preview or control mode?"
        followup_type = "camera_mode"
    else:
        question = "I didn't catch that. Please say it again in English."
        followup_type = "generic"
    response = make_response(
        question,
        expects_user_reply=True,
        followup_question=question,
        followup_type=followup_type,
        source="clarify",
        metadata={"reason": reason},
    )
    return response


def ask_clarification(text: str, reason: str = "clarify") -> dict:
    response = clarification_for_text(text, reason=reason)
    question = response["followup_question"]
    _pending.clear()
    _pending.update({"pending": True, "question": question, "reason": reason, "followup_type": response["followup_type"]})
    print(f'[CLARIFY] question="{question}"', flush=True)
    print(f"[CLARIFY] pending=true reason={reason}", flush=True)
    try:
        from engine.followup_manager import set_pending_followup
        set_pending_followup(question, response["followup_type"], "clarify")
    except Exception:
        pass
    try:
        from engine.turn_manager import mark_waiting_for_user
        mark_waiting_for_user(question, reason="clarification", workflow_id=response["followup_type"])
    except Exception:
        pass
    return response


def ask_custom_clarification(question: str, followup_type: str = "generic", reason: str = "clarify") -> dict:
    prompt = (question or "").strip() or "I didn't catch that. Please say it again in English."
    ftype = (followup_type or "generic").strip() or "generic"
    response = make_response(
        prompt,
        expects_user_reply=True,
        followup_question=prompt,
        followup_type=ftype,
        source="clarify",
        metadata={"reason": reason},
    )
    _pending.clear()
    _pending.update({"pending": True, "question": prompt, "reason": reason, "followup_type": ftype})
    print(f'[CLARIFY] question="{prompt}"', flush=True)
    print(f"[CLARIFY] pending=true reason={reason}", flush=True)
    try:
        from engine.followup_manager import set_pending_followup
        set_pending_followup(prompt, ftype, "clarify")
    except Exception:
        pass
    try:
        from engine.turn_manager import mark_waiting_for_user
        mark_waiting_for_user(prompt, reason="clarification", workflow_id=ftype)
    except Exception:
        pass
    return response


def has_pending_clarification() -> bool:
    return bool(_pending.get("pending"))


def clear_clarification(reason: str = "") -> None:
    if _pending:
        print(f"[CLARIFY] cleared reason={(reason or '').strip()}", flush=True)
    _pending.clear()


def slot_for_followup_type(followup_type: str) -> str:
    return _SLOT_BY_FOLLOWUP_TYPE.get((followup_type or "").strip(), "")


def receive_answer(text: str, followup_type: str | None = None) -> dict:
    preview = (text or "").strip()[:80]
    pending = dict(_pending)
    ftype = followup_type or pending.get("followup_type", "")
    slot = slot_for_followup_type(ftype)
    if slot:
        print(f"[CLARIFY] answer_received slot={slot} value={preview}", flush=True)
    else:
        print(f"[CLARIFY] answer_received text={preview}", flush=True)
    _pending.clear()
    return {"handled": bool(pending), "answer": text, "pending": pending}
