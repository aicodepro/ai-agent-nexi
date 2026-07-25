from __future__ import annotations

import re
from typing import Any

from engine.intent_taxonomy import empty_result, exact_schema


STOP_PHRASES = {"stop", "stop speaking", "stop talking", "shut up", "enough", "cancel speech"}
CANCEL_PHRASES = {"cancel", "never mind", "nevermind", "forget it", "abort"}
SLEEP_PHRASES = {"sleep", "go to sleep", "stop listening"}
WAKE_PHRASES = {"wake", "wake up", "activate nexi"}


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().rstrip(".?!").split())


def normalize_immediate_command(text: str) -> str:
    q = _norm(text)
    q = re.sub(r"^(?:(?:hey\s+)?(?:nexi|jarbos)\b[\s,]*)", "", q)
    q = re.sub(r"^(?:(?:please\s+)?(?:can|could|would|will)\s+you\s+(?:please\s+)?|please\s+)", "", q)
    q = re.sub(r"\s+(?:please|for me|please for me)$", "", q)
    return q.strip()


def _pending_followup_result(text: str, followup_type: str) -> dict[str, Any]:
    value = str(text or "").strip()
    lower = _norm(value)
    if followup_type == "open_app":
        from engine.website_resolver import looks_like_website, resolve_website
        from engine.app_resolver import resolve_app_name

        if looks_like_website(value):
            return empty_result(route="tool", intent="open_website", domain="web", confidence=0.98, reason="pending_open_target") | {"slots": {"url": resolve_website(value).get("url", value)}}
        return empty_result(route="tool", intent="open_app", domain="desktop", confidence=0.98, reason="pending_open_target") | {"slots": {"app_name": resolve_app_name(value).get("app_name", value)}}
    if followup_type == "open_website":
        from engine.website_resolver import resolve_website

        return empty_result(route="tool", intent="open_website", domain="web", confidence=0.98, reason="pending_website_target") | {"slots": {"url": resolve_website(value).get("url", value)}}
    if followup_type == "web_search":
        return empty_result(route="tool", intent="web_search", domain="web", confidence=0.98, reason="pending_search_query") | {"slots": {"query": value}}
    if followup_type in {"folder_name", "file_name", "folder_location", "camera_mode"}:
        return empty_result(route="followup", intent="workflow_answer", domain="workflow", confidence=0.94, reason="pending_slot_answer") | {"slots": {followup_type: value}}
    if lower in {"yes", "yeah", "yep", "sure", "ok", "okay", "confirm"}:
        return empty_result(route="followup", intent="confirmation", domain="conversation", confidence=0.96, reason="pending_confirmation_yes") | {"slots": {"answer": True}}
    if lower in {"no", "nope", "nah", "don't", "dont"}:
        return empty_result(route="followup", intent="confirmation", domain="conversation", confidence=0.96, reason="pending_confirmation_no") | {"slots": {"answer": False}}
    return empty_result(route="followup", intent="workflow_answer", domain="conversation", confidence=0.84, reason="pending_followup_answer") | {"slots": {"answer": value}}


def pre_route(text: str, context: dict | None = None) -> dict[str, Any] | None:
    q = normalize_immediate_command(text)
    ctx = context or {}
    if not q:
        return empty_result(route="clarify", intent="unknown", domain="unknown", confidence=1.0, reason="empty_input")
    if q in STOP_PHRASES:
        return empty_result(route="interrupt", intent="stop_speaking", domain="system", confidence=1.0, reason="stop_phrase")
    if q in CANCEL_PHRASES:
        return empty_result(route="cancel", intent="cancel", domain="system", confidence=1.0, reason="cancel_phrase")
    if q in SLEEP_PHRASES:
        return empty_result(route="sleep", intent="sleep", domain="system", confidence=1.0, reason="sleep_phrase")
    if q in WAKE_PHRASES:
        return empty_result(route="wake", intent="wake", domain="system", confidence=1.0, reason="wake_phrase")

    pending = ctx.get("pending_followup") or ctx.get("pending_clarification") or {}
    if pending:
        followup_type = str(pending.get("followup_type") or pending.get("type") or "generic")
        return exact_schema(_pending_followup_result(text, followup_type))

    active_workflow = ctx.get("active_workflow") or {}
    if active_workflow:
        return empty_result(route="workflow", intent="workflow_answer", domain="workflow", confidence=0.92, reason="active_workflow_answer") | {"slots": {"answer": str(text or "").strip()}}

    active_training = ctx.get("active_training") or {}
    if active_training:
        try:
            from engine.train_mode import is_plausible_training_instruction
            if is_plausible_training_instruction(text):
                return empty_result(route="training", intent="training_answer", domain="training", confidence=0.9, reason="active_training_answer") | {"slots": {"answer": str(text or "").strip()}}
        except Exception:
            pass

    try:
        from engine.correction_learner import parse_correction

        parsed = parse_correction(text)
        if parsed.get("parsed"):
            return empty_result(route="training", intent="correction", domain="training", confidence=1.0, reason="correction_phrase") | {"slots": {"trigger": parsed.get("trigger", ""), "action": parsed.get("action", "")}}
    except Exception:
        pass
    return None
