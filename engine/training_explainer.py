from __future__ import annotations


def explain_strategy(strategy: dict | None = None) -> str:
    if strategy is None:
        try:
            from engine.cognitive_context import get_last_strategy
            strategy = get_last_strategy()
        except Exception:
            strategy = {}
    if not strategy:
        return "I do not have a recent training decision to explain yet."
    need = strategy.get("detected_need") or "none"
    confidence = float(strategy.get("confidence", 0.0) or 0.0)
    route = strategy.get("chosen_route") or strategy.get("route") or "unknown"
    profile_used = bool(strategy.get("need_profile_used"))
    rules = strategy.get("profile_rules_used") or strategy.get("training_rules_used") or strategy.get("learned_rules_used") or []
    if profile_used:
        rule_text = ", ".join(str(rule) for rule in rules[:3]) or "profile defaults"
        return f"I detected {need} mode with {confidence:.2f} confidence. I applied your {need} profile: {rule_text}. I used {route} because that matched the task type."
    return f"I used {route} with confidence {confidence:.2f}. Detected need: {need}."


def what_training_affected_this(strategy: dict | None = None) -> str:
    return explain_strategy(strategy)


def safe_understanding_summary(strategy: dict | None = None) -> str:
    if strategy is None:
        try:
            from engine.cognitive_context import get_last_strategy
            strategy = get_last_strategy()
        except Exception:
            strategy = {}
    if not strategy:
        return "I do not have a recent command to summarize yet."
    need = strategy.get("detected_need") or "none"
    intent = strategy.get("chosen_intent") or "unknown"
    route = strategy.get("chosen_route") or "unknown"
    return f"I understood the task as {intent}, route {route}, need {need}."
