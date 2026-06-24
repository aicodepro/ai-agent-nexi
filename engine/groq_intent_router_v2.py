from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from engine.intent_taxonomy import BRAIN_INTENTS, OUTPUT_INTENTS, empty_result, exact_schema


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().rstrip(".?!").split())


def _load_prompt() -> str:
    try:
        from engine.prompt_loader import load_prompt_file
        return load_prompt_file("nexi_groq_intent_system_prompt.txt", "You are Nexi Intent Router v2. Return strict JSON only.")
    except Exception:
        return "You are Nexi Intent Router v2. Return strict JSON only."


def _json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        value = match.group(0)
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


# ── Rate limiter ────────────────────────────────────────────────────────────
_last_llm_call: float = 0.0

def _llm_rate_limited() -> bool:
    global _last_llm_call
    cooldown = float(os.getenv("GROQ_INTENT_COOLDOWN_SECONDS", "0.5"))
    now = time.time()
    if now - _last_llm_call < cooldown:
        return True
    _last_llm_call = now
    return False


# ── Deterministic fallback ──────────────────────────────────────────────────
def _qa_like(q: str) -> bool:
    prefixes = (
        "what is ", "what are ", "what's ", "whats ", "who is ", "who was ",
        "how to ", "how do ", "how does ", "why ", "why is ", "why does ",
        "explain ", "tell me about ", "describe ", "summarize ", "define ",
        "write ", "translate ", "calculate ", "compute ", "solve ",
    )
    return any(q.startswith(prefix) for prefix in prefixes)


def _react_like(q: str) -> bool:
    if any(phrase in q for phrase in (" and then ", " then ", " after that ")):
        verbs = sum(1 for token in ("find", "search", "open", "save", "create", "copy", "remember", "recall", "show") if token in q)
        return verbs >= 2
    return any(
        phrase in q
        for phrase in (
            "save my last note",
            "find my note",
            "recall my note",
            "search my memory and",
            "find in memory and",
        )
    )


# Zero-slot tools that can be matched by a simple alias/keyword in any position.
_SIMPLE_ALIAS_TOOLS = {
    "tell_time": ("system", ("what time is it", "what's the time", "whats the time", "current time", "time now", "tell me the time", "the time")),
    "tell_joke": ("conversation", ("tell me a joke", "tell a joke", "make me laugh", "crack a joke", "say a joke")),
    "internet_speed_test": ("system", ("internet speed", "speed test", "check internet speed", "check my internet", "network speed", "test internet")),
    "get_active_window": ("system", ("which app is active", "what app is active", "active window", "what app am i using", "current app", "what app is open", "what is the active app")),
    "what_am_i_working_on": ("system", ("what am i working on", "what am i doing", "what am i up to")),
    "get_system_state": ("system", ("system status", "pc status", "system state", "how is my pc", "computer status", "resource usage", "whats my system status", "what is my system status", "how is my computer")),
    "why_is_pc_slow": ("system", ("why is my pc slow", "why is my computer slow", "what is slowing my pc", "whats using my cpu", "what is using memory", "why is it lagging", "why is my pc lagging", "whats slowing my computer", "what is slowing my computer", "what's slowing my computer", "what's slowing my pc", "my pc is slow", "my computer is slow", "pc is slow", "computer is slow")),
    "media_pause": ("desktop", ("pause the video", "pause video", "pause music", "pause media", "stop playing")),
    "media_resume": ("desktop", ("resume the video", "resume video", "play again", "resume media", "continue playing")),
    "media_mute": ("desktop", ("mute the video", "mute sound", "mute media")),
    "browser_new_tab": ("browser", ("open a new tab", "open new tab", "new tab")),
    "browser_close_tab": ("browser", ("close the tab", "close current tab", "close this tab", "close tab")),
    "browser_refresh": ("browser", ("refresh the page", "reload the page", "refresh page", "reload page")),
    "browser_back": ("browser", ("go back",)),
    "browser_forward": ("browser", ("go forward",)),
    "browser_history": ("browser", ("show my history", "open history", "browser history")),
    "browser_fullscreen": ("browser", ("go fullscreen", "toggle fullscreen", "full screen")),
}


