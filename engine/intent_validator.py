from __future__ import annotations

from typing import Any

from engine.intent_taxonomy import BRAIN_INTENTS, OUTPUT_INTENTS, TOOL_INTENTS, exact_schema


LOW_CONFIDENCE_THRESHOLD = 0.65


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _question_for(intent: str, missing_slots: list[str] | None = None) -> str:
    slot = (missing_slots or [""])[0]
    try:
        from engine.confidence_manager import build_clarification_question

        return build_clarification_question("", intent=intent, missing_slot=slot)
    except Exception:
        if slot == "app_name" or intent == "open_app":
            return "Which app should I open?"
        if slot == "url" or intent == "open_website":
            return "Which website should I open?"
        if slot == "query" or intent == "web_search":
            return "What should I search for?"
        return "I didn't catch that. Please say it again in English."


def _coerce(raw: dict | None) -> dict:
    data = dict(raw or {})
    data["expects_user_reply"] = _as_bool(data.get("expects_user_reply"))
    data["requires_confirmation"] = _as_bool(data.get("requires_confirmation"))
    data["should_call_gemini"] = _as_bool(data.get("should_call_gemini"))
    data["should_call_tool"] = _as_bool(data.get("should_call_tool"))
    if not isinstance(data.get("slots"), dict):
        data["slots"] = {}
    if not isinstance(data.get("missing_slots"), list):
        data["missing_slots"] = []
    return exact_schema(data)


def validate_router_result(raw: dict | None) -> dict:
    result = _coerce(raw)
    route = result["route"]
    intent = result["intent"]

    if intent in OUTPUT_INTENTS and route == "tool":
        route = "output"
    elif intent in TOOL_INTENTS and route in {"", "system"}:
        route = "tool"
    elif intent in BRAIN_INTENTS and route not in {"brain", "clarify"}:
        route = "brain"

    result["route"] = route
    result["should_call_tool"] = route == "tool"
    result["should_call_gemini"] = route == "brain"

    if route in {"tool", "output"}:
        try:
            from engine.tool_registry import get_tool

            known_tool = get_tool(intent) is not None
        except Exception:
            known_tool = False
        if not known_tool:
            result["route"] = "reject"
            result["intent"] = "unknown"
            result["reason"] = "unknown_tool"
            result["should_call_tool"] = False
            result["should_call_gemini"] = False
            result["expects_user_reply"] = False
            return exact_schema(result)

    if route == "tool":
        result["should_call_gemini"] = False
    if route == "brain":
        result["should_call_tool"] = False

    missing = [str(slot) for slot in result.get("missing_slots") or [] if str(slot).strip()]
    if missing or result["confidence"] < LOW_CONFIDENCE_THRESHOLD:
        result["route"] = "clarify"
        result["missing_slots"] = missing
        result["expects_user_reply"] = True
        result["clarification_question"] = result.get("clarification_question") or _question_for(intent, missing)
        result["should_call_gemini"] = False
        result["should_call_tool"] = False
        if not result.get("reason"):
            result["reason"] = "missing_slot" if missing else "low_confidence"

    if result["route"] == "clarify" and not result.get("clarification_question"):
        result["clarification_question"] = _question_for(intent, result.get("missing_slots") or [])

    return exact_schema(result)


def validate_tool_slots(result: dict) -> dict:
    checked = exact_schema(result)
    if checked["route"] not in {"tool", "output"}:
        return checked
    try:
        from engine.tool_manifest_loader import get_manifest_tool

        manifest_tool = get_manifest_tool(checked["intent"])
    except Exception:
        manifest_tool = None
    if manifest_tool:
        risk = str(manifest_tool.get("risk_level") or "none").lower()
        checked["risk_level"] = risk if risk in {"none", "low", "medium", "high", "critical"} else "none"
        if manifest_tool.get("confirmation_required") is True:
            checked["requires_confirmation"] = True
    try:
        from engine.tool_registry import missing_slots

        missing = missing_slots(checked["intent"], checked.get("slots") or {})
    except Exception:
        missing = []
    if missing:
        checked["route"] = "clarify"
        checked["missing_slots"] = missing
        checked["expects_user_reply"] = True
        checked["clarification_question"] = _question_for(checked["intent"], missing)
        checked["should_call_tool"] = False
        checked["should_call_gemini"] = False
        checked["reason"] = "missing_tool_slot"
    return exact_schema(checked)
