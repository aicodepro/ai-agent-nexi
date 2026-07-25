from __future__ import annotations

from typing import Any


_last_explanation: dict[str, Any] = {}


def record_intent_decision(
    result: dict[str, Any],
    *,
    selected_tool: str = "",
    selected_rule: str = "",
    missing_slot: str = "",
) -> None:
    global _last_explanation
    _last_explanation = {
        "route": result.get("route", "unknown"),
        "intent": result.get("intent", "unknown"),
        "confidence": float(result.get("confidence", 0.0) or 0.0),
        "selected_tool": selected_tool or (result.get("intent", "") if result.get("route") == "tool" else ""),
        "selected_rule": selected_rule,
        "missing_slot": missing_slot or ((result.get("missing_slots") or [""])[0] if isinstance(result.get("missing_slots"), list) and result.get("missing_slots") else ""),
        "reason": str(result.get("reason", ""))[:160],
    }


def get_last_decision() -> dict[str, Any]:
    """The route Nexi ACTUALLY dispatched, as recorded by the live router.

    This is the single source of truth for any self-explanation. The parallel
    strategy in engine.realtime_cognitive_engine is only a hypothesis and must
    never be reported to the user as the decision that was made.
    """
    return dict(_last_explanation)


def explain_intent(result: dict[str, Any] | None = None, *, selected_tool: str = "", selected_rule: str = "", missing_slot: str = "") -> str:
    data = dict(result or _last_explanation or {})
    if result:
        record_intent_decision(data, selected_tool=selected_tool, selected_rule=selected_rule, missing_slot=missing_slot)
        data = dict(_last_explanation)
    route = data.get("route", "unknown")
    intent = data.get("intent", "unknown")
    confidence = float(data.get("confidence", 0.0) or 0.0)
    parts = [f"I routed that as {route}/{intent} with confidence {confidence:.2f}."]
    tool = data.get("selected_tool")
    rule = data.get("selected_rule")
    slot = data.get("missing_slot")
    if tool:
        parts.append(f"Selected tool: {tool}.")
    if rule:
        parts.append("Selected rule: correction rule.")
    if slot:
        parts.append(f"Missing slot: {slot}.")
    if data.get("reason"):
        parts.append(f"Reason: {data['reason']}.")
    return " ".join(parts)


def explain_last_intent() -> str:
    if not _last_explanation:
        return "I have not routed a Phase 4 intent yet."
    return explain_intent()