def _alias_tool_match(q: str) -> dict[str, Any] | None:
    """Match zero-slot tools by alias phrase. Longest phrase wins to avoid 'pause' eating 'pause and explain'."""
    best_intent = ""
    best_domain = ""
    best_len = 0
    for intent, (domain, phrases) in _SIMPLE_ALIAS_TOOLS.items():
        for phrase in phrases:
            if (q == phrase or f" {phrase} " in f" {q} " or q.startswith(phrase + " ") or q.endswith(" " + phrase)) and len(phrase) > best_len:
                best_intent, best_domain, best_len = intent, domain, len(phrase)
    if not best_intent:
        return None
    # Weather handled separately because it carries an optional location slot.
    return empty_result(route="tool", intent=best_intent, domain=best_domain, confidence=0.93, reason=f"alias_{best_intent}")


def _youtube_match(q: str, text: str) -> dict[str, Any] | None:
    """Route YouTube open vs play/search. Runs before generic open/search rules."""
    is_yt = ("youtube" in q) or (" yt" in f" {q}") or q.startswith("yt ") or ("yutub" in q) or ("you tube" in q)
    if not is_yt:
        return None
    if q in {"open youtube", "youtube kholo", "open yt", "yutub kholo", "you tube kholo", "go to youtube", "launch youtube", "start youtube"}:
        from engine.website_resolver import resolve_website
        return exact_schema(empty_result(route="tool", intent="open_website", domain="web", confidence=0.95, reason="open_youtube") | {"slots": {"url": resolve_website("youtube").get("url", "youtube.com")}})
    yt_query = re.sub(r"\b(on\s+)?(youtube|yt|yutub|you tube)\b", " ", str(text or ""), flags=re.I)
    yt_query = re.sub(r"\b(play|search|for|pe|karo|dhoondo|khojo|kholo|open)\b", " ", yt_query, flags=re.I)
    yt_query = " ".join(yt_query.split()).strip(" .?!")
    if yt_query:
        return exact_schema(empty_result(route="tool", intent="search_youtube", domain="web", confidence=0.92, reason="youtube_search") | {"slots": {"query": yt_query}})
    return exact_schema(empty_result(route="clarify", intent="search_youtube", domain="web", confidence=0.9, reason="missing_yt_query", clarification_question="What should I play on YouTube?") | {"missing_slots": ["query"]})


def _weather_match(q: str, text: str) -> dict[str, Any] | None:
    if not any(w in q for w in ("weather", "temperature", "how hot", "how cold")):
        return None
    location = ""
    m = re.search(r"(?:weather|temperature)\s+(?:in|at|for)\s+(.+)", q)
    if m:
        location = m.group(1).strip(" .?!")
    slots = {"location": location} if location else {}
    return exact_schema(empty_result(route="tool", intent="weather_lookup", domain="web", confidence=0.9, reason="weather_lookup") | {"slots": slots})


