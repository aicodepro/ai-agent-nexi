from __future__ import annotations

from typing import Any


def _safe_followup() -> dict[str, Any]:
    try:
        from engine.followup_manager import peek_pending_followup

        pending = peek_pending_followup()
        if pending:
            return {
                "followup_type": pending.get("followup_type", "generic"),
                "source": pending.get("source", ""),
                "question_preview": str(pending.get("question", ""))[:120],
            }
    except Exception:
        pass
    return {}


def _safe_clarification() -> dict[str, Any]:
    try:
        from engine.clarification_manager import has_pending_clarification

        if has_pending_clarification():
            pending = _safe_followup()
            return pending or {"followup_type": "generic"}
    except Exception:
        pass
    return {}


def _safe_workflow() -> dict[str, Any]:
    try:
        from engine.workflow_state import get_workflow

        wf = get_workflow() or {}
        if wf:
            return {"name": wf.get("name", ""), "step": wf.get("step", ""), "slot_keys": sorted((wf.get("slots") or {}).keys())}
    except Exception:
        pass
    return {}


def _safe_training() -> dict[str, Any]:
    active: dict[str, Any] = {}
    try:
        from engine.train_mode import is_training_mode

        if is_training_mode():
            active["mode"] = "basic"
    except Exception:
        pass
    try:
        from engine.need_training_manager import get_active_need

        need = get_active_need()
        if need:
            active["need"] = need
    except Exception:
        pass
    try:
        from engine.deep_training_engine import get_active_ultra_need

        ultra = get_active_ultra_need()
        if ultra:
            active["ultra_need"] = ultra
    except Exception:
        pass
    return active


def _safe_output_context() -> dict[str, Any]:
    try:
        from engine.output_actions import get_latest_output

        latest = get_latest_output()
        if latest.get("content"):
            return {
                "available": True,
                "title": str(latest.get("title", ""))[:80],
                "content_type": str(latest.get("content_type", "text"))[:40],
                "summary_preview": str(latest.get("summary", ""))[:160],
            }
    except Exception:
        pass
    return {"available": False}


def _safe_recent_turns(limit: int = 4) -> list[dict[str, Any]]:
    try:
        from engine.conversation_context import get_recent_turns

        turns = []
        for turn in get_recent_turns(limit):
            turns.append({
                "role": turn.get("role", ""),
                "route": turn.get("route", ""),
                "intent": turn.get("intent", ""),
                "text_preview": str(turn.get("text", ""))[:160],
            })
        return turns
    except Exception:
        return []


def _safe_session_memory() -> str:
    try:
        from engine.memory.session_memory import get_session_memory

        return get_session_memory().to_context_string(limit=6, max_chars=900)
    except Exception:
        return ""


def _safe_episodic_memory(text: str) -> list[dict[str, Any]]:
    try:
        from engine.memory.episodic_memory import get_episodic_memory

        episodes = get_episodic_memory().recall_similar(text, n=3)
        return [
            {
                "user_input_preview": episode.user_input[:120],
                "intent": episode.intent[:80],
                "route": episode.route[:80],
                "outcome": episode.outcome[:40],
            }
            for episode in episodes
        ]
    except Exception:
        return []


def _safe_semantic_memory(text: str) -> str:
    try:
        from engine.memory.semantic_memory import get_semantic_memory

        memory = get_semantic_memory()
        context = memory.build_context(text, limit=4, max_chars=700)
        if not context:
            context = memory.build_context("", limit=2, max_chars=300)
        return context
    except Exception:
        return ""


def _safe_reflection_memory(text: str) -> str:
    try:
        from engine.reflection_memory import ReflectionMemory

        return ReflectionMemory.get_context(text, max_lessons=2)
    except Exception:
        return ""


def _safe_memory_context(text: str) -> dict[str, Any]:
    session = _safe_session_memory()
    episodic = _safe_episodic_memory(text)
    semantic = _safe_semantic_memory(text)
    reflection = _safe_reflection_memory(text)
    return {
        "session": session,
        "episodic": episodic,
        "semantic": semantic,
        "reflection": reflection,
        "available": bool(session or episodic or semantic or reflection),
    }


def build_intent_context(text: str, source: str = "ui") -> dict[str, Any]:
    context = {
        "source": str(source or "ui")[:40],
        "text_preview": str(text or "")[:160],
        "pending_clarification": _safe_clarification(),
        "pending_followup": _safe_followup(),
        "active_workflow": _safe_workflow(),
        "active_training": _safe_training(),
        "latest_output": _safe_output_context(),
        "recent_turns": _safe_recent_turns(),
        "memory_context": _safe_memory_context(text),
    }
    print(
        "[INTENT_CONTEXT] built "
        f"pending={str(bool(context['pending_followup'] or context['pending_clarification'])).lower()} "
        f"workflow={str(bool(context['active_workflow'])).lower()} "
        f"training={str(bool(context['active_training'])).lower()} "
        f"memory={str(bool(context['memory_context']['available'])).lower()}",
        flush=True,
    )
    return context
