from __future__ import annotations

import json
import os
import re

import requests

ALLOWED_ROUTES = {
    "interrupt", "sleep", "wake", "cancel", "memory", "local_skill", "workflow_start",
    "workflow_answer", "workflow_switch", "followup_answer", "brain", "clarify", "repeat_last", "output_action", "training",
}
ALLOWED_INTENTS = {
    "open_app", "open_website", "web_search", "create_folder", "create_file", "take_note",
    "remember", "recall_memory", "forget_memory", "essay_request", "general_qa",
    "summarize", "explain", "copy_latest_output", "save_latest_output", "clarify", "unknown",
    "repeat_last", "stop_speaking", "workflow_answer", "cancel", "camera_preview", "hand_gesture_control", "eye_mouse_control",
    "eye_mouse_calibrate", "stop_camera_control", "local_skill",
    "train_jarvis", "learn_rule", "correction", "show_training_rules", "cognitive_status",
    "learned_rule_match", "user_preference_update", "why_did_you_do_that", "what_did_you_understand",
    "train_need_profile", "start_ultra_training", "deep_training_command", "show_training_profiles",
}
DEFAULT_RESULT = {
    "route": "clarify",
    "intent": "unknown",
    "confidence": 0.0,
    "reason": "fallback",
    "slots": {},
    "workflow_action": "none",
    "expects_user_reply": False,
    "clarification_question": "I didn't catch that. Please say it again in English.",
    "requires_safety": False,
}