def _deterministic_router(text: str, context: dict | None = None) -> dict[str, Any]:
    q = _norm(text)
    if not q:
        return empty_result(route="clarify", intent="unknown", confidence=1.0, reason="empty_input")

    try:
        from engine.smart_followup_engine import resolve_followup
        followup = resolve_followup(text, context)
        if followup:
            return followup
    except Exception:
        pass

    if q in {"hello", "hi", "hey", "hello there", "hi there"}:
        return empty_result(route="system", intent="greeting", domain="conversation", confidence=1.0, reason="greeting")
    if q in {"who are you", "what is your name", "what's your name", "introduce yourself"}:
        return empty_result(route="system", intent="identity", domain="conversation", confidence=1.0, reason="identity")
    if q in {"repeat", "repeat that", "say that again", "can you repeat that"}:
        return empty_result(route="system", intent="repeat_last", domain="conversation", confidence=1.0, reason="repeat")
    if q in {"what did you understand", "why did you do that", "what rule did you use", "what tool did you choose"}:
        return empty_result(route="system", intent="what_did_you_understand" if q.startswith("what") else "why_did_you_do_that", domain="system", confidence=1.0, reason="intent_explain")

    # ── Early guards: YouTube + browser-tab must beat generic open/search ────
    _yt = _youtube_match(q, str(text or ""))
    if _yt:
        return _yt
    if q in {"open a new tab", "open new tab", "new tab"}:
        return empty_result(route="tool", intent="browser_new_tab", domain="browser", confidence=0.95, reason="browser_new_tab")

    if q in {"open", "launch", "start"}:
        return exact_schema(empty_result(route="clarify", intent="open_app", domain="desktop", confidence=0.92, reason="missing_app", clarification_question="Which app should I open?") | {"missing_slots": ["app_name"]})
    if q.startswith(("open ", "launch ")):
        target = re.sub(r"^(open|launch)\s+", "", str(text or "").strip(), flags=re.I).strip()
        from engine.website_resolver import looks_like_website, resolve_website
        if looks_like_website(target):
            return exact_schema(empty_result(route="tool", intent="open_website", domain="web", confidence=0.95, reason="open_website") | {"slots": {"url": resolve_website(target).get("url", target)}})
        from engine.app_resolver import resolve_app_name
        return exact_schema(empty_result(route="tool", intent="open_app", domain="desktop", confidence=0.95, reason="open_app") | {"slots": {"app_name": resolve_app_name(target).get("app_name", target)}})

    if q in {"search", "google", "search web", "search the web"}:
        return exact_schema(empty_result(route="clarify", intent="web_search", domain="web", confidence=0.92, reason="missing_query", clarification_question="What should I search for?") | {"missing_slots": ["query"]})
    if q.startswith(("search ", "google ")):
        query = re.sub(r"^(search|google)\s+", "", str(text or "").strip(), flags=re.I).strip()
        return exact_schema(empty_result(route="tool", intent="web_search", domain="web", confidence=0.95, reason="web_search") | {"slots": {"query": query}})

    if q.startswith(("remember ", "remember that ")) or q in {"show memory", "what do you remember"}:
        return empty_result(route="memory", intent="remember" if q.startswith("remember") else "recall_memory", domain="memory", confidence=0.94, reason="memory_phrase")

    if q in {"train nexi", "start training", "start training mode", "training mode"}:
        return empty_result(route="training", intent="train_nexi", domain="training", confidence=1.0, reason="training_phrase")
    if q.startswith("train nexi deeply for ") or q.startswith("start ultra training for "):
        return empty_result(route="training", intent="start_ultra_training", domain="training", confidence=1.0, reason="ultra_training_phrase")
    if q.startswith("train nexi for "):
        return empty_result(route="training", intent="train_need_profile", domain="training", confidence=1.0, reason="need_training_phrase")
    if q.startswith(("create training dataset", "simulate training", "run training evaluation", "show training score", "show weak areas", "show training curriculum")):
        return empty_result(route="training", intent="deep_training_command", domain="training", confidence=1.0, reason="deep_training_phrase")
    if q in {"show training rules", "what have you learned", "show training profiles", "show need profiles"}:
        return empty_result(route="memory", intent="show_training_rules" if "rules" in q or "learned" in q else "show_training_profiles", domain="training", confidence=1.0, reason="training_summary")

    if q.startswith(("create folder", "create a folder", "make folder", "new folder")):
        return empty_result(route="workflow", intent="create_folder", domain="workflow", confidence=0.92, reason="folder_workflow")
    if q.startswith(("create file", "create a file", "create text file", "create python file")):
        return empty_result(route="workflow", intent="create_file", domain="workflow", confidence=0.92, reason="file_workflow")

    if _react_like(q):
        return empty_result(route="react", intent="react_multi_step", domain="workflow", confidence=0.88, reason="multi_step_task")

    # ── YouTube play/search handled early via _youtube_match() ───────────────

    # ── Hinglish browser open (chrome/browser kholo) ─────────────────────────
    if q in {"chrome kholo", "browser kholo", "krom kholo", "browzer kholo"}:
        from engine.app_resolver import resolve_app_name
        return exact_schema(empty_result(route="tool", intent="open_app", domain="desktop", confidence=0.95, reason="open_chrome_hi") | {"slots": {"app_name": resolve_app_name("chrome").get("app_name", "chrome")}})
    if q.startswith(("google pe search karo", "google pe dhoondo", "google search karo", "google pe khojo")):
        gq = re.sub(r"^google\s+(pe\s+)?(search karo|dhoondo|khojo|search)\s*", "", q).strip()
        if gq:
            return exact_schema(empty_result(route="tool", intent="web_search", domain="web", confidence=0.93, reason="google_search_hi") | {"slots": {"query": gq}})
        return exact_schema(empty_result(route="clarify", intent="web_search", domain="web", confidence=0.9, reason="missing_query", clarification_question="What should I search for?") | {"missing_slots": ["query"]})

    # ── Simple alias-driven tools (time/joke/weather/media/browser) ──────────
    _weather = _weather_match(q, str(text or ""))
    if _weather:
        return _weather
    _alias_hit = _alias_tool_match(q)
    if _alias_hit:
        return _alias_hit

    if "stop" in q and any(word in q for word in ("camera", "gesture", "eye", "control")):
        return empty_result(route="tool", intent="stop_camera_control", domain="desktop", confidence=0.95, reason="stop_camera_control")
    if "calibrate" in q and "eye" in q:
        return empty_result(route="tool", intent="eye_mouse_calibrate", domain="desktop", confidence=0.95, reason="eye_calibration")
    if "eye" in q and ("mouse" in q or "control" in q or "tracking" in q):
        mode = "control" if ("enable" in q or "eye control" in q) and "preview" not in q else "preview"
        return exact_schema(empty_result(route="tool", intent="eye_mouse_control", domain="desktop", confidence=0.93, reason="eye_mouse_control") | {"slots": {"mode": mode}, "risk_level": "high" if mode == "control" else "low", "requires_confirmation": mode == "control"})
    if "hand" in q or "gesture" in q:
        mode = "control" if ("enable" in q or "hand mouse" in q or "gesture mouse" in q or "mouse control" in q) and "preview" not in q else "preview"
        return exact_schema(empty_result(route="tool", intent="hand_gesture_control", domain="desktop", confidence=0.93, reason="hand_gesture_control") | {"slots": {"mode": mode}, "risk_level": "high" if mode == "control" else "low", "requires_confirmation": mode == "control"})
    if "camera" in q and "preview" in q:
        return empty_result(route="tool", intent="camera_preview", domain="desktop", confidence=0.93, reason="camera_preview")

    if _qa_like(q):
        intent = "essay_request" if q.startswith("write ") and "essay" in q else "general_qa"
        return empty_result(route="brain", intent=intent, domain="conversation", confidence=0.86, reason="qa_prefix")

    return empty_result(route="clarify", intent="unknown", domain="unknown", confidence=0.6, reason="unknown_input")


