from __future__ import annotations


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def score_intent_confidence(signals: dict) -> float:
    score = float(signals.get("base_confidence", signals.get("groq_intent_confidence", 0.0)) or 0.0)
    if signals.get("learned_rule_match"):
        score = max(score, 0.97)
    if signals.get("pending_clarification") and signals.get("short_answer_plausible"):
        score = max(score, 0.92)
    if signals.get("tool_slots_complete"):
        score += 0.05
    if signals.get("recent_context_match"):
        score += 0.05
    if signals.get("asr_quality") == "low" or signals.get("transcript_rejected"):
        score -= 0.25
    if signals.get("missing_slot"):
        score = min(score, 0.60)
    route = signals.get("route", "")
    score = _clamp(score)
    print(f"[CONFIDENCE] score={score:.2f} route={route}", flush=True)
    return score


def should_clarify(confidence: float, route: str, pending_state: bool = False) -> bool:
    clarify = False
    reason = "none"
    if pending_state and confidence >= 0.5:
        clarify = False
        reason = "pending_state"
    elif confidence < 0.65:
        clarify = True
        reason = "low_confidence"
    elif route in {"", "unknown"}:
        clarify = True
        reason = "unknown_route"
    print(f"[CONFIDENCE] clarify={str(clarify).lower()} reason={reason}", flush=True)
    return clarify


def build_clarification_question(user_text: str, intent: str = "", missing_slot: str = "") -> str:
    if missing_slot == "app_name" or intent == "open_app":
        return "Which app should I open?"
    if missing_slot == "url" or intent == "open_website":
        return "Which website should I open?"
    if missing_slot == "query" or intent == "web_search":
        return "What should I search for?"
    if missing_slot == "file_name":
        return "What should I name the file?"
    if missing_slot == "folder_name":
        return "What should I name the folder?"
    return "I did not catch that. Please say it again in English."
