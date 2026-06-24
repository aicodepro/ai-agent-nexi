from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.memory_safety import is_safe_to_store, redact_sensitive


REFLECTION_PATH = Path(__file__).resolve().parents[1] / "data" / "memory" / "reflection_events.json"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean(text: str, limit: int = 500) -> str:
    value = re.sub(r"\s+", " ", redact_sensitive(str(text or ""))).strip()
    safe, _reason = is_safe_to_store(value)
    return value[:limit] if safe else ""


def _load() -> list[dict[str, Any]]:
    try:
        if REFLECTION_PATH.exists():
            data = json.loads(REFLECTION_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
    except Exception:
        pass
    return []


def _save(events: list[dict[str, Any]]) -> None:
    REFLECTION_PATH.parent.mkdir(parents=True, exist_ok=True)
    REFLECTION_PATH.write_text(json.dumps(events[-500:], indent=2), encoding="utf-8")


def extract_learning_events(user_text: str, result: dict, assistant_text: str) -> list[dict]:
    events = []
    user = _clean(user_text)
    assistant = _clean(assistant_text)
    if not user:
        print("[REFLECTION] skipped reason=unsafe_or_empty", flush=True)
        return []
    q = user.lower()
    if q.startswith(("no,", "actually", "this is wrong", "that's wrong", "that is wrong", "correct this")) or " next time " in q:
        events.append({"type": "user_correction", "text": user})
    if any(phrase in q for phrase in ("keep answers short", "short answers", "use the workspace")):
        events.append({"type": "style_preference", "text": user})
    tool = result.get("tool") if isinstance(result, dict) else ""
    if tool:
        if result.get("success") is True:
            events.append({"type": "successful_tool_route", "tool": tool, "text": assistant or user})
        else:
            events.append({"type": "failed_tool_route", "tool": tool, "text": str(result.get("message") or "unverified")[:200]})
    if isinstance(result, dict) and float(result.get("confidence", 1.0) or 1.0) < 0.65:
        events.append({"type": "low_confidence_intent", "text": user})
    return events


def store_reflection_events(events: list[dict]) -> dict:
    safe_events = []
    for event in events or []:
        text = _clean(event.get("text", ""), 400)
        if event.get("text") and not text:
            continue
        safe_event = dict(event)
        safe_event["text"] = text
        safe_event["created_at"] = _now()
        safe_events.append(safe_event)
        if safe_event.get("type") == "failed_tool_route":
            try:
                from engine.adaptive_memory import record_tool_failure
                record_tool_failure(str(safe_event.get("tool") or "tool"), text or "unverified")
            except Exception:
                pass
            try:
                from engine.reflection_memory import ReflectionMemory
                tool_name = str(safe_event.get("tool") or "tool")
                ReflectionMemory.store_lesson(
                    failure=f"{tool_name}: {text or 'unverified failure'}",
                    lesson=f"{tool_name} failed or could not be verified.",
                    next_action="Verify the tool result before reporting success; use a safer fallback if available.",
                    context=f"event=failed_tool_route tool={tool_name}",
                    tool_name=tool_name,
                )
            except Exception:
                pass
        if safe_event.get("type") in {"style_preference", "user_correction"}:
            try:
                from engine.user_model import infer_user_preference, update_user_model
                pref = infer_user_preference(text)
                if pref:
                    update_user_model(pref)
            except Exception:
                pass
            if safe_event.get("type") == "user_correction":
                try:
                    from engine.reflection_memory import ReflectionMemory
                    ReflectionMemory.store_lesson(
                        failure=f"User corrected prior behavior: {text}",
                        lesson="User correction should override prior routing for similar phrasing.",
                        next_action="Apply the correction before using default routing.",
                        context="event=user_correction",
                    )
                except Exception:
                    pass
        if safe_event.get("type") == "low_confidence_intent":
            try:
                from engine.reflection_memory import ReflectionMemory
                ReflectionMemory.store_lesson(
                    failure=f"Low confidence intent: {text}",
                    lesson="Low-confidence intent routing should not take risky actions silently.",
                    next_action="Ask a concise clarification or choose a safe fallback.",
                    context="event=low_confidence_intent",
                )
            except Exception:
                pass
    if not safe_events:
        print("[REFLECTION] stored=0", flush=True)
        return {"stored": 0}
    existing = _load()
    existing.extend(safe_events)
    _save(existing)
    print(f"[REFLECTION] stored={len(safe_events)}", flush=True)
    return {"stored": len(safe_events)}


def reflect_after_turn(user_text: str, strategy: dict, result: dict, assistant_text: str) -> dict:
    tool_result = dict(result or {})
    if strategy and "confidence" not in tool_result:
        tool_result["confidence"] = strategy.get("confidence", 1.0)
    events = extract_learning_events(user_text, tool_result, assistant_text)
    print(f"[REFLECTION] events={len(events)}", flush=True)
    stored = store_reflection_events(events)
    reflection = {"events": events, **stored}
    try:
        from engine.cognitive_context import set_last_reflection
        set_last_reflection(reflection)
    except Exception:
        pass
    return reflection