# ── LLM router (provider-abstracted: xAI Grok or Groq) ───────────────────────
def _route_with_llm(text: str, context: dict) -> dict[str, Any] | None:
    if (os.getenv("GROQ_INTENT_V2_ENABLED", "true") or "").strip().lower() in {"0", "false", "no", "off"}:
        return None
    if _llm_rate_limited():
        return None
    try:
        from engine.providers import get_intent_provider

        provider = get_intent_provider()
    except Exception as exc:
        print(f"[INTENT_V2] provider_init_failed reason={type(exc).__name__}", flush=True)
        provider = None
    if provider is None or not provider.is_available():
        return None

    try:
        from engine.tool_manifest_loader import router_capability_manifest

        capabilities = router_capability_manifest()
    except Exception:
        capabilities = []

    messages = [
        {"role": "system", "content": _load_prompt()},
        {"role": "user", "content": json.dumps({"text": text, "context": context, "capabilities": capabilities})},
    ]

    from engine.intent_taxonomy import router_decision_schema

    result = provider.route_with_schema(messages, router_decision_schema(), timeout=float(os.getenv("GROQ_INTENT_TIMEOUT_SECONDS", "3")))
    if not result.ok:
        if result.error_code == "invalid_json":
            return empty_result(route="clarify", intent="unknown", confidence=0.0, reason="invalid_json")
        # On provider failure, optionally fall back to a secondary provider.
        fallback_name = (os.getenv("INTENT_ROUTER_FALLBACK_PROVIDER", "") or "").strip().lower()
        if fallback_name:
            try:
                from engine.providers import get_intent_provider as _gip

                fb = _gip(fallback_name)
                if fb is not None and fb.is_available():
                    fb_result = fb.route_with_schema(messages, router_decision_schema(), timeout=float(os.getenv("GROQ_INTENT_TIMEOUT_SECONDS", "3")))
                    if fb_result.ok and fb_result.decision is not None:
                        print(f"[INTENT_V2] fallback_provider={fb.name} used", flush=True)
                        return fb_result.decision
            except Exception:
                pass
        return None
    if result.decision is not None:
        print(f"[INTENT_V2] provider={result.provider} model={result.model} routed", flush=True)
        return result.decision
    return None


