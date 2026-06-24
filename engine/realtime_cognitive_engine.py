from __future__ import annotations

import re
from typing import Any


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).strip()


def _preview(text: str) -> str:
    return _normalize(text)[:80].replace('"', "'")


def _context(source: str, metadata: dict | None = None) -> dict[str, Any]:
    context: dict[str, Any] = {"source": source, "metadata": metadata or {}}
    try:
        from engine.conversation_context import get_current_task_context, get_recent_turns, get_working_memory
        context["recent_turns"] = get_recent_turns(10)
        context["working_memory"] = get_working_memory(limit=10, max_chars=2200)
        context["current_task"] = get_current_task_context()
    except Exception:
        context["recent_turns"] = []
        context["working_memory"] = ""
        context["current_task"] = {}
    try:
        from engine.followup_manager import peek_pending_followup
        context["pending_followup"] = peek_pending_followup()
    except Exception:
        context["pending_followup"] = {}
    try:
        from engine.clarification_manager import has_pending_clarification
        context["pending_clarification"] = has_pending_clarification()
    except Exception:
        context["pending_clarification"] = False
    try:
        from engine.user_model import get_user_model_context
        context["user_model"] = get_user_model_context()
    except Exception:
        context["user_model"] = ""
    try:
        from engine.need_training_manager import get_active_need
        context["active_training_need"] = get_active_need()
    except Exception:
        context["active_training_need"] = ""
    try:
        from engine.deep_training_engine import get_active_ultra_need
        context["active_ultra_need"] = get_active_ultra_need()
    except Exception:
        context["active_ultra_need"] = ""
    return context


def analyze_input(user_text: str, source: str = "typed", metadata: dict | None = None) -> dict:
    normalized = _normalize(user_text)
    print(f"[COGNITIVE] input=\"{_preview(normalized)}\"", flush=True)
    context = _context(source, metadata)
    strategy = decide_next_action(normalized, context)
    strategy["user_text"] = user_text or ""
    strategy["normalized_text"] = normalized
    strategy["source"] = source or "typed"
    print(f"[COGNITIVE] hypotheses={len(strategy.get('intent_hypotheses', []))}", flush=True)
    print(
        f"[COGNITIVE] chosen route={strategy.get('chosen_route')} intent={strategy.get('chosen_intent')} confidence={float(strategy.get('confidence', 0.0)):.2f}",
        flush=True,
    )
    print(f"[COGNITIVE] learned_rules_used={len(strategy.get('learned_rules_used', []))}", flush=True)
    print(f"[COGNITIVE] need={strategy.get('detected_need') or 'none'} profile_used={str(bool(strategy.get('need_profile_used'))).lower()}", flush=True)
    print(f"[COGNITIVE] clarification_required={str(bool(strategy.get('needs_clarification'))).lower()}", flush=True)
    meta_queries = {"what did you understand", "why did you do that", "what have you learned", "show training rules", "show training profiles", "cognitive status"}
    if normalized.lower().rstrip(".?!") not in meta_queries:
        try:
            from engine.cognitive_context import set_last_strategy
            set_last_strategy(strategy)
        except Exception:
            pass
    return strategy


def generate_intent_hypotheses(user_text: str, context: dict) -> list[dict]:
    q = _normalize(user_text)
    low = q.lower().rstrip(".?!")
    hypotheses: list[dict[str, Any]] = []
    try:
        from engine.training_rules import apply_training_rule, match_training_rules, parse_training_instruction
        parsed = parse_training_instruction(q)
        if parsed.get("parsed"):
            hypotheses.append({"intent": "learn_rule", "route": "training", "confidence": 1.0, "reason": "training instruction", "slots": {}})
        for rule in match_training_rules(q, context):
            applied = apply_training_rule(rule, {"confidence": 0.0, "slots": {}})
            hypotheses.append({
                "intent": applied.get("chosen_intent", "learned_rule_match"),
                "route": applied.get("chosen_route", "tool"),
                "confidence": applied.get("confidence", 0.97),
                "reason": applied.get("reason", "learned rule matched"),
                "slots": applied.get("slots", {}),
                "learned_rules_used": applied.get("learned_rules_used", []),
            })
    except Exception:
        pass
    if low.startswith(("train nexi for ", "train nexi deeply for ", "start ultra training for ")):
        hypotheses.append({"intent": "train_need_profile", "route": "training", "confidence": 1.0, "reason": "need training command", "slots": {}})
    if low.startswith(("create training dataset", "simulate training", "run training evaluation", "show training score", "show weak areas", "show training curriculum")):
        hypotheses.append({"intent": "deep_training_command", "route": "training", "confidence": 1.0, "reason": "ultra training command", "slots": {}})
    pending = context.get("pending_followup") or {}
    if pending:
        ftype = pending.get("followup_type", "")
        if ftype == "open_app":
            if low in {"youtube", "gmail", "github"} or "." in low:
                hypotheses.append({"intent": "open_website", "route": "tool", "confidence": 0.98, "reason": "pending open target website", "slots": {"url": "youtube.com" if low == "youtube" else low}})
            else:
                hypotheses.append({"intent": "open_app", "route": "tool", "confidence": 0.96, "reason": "pending open target app", "slots": {"app_name": q}})
        elif ftype == "web_search":
            hypotheses.append({"intent": "web_search", "route": "tool", "confidence": 0.96, "reason": "pending search query", "slots": {"query": q}})
    try:
        from engine.tool_usage_intelligence import resolve_tool_alias
        alias = resolve_tool_alias(q, context)
        if alias.get("handled"):
            hypotheses.append({"intent": alias["name"], "route": "tool", "confidence": alias.get("confidence", 0.95), "reason": alias.get("reason", "tool alias"), "slots": alias.get("slots", {}), "learned_rules_used": alias.get("learned_rules_used", [])})
    except Exception:
        pass
    try:
        from engine.tool_registry import select_tool
        selected = select_tool(q)
        if selected.get("handled"):
            hypotheses.append({"intent": selected.get("name"), "route": "tool", "confidence": selected.get("confidence", 0.90), "reason": "tool registry", "slots": selected.get("slots", {})})
    except Exception:
        pass
    if low in {"what have you learned", "show training rules", "show training profiles", "cognitive status", "why did you do that", "what did you understand"}:
        hypotheses.append({"intent": low.replace(" ", "_"), "route": "memory", "confidence": 1.0, "reason": "cognitive command", "slots": {}})
    try:
        from engine.intent_router import route_intent
        routed = route_intent(q)
        if routed.route == "brain":
            hypotheses.append({"intent": routed.intent, "route": "brain", "confidence": routed.confidence, "reason": routed.reason, "slots": {}})
        elif routed.route == "local_action":
            hypotheses.append({"intent": routed.intent, "route": "tool", "confidence": routed.confidence, "reason": routed.reason, "slots": {}})
    except Exception:
        pass
    if not hypotheses:
        hypotheses.append({"intent": "unknown", "route": "clarify", "confidence": 0.0, "reason": "no confident hypothesis", "slots": {}})
    return hypotheses