def get_model_config() -> dict:
    return {
        "intent_model": os.getenv("GROQ_INTENT_MODEL", "openai/gpt-oss-20b"),
        "intent_model_fallback": os.getenv("GROQ_INTENT_MODEL_FALLBACK", "qwen/qwen3-32b"),
        "intent_model_strong": os.getenv("GROQ_INTENT_MODEL_STRONG", "openai/gpt-oss-120b"),
        "safety_model": os.getenv("SAFETY_MODEL", "openai/gpt-oss-safeguard-20b"),
        "brain_model_primary": os.getenv("GEMINI_MODEL_PRIMARY", "gemini-2.5-flash"),
        "brain_model_fallback": os.getenv("GEMINI_MODEL_FALLBACK", "gemini-2.5-flash-lite"),
        "asr_model": os.getenv("ASR_MODEL", "whisper-large-v3-turbo"),
        "tts_model": os.getenv("TTS_MODEL", "orpheus-english"),
        "vision_model": os.getenv("VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
    }


def _load_prompt() -> str:
    from engine.prompt_loader import load_prompt_file

    return load_prompt_file("jarvis_groq_intent_system_prompt.txt", load_prompt_file("groq_intent_system_prompt.txt", "You are Jarvis Intent Planner. Return strict JSON only."))


def _json_object(text: str) -> dict:
    value = (text or "").strip()
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        value = match.group(0)
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


def _normalize(data: dict) -> dict:
    result = dict(DEFAULT_RESULT)
    result.update(data or {})
    if result.get("route") not in ALLOWED_ROUTES:
        result["route"] = "clarify"
    if result.get("intent") not in ALLOWED_INTENTS:
        result["intent"] = "unknown"
    try:
        result["confidence"] = max(0.0, min(1.0, float(result.get("confidence", 0.0))))
    except (TypeError, ValueError):
        result["confidence"] = 0.0
    if not isinstance(result.get("slots"), dict):
        result["slots"] = {}
    result["expects_user_reply"] = bool(result.get("expects_user_reply", False))
    result["requires_safety"] = bool(result.get("requires_safety", False))
    result["clarification_question"] = str(result.get("clarification_question") or "")
    return result


def _finalize(result: dict, *, json_valid: bool = True, low_confidence: bool = False) -> dict:
    normalized = _normalize(result)
    print(f"[INTENT] route={normalized.get('route')} intent={normalized.get('intent')} confidence={normalized.get('confidence')}", flush=True)
    print(f"[INTENT] json_valid={str(json_valid).lower()}", flush=True)
    if low_confidence:
        print("[INTENT] low_confidence_clarify=true", flush=True)
    return normalized


def _pending_followup_classify(text: str, followup_type: str) -> dict:
    value = (text or "").strip()
    q = value.lower().rstrip(".?!")
    if followup_type == "open_app":
        try:
            from engine.local_skills import SITES
            is_site = q in SITES or "." in q
        except Exception:
            is_site = "." in q
        if is_site:
            return _normalize({"route": "local_skill", "intent": "open_website", "confidence": 0.98, "reason": "pending open target website", "slots": {"url": "youtube.com" if q == "youtube" else q}})
        return _normalize({"route": "local_skill", "intent": "open_app", "confidence": 0.98, "reason": "pending open target app", "slots": {"app_name": value}})
    if followup_type == "web_search":
        return _normalize({"route": "local_skill", "intent": "web_search", "confidence": 0.98, "reason": "pending search query", "slots": {"query": value}})
    if followup_type in {"folder_name", "file_name"}:
        return _normalize({"route": "workflow_answer", "intent": "workflow_answer", "confidence": 0.95, "reason": "pending slot answer", "slots": {followup_type: value}})
    return _normalize({"route": "followup_answer", "intent": "unknown", "confidence": 0.8, "reason": "pending follow-up answer", "slots": {}})


def _deterministic_classify(text: str, active_workflow: dict | None = None, pending_followup: dict | None = None) -> dict:
    q = (text or "").strip().lower().rstrip(".?!")
    if pending_followup:
        return _pending_followup_classify(text, str(pending_followup.get("followup_type") or ""))
    if q in {"repeat", "can you repeat", "say that again", "repeat that"}:
        return _normalize({"route": "repeat_last", "intent": "repeat_last", "confidence": 1.0, "reason": "repeat phrase"})
    output_intents = {
        "copy it": "copy_latest_output",
        "copy this": "copy_latest_output",
        "open the box": "show_latest_output",
        "show it again": "show_latest_output",
        "close the box": "close_output_workspace",
        "minimize the box": "minimize_output_workspace",
        "pin the box": "pin_output_workspace",
        "make it shorter": "shorten_latest_output",
        "regenerate it": "regenerate_latest_output",
        "create a file": "create_file_from_latest_output",
    }
    if q in output_intents or q.startswith("save it as "):
        return _normalize({"route": "output_action", "intent": output_intents.get(q, "save_latest_output"), "confidence": 1.0, "reason": "output action phrase"})
    if q in {"stop", "stop speaking", "shut up", "cancel speech"}:
        return _normalize({"route": "interrupt", "intent": "stop_speaking", "confidence": 1.0, "reason": "interrupt phrase"})
    if q in {"sleep", "go to sleep", "stop listening"}:
        return _normalize({"route": "sleep", "intent": "unknown", "confidence": 1.0, "reason": "sleep phrase"})
    if q in {"wake", "wake up", "activate jarvis"}:
        return _normalize({"route": "wake", "intent": "unknown", "confidence": 1.0, "reason": "wake phrase"})
    if q in {"train jarvis", "start training", "start training mode", "training mode"}:
        return _normalize({"route": "training", "intent": "train_jarvis", "confidence": 1.0, "reason": "training mode phrase"})
    if q.startswith("train jarvis deeply for ") or q.startswith("start ultra training for "):
        return _normalize({"route": "training", "intent": "start_ultra_training", "confidence": 1.0, "reason": "ultra training phrase"})
    if q.startswith("train jarvis for "):
        return _normalize({"route": "training", "intent": "train_need_profile", "confidence": 1.0, "reason": "need training phrase"})
    if q.startswith(("create training dataset", "simulate training", "run training evaluation", "show training score", "show weak areas", "show training curriculum")):
        return _normalize({"route": "training", "intent": "deep_training_command", "confidence": 1.0, "reason": "deep training management phrase"})
    if q.startswith(("when i say ", "whenever i ask ")):
        return _normalize({"route": "training", "intent": "learn_rule", "confidence": 1.0, "reason": "training rule phrase"})
    if q in {"show training rules", "what have you learned", "what have you learned?"}:
        return _normalize({"route": "memory", "intent": "show_training_rules", "confidence": 1.0, "reason": "training summary phrase"})
    if q in {"show training profiles", "show need profiles", "show jarvis profiles"}:
        return _normalize({"route": "memory", "intent": "show_training_profiles", "confidence": 1.0, "reason": "training profile summary phrase"})
    if q == "cognitive status":
        return _normalize({"route": "memory", "intent": "cognitive_status", "confidence": 1.0, "reason": "cognitive status phrase"})
    if q in {"why did you do that", "why did you do that?"}:
        return _normalize({"route": "memory", "intent": "why_did_you_do_that", "confidence": 1.0, "reason": "route explanation phrase"})
    if q in {"what did you understand", "what did you understand?"}:
        return _normalize({"route": "memory", "intent": "what_did_you_understand", "confidence": 1.0, "reason": "understanding summary phrase"})
    if active_workflow:
        if q in {"cancel", "never mind", "nevermind", "forget it"}:
            return _normalize({"route": "cancel", "intent": "cancel", "confidence": 1.0, "workflow_action": "cancel", "reason": "workflow cancel"})
        if q.startswith(("open ", "search ", "google ")):
            return _normalize({"route": "workflow_switch", "intent": "open_app" if q.startswith("open ") else "web_search", "confidence": 0.95, "workflow_action": "switch", "reason": "new local intent"})
        if any(word in q for word in ("essay", "explain", "write", "summarize", "ideas")):
            return _normalize({"route": "workflow_switch", "intent": "essay_request", "confidence": 0.95, "workflow_action": "switch", "reason": "new brain intent"})
        return _normalize({"route": "workflow_answer", "intent": "workflow_answer", "confidence": 0.9, "workflow_action": "continue", "reason": "active workflow reply"})
    if q.startswith(("remember ", "remember that ")) or q in {"show memory", "what do you remember"}:
        return _normalize({"route": "memory", "intent": "remember", "confidence": 0.95, "reason": "memory phrase"})
    if q in {"open", "launch", "start"}:
        return _normalize({"route": "clarify", "intent": "open_app", "confidence": 0.92, "reason": "missing app name", "slots": {}, "expects_user_reply": True, "clarification_question": "Which app should I open?"})
    if q in {"search", "google", "search web", "search the web"}:
        return _normalize({"route": "clarify", "intent": "web_search", "confidence": 0.92, "reason": "missing search query", "slots": {}, "expects_user_reply": True, "clarification_question": "What should I search for?"})
    if q.startswith(("create folder", "create a folder", "make folder", "new folder")):
        return _normalize({"route": "workflow_start", "intent": "create_folder", "confidence": 0.95, "reason": "folder workflow"})
    if "stop" in q and any(word in q for word in ("camera", "gesture", "eye", "control")):
        return _normalize({"route": "local_skill", "intent": "stop_camera_control", "confidence": 0.96, "reason": "stop camera controls", "slots": {}})
    if "calibrate" in q and "eye" in q:
        return _normalize({"route": "local_skill", "intent": "eye_mouse_calibrate", "confidence": 0.95, "reason": "eye calibration", "slots": {}})
    if "eye" in q and ("mouse" in q or "control" in q or "tracking" in q):
        mode = "control" if ("enable" in q or "eye control" in q) and "preview" not in q else "preview"
        return _normalize({"route": "local_skill", "intent": "eye_mouse_control", "confidence": 0.93, "reason": "eye mouse control", "slots": {"mode": mode}, "requires_safety": mode == "control"})
    if "hand" in q or "gesture" in q:
        mode = "control" if ("enable" in q or "hand mouse" in q or "gesture mouse" in q or "mouse control" in q) and "preview" not in q else "preview"
        return _normalize({"route": "local_skill", "intent": "hand_gesture_control", "confidence": 0.93, "reason": "hand gesture control", "slots": {"mode": mode}, "requires_safety": mode == "control"})
    if "camera" in q and "preview" in q:
        return _normalize({"route": "local_skill", "intent": "camera_preview", "confidence": 0.93, "reason": "camera preview", "slots": {}})
    if q.startswith(("open ", "launch ")):
        target = q.split(" ", 1)[1].strip()
        try:
            from engine.local_skills import SITES
            is_site = target in SITES or "." in target
        except Exception:
            is_site = "." in target
        if is_site:
            return _normalize({"route": "local_skill", "intent": "open_website", "confidence": 0.95, "reason": "open website", "slots": {"url": "youtube.com" if target == "youtube" else target}})
        return _normalize({"route": "local_skill", "intent": "open_app", "confidence": 0.95, "reason": "open app", "slots": {"app_name": target}})
    if q.startswith(("search ", "google ")):
        query = q.split(" ", 1)[1].strip()
        return _normalize({"route": "local_skill", "intent": "web_search", "confidence": 0.95, "reason": "search query", "slots": {"query": query}})
    if q.startswith("take screenshot"):
        return _normalize({"route": "local_skill", "intent": "local_skill", "confidence": 0.9, "reason": "local prefix"})
    if any(word in q for word in ("essay", "explain", "why", "how", "what is", "ideas")):
        return _normalize({"route": "brain", "intent": "general_qa", "confidence": 0.85, "reason": "brain phrase"})
    return dict(DEFAULT_RESULT)


def classify_intent(text: str, *, source: str, active_workflow: dict | None = None, recent_turns: list[dict] | None = None, pending_followup: dict | None = None) -> dict:
    deterministic = _deterministic_classify(text, active_workflow, pending_followup)
    if deterministic["confidence"] >= 0.9 or (os.getenv("GROQ_INTENT_ENABLED", "true") or "").lower() in {"0", "false", "no", "off"}:
        return _finalize(deterministic)
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return _finalize(deterministic)
    payload = {
        "model": get_model_config()["intent_model"],
        "temperature": float(os.getenv("GROQ_INTENT_TEMPERATURE", "0")),
        "max_tokens": int(os.getenv("GROQ_INTENT_MAX_TOKENS", "300")),
        "messages": [
            {"role": "system", "content": _load_prompt()},
            {"role": "user", "content": json.dumps({"text": text, "source": source, "active_workflow": active_workflow, "pending_followup": pending_followup, "recent_turns": recent_turns or []})},
        ],
    }
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("GROQ_INTENT_TIMEOUT_SECONDS", "4")),
        )
        if response.status_code >= 400:
            return _finalize(deterministic)
        content = response.json()["choices"][0]["message"]["content"]
        result = _normalize(_json_object(content))
        if result["confidence"] < float(os.getenv("GROQ_INTENT_MIN_CONFIDENCE", "0.65")):
            return _finalize(dict(DEFAULT_RESULT), low_confidence=True)
        return _finalize(result)
    except json.JSONDecodeError:
        return _finalize(dict(DEFAULT_RESULT), json_valid=False)
    except Exception:
        return _finalize(deterministic)