# Backwards-compatible alias for older imports/tests.
def _route_with_groq(text: str, context: dict) -> dict[str, Any] | None:
    return _route_with_llm(text, context)


# ── Slot enrichment for deterministic fallback ───────────────────────────────
def _enrich_slots_with_llm(result: dict, text: str) -> dict:
    intent = result.get("intent", "")
    if result.get("route") not in {"tool", "workflow"}:
        return result
    if result.get("slots") and not result.get("missing_slots"):
        return result
    try:
        from engine.llm_parameter_extractor import extract_parameters
        params = extract_parameters(text, intent)
    except Exception:
        return result
    if not params.get("slots") and not params.get("missing"):
        return result
    slots = dict(result.get("slots", {}))
    missing = list(result.get("missing_slots", []))
    existing_slot_names = set(slots.keys())
    for k, v in params.get("slots", {}).items():
        if v is not None and k not in existing_slot_names:
            slots[k] = v
    llm_missing = params.get("missing", [])
    for m in llm_missing:
        if m not in existing_slot_names and m not in slots:
            if m not in missing:
                missing.append(m)
    result = dict(result)
    result["slots"] = slots
    result["missing_slots"] = missing
    return result


# ── Finalize ─────────────────────────────────────────────────────────────────
def _finalize(raw: dict[str, Any], text: str, *, selected_rule: str = "") -> dict[str, Any]:
    from engine.intent_validator import validate_router_result, validate_tool_slots
    from engine.slot_normalizer import normalize_router_result

    result = validate_router_result(raw)
    result = normalize_router_result(result, text=text)
    result = validate_tool_slots(result)

    try:
        from engine.confidence_manager import score_intent_confidence, should_clarify
        missing = bool(result.get("missing_slots"))
        score = score_intent_confidence({
            "base_confidence": result.get("confidence", 0.0),
            "route": result.get("route", ""),
            "missing_slot": missing,
            "tool_slots_complete": result.get("route") == "tool" and not missing,
            "learned_rule_match": bool(selected_rule),
        })
        result["confidence"] = score
        if should_clarify(score, result.get("route", ""), pending_state=result.get("route") in {"followup", "workflow"}) and result.get("route") not in {"reject"}:
            result["route"] = "clarify"
            result["expects_user_reply"] = True
            if not result.get("clarification_question"):
                from engine.confidence_manager import build_clarification_question
                result["clarification_question"] = build_clarification_question(text, intent=result.get("intent", ""), missing_slot=((result.get("missing_slots") or [""])[0] if result.get("missing_slots") else ""))
            result["should_call_tool"] = False
            result["should_call_gemini"] = False
    except Exception:
        pass

    result = validate_router_result(result)
    selected_tool = result.get("intent", "") if result.get("route") == "tool" else ""
    missing_slot = (result.get("missing_slots") or [""])[0] if result.get("missing_slots") else ""
    try:
        from engine.intent_explainer import record_intent_decision
        record_intent_decision(result, selected_tool=selected_tool, selected_rule=selected_rule, missing_slot=missing_slot)
    except Exception:
        pass
    try:
        from engine.presence_state import get_presence
        get_presence().update_mode(
            "thinking",
            attention="tool" if result.get("route") in {"tool", "workflow", "react"} else "user",
            confidence=float(result.get("confidence") or 0.0),
            current_goal=f"route={result.get('route', '')} intent={result.get('intent', '')}",
            last_event="intent_routed",
        )
    except Exception:
        pass
    print(f"[INTENT_V2] route={result.get('route')} intent={result.get('intent')} confidence={result.get('confidence'):.2f}", flush=True)
    return exact_schema(result)


