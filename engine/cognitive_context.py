from __future__ import annotations

from typing import Any


_last_strategy: dict[str, Any] = {}
_last_reflection: dict[str, Any] = {}


def set_last_strategy(strategy: dict[str, Any] | None) -> None:
    global _last_strategy
    _last_strategy = dict(strategy or {})


def get_last_strategy() -> dict[str, Any]:
    return dict(_last_strategy)


def set_last_reflection(reflection: dict[str, Any] | None) -> None:
    global _last_reflection
    _last_reflection = dict(reflection or {})


def get_last_reflection() -> dict[str, Any]:
    return dict(_last_reflection)


def describe_last_understanding() -> str:
    strategy = get_last_strategy()
    if not strategy:
        return "I do not have a recent command to summarize yet."
    text = strategy.get("normalized_text") or strategy.get("user_text") or "that command"
    intent = strategy.get("chosen_intent") or "unknown"
    route = strategy.get("chosen_route") or "clarify"
    confidence = strategy.get("confidence", 0.0)
    reason = strategy.get("reason") or "I selected the safest available route."
    rules = strategy.get("learned_rules_used") or []
    if strategy.get("need_profile_used"):
        need = strategy.get("detected_need") or "that"
        return f"I understood '{text}' as {intent} via {route} using your {need} training profile."
    if rules:
        return f"I understood '{text}' as {intent} via {route} because a learned rule matched."
    return f"I understood '{text}' as {intent} via {route} with confidence {confidence:.2f}. {reason}"


def explain_last_route() -> str:
    strategy = get_last_strategy()
    if not strategy:
        return "I do not have a recent route decision to explain yet."
    intent = strategy.get("chosen_intent") or "unknown"
    route = strategy.get("chosen_route") or "clarify"
    reason = strategy.get("reason") or "that was the highest-confidence safe route."
    rules = strategy.get("learned_rules_used") or []
    if strategy.get("need_profile_used"):
        from engine.training_explainer import explain_strategy
        return explain_strategy(strategy)
    if rules:
        return f"I routed it as {intent} through {route} because your learned rule matched this command."
    return f"I routed it as {intent} through {route} because {reason}"


def cognitive_status() -> str:
    try:
        from engine.conversation_context import get_recent_turns
        recent_turns = len(get_recent_turns(20))
    except Exception:
        recent_turns = 0
    try:
        from engine.training_rules import list_training_rules
        training_rules = len([r for r in list_training_rules() if r.get("enabled", True)])
    except Exception:
        training_rules = 0
    try:
        from engine.need_training_manager import get_active_need, list_need_profiles
        active_need = get_active_need()
        training_profiles = len([p for p in list_need_profiles() if p.get("enabled", True)])
    except Exception:
        active_need = ""
        training_profiles = 0
    try:
        from engine.training_evaluator import get_training_score
        training_score = get_training_score()
    except Exception:
        training_score = {"evaluation_count": 0, "overall_score": 0.0}
    try:
        from engine.user_model import count_preferences
        preferences = count_preferences()
    except Exception:
        preferences = 0
    try:
        from engine.tool_usage_intelligence import count_tool_failure_lessons
        tool_failures = count_tool_failure_lessons()
    except Exception:
        tool_failures = 0
    return (
        "Cognitive core active. "
        f"Recent turns: {recent_turns}. "
        f"Training rules: {training_rules}. "
        f"Training profiles: {training_profiles}. "
        f"Training evaluations: {training_score.get('evaluation_count', 0)}. "
        f"Preferences: {preferences}. "
        f"Tool failure lessons: {tool_failures}. "
        f"Mode: {'training ' + active_need if active_need else 'adaptive routing'}."
    )