def choose_best_route(hypotheses: list[dict], context: dict) -> dict:
    best = max(hypotheses or [], key=lambda item: float(item.get("confidence", 0.0) or 0.0), default={"intent": "unknown", "route": "clarify", "confidence": 0.0, "reason": "empty hypotheses", "slots": {}})
    try:
        from engine.confidence_manager import build_clarification_question, score_intent_confidence, should_clarify
        confidence = score_intent_confidence({
            "base_confidence": best.get("confidence", 0.0),
            "route": best.get("route", ""),
            "learned_rule_match": bool(best.get("learned_rules_used")),
            "pending_clarification": bool(context.get("pending_clarification") or context.get("pending_followup")),
            "short_answer_plausible": bool(context.get("pending_followup")),
            "tool_slots_complete": bool(best.get("slots")) or best.get("route") != "tool",
        })
        clarify = should_clarify(confidence, best.get("route", ""), bool(context.get("pending_followup")))
        question = build_clarification_question("", best.get("intent", "")) if clarify else ""
    except Exception:
        confidence = float(best.get("confidence", 0.0) or 0.0)
        clarify = confidence < 0.65
        question = "I did not catch that. Please say it again in English." if clarify else ""
    route = "clarify" if clarify else best.get("route", "clarify")
    return {
        "chosen_route": route,
        "chosen_intent": "clarify" if clarify else best.get("intent", "unknown"),
        "confidence": confidence,
        "needs_clarification": clarify,
        "clarification_question": question,
        "learned_rules_used": list(best.get("learned_rules_used") or []),
        "risk_level": "low" if route == "tool" else "none",
        "reason": best.get("reason", ""),
        "slots": dict(best.get("slots") or {}),
    }


def decide_next_action(user_text: str, context: dict) -> dict:
    hypotheses = generate_intent_hypotheses(user_text, context)
    decision = choose_best_route(hypotheses, context)
    try:
        from engine.user_intent_profile import detect_need
        detected = detect_need(user_text, context)
        if detected.get("need"):
            decision["detected_need"] = detected.get("need")
            decision["detected_need_confidence"] = detected.get("confidence", 0.0)
    except Exception:
        pass
    try:
        from engine.need_training_manager import apply_need_profile, get_active_need, match_need_profile
        active_need = get_active_need()
        profiles = match_need_profile(user_text, context)
        if active_need:
            decision["active_training_need"] = active_need
            decision["training_level"] = "medium"
        decision = apply_need_profile(decision, profiles)
    except Exception:
        decision.setdefault("need_profile_used", False)
    try:
        from engine.deep_training_engine import get_active_ultra_need
        active_ultra_need = get_active_ultra_need()
        if active_ultra_need:
            decision["active_ultra_need"] = active_ultra_need
            decision["training_level"] = "ultra"
    except Exception:
        pass
    try:
        from engine.training_policy import apply_tool_policy, match_tool_policies
        policies = match_tool_policies(decision.get("detected_need", ""))
        if policies:
            decision = apply_tool_policy(decision, policies)
    except Exception:
        pass
    try:
        from engine.user_model import apply_user_model_to_strategy
        decision = apply_user_model_to_strategy(decision)
    except Exception:
        pass
    decision["intent_hypotheses"] = hypotheses
    decision["likely_goal"] = decision.get("chosen_intent", "unknown")
    return decision