# ── Public entry point ───────────────────────────────────────────────────────
def _deterministic_is_confident(result: dict[str, Any]) -> bool:
    """A deterministic match we trust enough to skip the LLM entirely."""
    route = result.get("route")
    if route in {"clarify", "reject"} or result.get("intent") in {"unknown"}:
        return False
    if route in {"system", "memory", "training", "workflow", "react"}:
        return True
    if route in {"tool", "output"}:
        # Confident only when no slots are missing (e.g. "open chrome", not bare "open").
        return not result.get("missing_slots")
    if route == "brain":
        return float(result.get("confidence") or 0.0) >= 0.85
    return False


def route_intent_v2(text: str, *, source: str = "ui", context: dict | None = None) -> dict[str, Any]:
    from engine.intent_context_builder import build_intent_context
    from engine.intent_pre_router import pre_route

    ctx = context or build_intent_context(text, source=source)
    pre = pre_route(text, ctx)
    if pre:
        return _finalize(pre, text)

    try:
        from engine.correction_learner import apply_correction
        correction = apply_correction(text)
        if correction.get("matched"):
            action_text = str(correction.get("action_text") or "")
            if action_text:
                routed = _deterministic_router(action_text, ctx)
                return _finalize(routed, action_text, selected_rule=str((correction.get("rule") or {}).get("id") or "correction"))
    except Exception:
        pass

    # Deterministic exact/alias routing first — cheap, safe, model-independent.
    deterministic = _deterministic_router(text, ctx)
    if _deterministic_is_confident(deterministic):
        return _finalize(deterministic, text)

    # LLM router (xAI Grok or Groq) for fuzzy / ambiguous language.
    llm_raw = _route_with_groq(text, ctx)
    if llm_raw is not None and llm_raw.get("route") not in {"clarify", "unknown"} and llm_raw.get("intent") not in {"unknown", "clarify"}:
        return _finalize(llm_raw, text)

    # Fall back to deterministic result (enriched with slot extraction).
    enriched = _enrich_slots_with_llm(deterministic, text)
    return _finalize(enriched, text)


def classify_intent_v2(text: str, *, source: str = "ui", context: dict | None = None) -> dict[str, Any]:
    return route_intent_v2(text, source=source, context=context)
