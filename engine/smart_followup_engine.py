from __future__ import annotations

from typing import Any

from engine.intent_taxonomy import empty_result, exact_schema


YES = {"yes", "yeah", "yep", "sure", "ok", "okay", "confirm", "do it"}
NO = {"no", "nope", "nah", "don't", "dont"}
CANCEL = {"cancel", "never mind", "nevermind", "forget it", "stop"}


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().rstrip(".?!").split())


def _latest_available(context: dict | None = None) -> bool:
    latest = (context or {}).get("latest_output") or {}
    if latest.get("available"):
        return True
    try:
        from engine.output_actions import get_latest_output

        return bool(get_latest_output().get("content"))
    except Exception:
        return False


def resolve_followup(text: str, context: dict | None = None) -> dict[str, Any] | None:
    q = _norm(text)
    if not q:
        return None
    if q in CANCEL:
        return empty_result(route="cancel", intent="cancel", domain="system", confidence=1.0, reason="followup_cancel")
    if q in YES:
        return exact_schema(empty_result(route="followup", intent="confirmation", domain="conversation", confidence=0.96, reason="followup_yes") | {"slots": {"answer": True}})
    if q in NO:
        return exact_schema(empty_result(route="followup", intent="confirmation", domain="conversation", confidence=0.96, reason="followup_no") | {"slots": {"answer": False}})

    output_available = _latest_available(context)
    if q in {"copy it", "copy this", "copy latest", "copy latest output"}:
        return empty_result(route="output", intent="copy_latest_output", domain="output", confidence=0.98, reason="copy_followup")
    if q.startswith("save it as "):
        return exact_schema(empty_result(route="output", intent="save_latest_output", domain="output", confidence=0.98, reason="save_followup") | {"slots": {"file_name": text[11:].strip()}})
    if q in {"save it", "save this", "save latest"}:
        return exact_schema(empty_result(route="clarify", intent="save_latest_output", domain="output", confidence=0.98, reason="save_missing_name", clarification_question="What should I name the file?") | {"missing_slots": ["file_name"]})
    if q in {"open it", "open this", "show it again", "show latest", "show latest output", "again"}:
        if output_available:
            return empty_result(route="output", intent="show_latest_output", domain="output", confidence=0.94, reason="show_followup")
        return empty_result(route="system", intent="repeat_last", domain="conversation", confidence=0.85, reason="repeat_followup")
    if q in {"make it shorter", "shorten it", "shorten this", "shorter"}:
        return empty_result(route="output", intent="shorten_latest_output", domain="output", confidence=0.95, reason="shorten_followup")
    if q in {"continue", "continue it", "keep going"}:
        return empty_result(route="clarify", intent="continue_response", domain="conversation", confidence=0.7, reason="continue_needs_instruction", clarification_question="What should I continue with?")
    return None


def execute_output_action(intent: str, slots: dict | None = None) -> dict[str, Any]:
    values = dict(slots or {})
    try:
        from engine import output_actions

        if intent == "copy_latest_output":
            result = output_actions.copy_latest_output()
        elif intent in {"save_latest_output", "create_file_from_latest_output"}:
            filename = values.get("file_name") or values.get("filename")
            result = output_actions.save_latest_output_as(str(filename or "")) if filename else output_actions.create_output_file()
        elif intent == "show_latest_output":
            result = output_actions.reopen_latest_output()
        elif intent == "read_output_summary":
            text = output_actions.summarize_latest_output(420)
            result = {"ok": bool(text), "message": text or "There is no output to summarize yet."}
        elif intent == "shorten_latest_output":
            text = output_actions.summarize_latest_output(420)
            result = {"ok": bool(text), "message": text or "I don't have anything to shorten yet."}
        elif intent == "regenerate_latest_output":
            result = {"ok": False, "message": "I can regenerate it if you tell me what to change."}
        else:
            result = {"ok": False, "message": "I don't know that output action yet."}
    except Exception:
        result = {"ok": False, "message": "I couldn't run that output action safely."}
    ok = bool(result.get("ok"))
    return {"handled": True, "ok": ok, "success": ok, "verified": ok, "message": result.get("message", ""), **result}
