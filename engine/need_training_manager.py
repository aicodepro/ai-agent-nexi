from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from engine.training_profile_store import disable_profile, list_profiles, mark_profile_used, normalize_need, profile_id, upsert_profile
from engine.training_safety import redact_training_text, validate_text
from engine.user_intent_profile import detect_need as detect_text_need, score_need_match


_active_need: str = ""
_pending_instructions: list[dict[str, Any]] = []


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _split_traits(text: str) -> list[str]:
    value = re.sub(r"^(when i ask(?: for)? [^,]+,|for [^,]+,)", "", text.strip(), flags=re.I).strip()
    parts = re.split(r",| and |;", value)
    return [part.strip(" .")[:180] for part in parts if part.strip(" .")]


def _style_for(need: str, rules: list[str]) -> str:
    joined = " ".join(rules).lower()
    if "founder" in joined:
        return "founder"
    if "technical" in joined or need in {"coding", "seo", "jarvis debugging"}:
        return "technical"
    if "demo" in joined or need == "client demo":
        return "demo"
    if "sales" in joined or need == "sales":
        return "sales"
    if "short" in joined or "minimal" in joined:
        return "minimal"
    return need if need in {"coding", "seo", "sales"} else "direct"


def _aliases_for(need: str) -> list[str]:
    base = [need]
    if need == "seo":
        base += ["seo audit", "ranking", "technical seo", "rank this page"]
    elif need == "coding":
        base += ["fix code", "debug", "patch", "run tests", "next.js component"]
    elif need == "sales":
        base += ["sales call", "client message", "lead", "proposal"]
    elif need == "jarvis debugging":
        base += ["jarvis debugging", "jarvis is not", "tts", "asr", "hotword"]
    return list(dict.fromkeys(base))


def start_need_training(need_name: str | None = None) -> dict:
    global _active_need, _pending_instructions
    need = normalize_need(need_name or "general")
    _active_need = need
    _pending_instructions = []
    print(f"[NEED_TRAINING] started need={need}", flush=True)
    label = need[:1].upper() + need[1:]
    return {"started": True, "need": need, "message": f"{label} training active. Teach me the workflow, style, tools, or examples."}


def get_active_need() -> str:
    return _active_need


def stop_need_training() -> dict:
    global _active_need, _pending_instructions
    need = _active_need
    if need and _pending_instructions:
        profile = build_need_profile(need, _pending_instructions)
        saved = save_need_profile(profile)
    else:
        saved = {"saved": False}
    _active_need = ""
    _pending_instructions = []
    label = need[:1].upper() + need[1:] if need else "Training"
    return {"stopped": True, "need": need, "saved": saved.get("saved", False), "message": f"Training saved. {label} profile is ready." if need else "Training stopped."}


def classify_training_need(text: str) -> dict:
    value = redact_training_text(text)
    match = re.search(r"train jarvis (?:deeply )?for ([a-z0-9 ._/-]+)", value, re.I)
    if match:
        return {"need": normalize_need(match.group(1)), "confidence": 0.98, "reason": "explicit training command"}
    detected = detect_text_need(value)
    return {"need": detected.get("need", ""), "confidence": detected.get("confidence", 0.0), "reason": detected.get("reason", "")}


def capture_training_instruction(text: str, current_need: str | None = None) -> dict:
    global _pending_instructions
    need = normalize_need(current_need or _active_need or classify_training_need(text).get("need") or "general")
    value = redact_training_text(text)
    safe, reason = validate_text(value)
    if not safe:
        return {"captured": False, "reason": reason, "need": need}
    lowered = value.lower()
    item_type = "instruction"
    if lowered.startswith("use this as ideal example") or "ideal example" in lowered or "save this response style" in lowered:
        item_type = "example_rule"
    elif "bad example" in lowered or "not like this" in lowered:
        item_type = "negative_example_rule"
    elif "wrong" in lowered or "next time" in lowered or "you misunderstood" in lowered:
        item_type = "correction_rule"
    rules = _split_traits(value)
    instruction = {"type": item_type, "need": need, "text": value[:1000], "rules": rules, "created_at": _now()}
    _pending_instructions.append(instruction)
    _pending_instructions = _pending_instructions[-20:]
    print(f"[NEED_TRAINING] instruction_captured type={item_type}", flush=True)
    profile = build_need_profile(need, [instruction])
    saved = save_need_profile(profile)
    return {"captured": True, "need": need, "instruction": instruction, "profile": saved.get("profile")}


def build_need_profile(need_name: str, instructions: list[dict]) -> dict:
    need = normalize_need(need_name or "general")
    all_rules: list[str] = []
    examples: list[dict] = []
    success: list[str] = []
    for item in instructions or []:
        for rule in item.get("rules", []) or []:
            if rule:
                all_rules.append(rule)
        if item.get("type") in {"example_rule", "negative_example_rule"}:
            examples.append({"type": item.get("type"), "text": item.get("text", "")[:600], "created_at": item.get("created_at", _now())})
        if "pass/partial/fail" in item.get("text", "").lower():
            success.append("Report PASS/PARTIAL/FAIL")
    rules = list(dict.fromkeys(all_rules))[-30:]
    output = "workspace" if any("long" in r.lower() or "audit" in r.lower() for r in rules) else "main_ui"
    return {
        "id": profile_id(need),
        "level": "medium",
        "need_name": need,
        "aliases": _aliases_for(need),
        "description": f"Need profile for {need}",
        "style": _style_for(need, rules),
        "rules": rules,
        "workflow_steps": [r for r in rules if any(word in r.lower() for word in ("inspect", "run", "test", "audit", "fix", "ask"))],
        "tools_preferred": [],
        "tools_blocked": [],
        "output_preference": output,
        "clarification_policy": "ask_if_missing",
        "examples": examples[-10:],
        "success_criteria": list(dict.fromkeys(success + [r for r in rules if "avoid" in r.lower() or "include" in r.lower()]))[-20:],
        "created_at": _now(),
        "updated_at": _now(),
        "last_used_at": "",
        "use_count": 0,
        "enabled": True,
    }


def save_need_profile(profile: dict) -> dict:
    saved = upsert_profile(profile)
    return {"saved": True, "profile": saved}


def match_need_profile(user_text: str, context: dict | None = None) -> list[dict]:
    matches = []
    detected = detect_text_need(user_text, context)
    for profile in list_profiles(enabled_only=True):
        score = score_need_match(user_text, profile)
        if detected.get("need") and normalize_need(profile.get("need_name")) == normalize_need(detected.get("need")):
            score = max(score, float(detected.get("confidence", 0.0)))
        if score >= 0.55:
            match = dict(profile)
            match["match_confidence"] = round(score, 2)
            matches.append(match)
            mark_profile_used(profile.get("id", ""))
            print(f"[NEED_TRAINING] profile_matched need={profile.get('need_name')} confidence={score:.2f}", flush=True)
    return sorted(matches, key=lambda item: item.get("match_confidence", 0.0), reverse=True)


def match_need_profiles(user_text: str, context: dict | None = None) -> list[dict]:
    return match_need_profile(user_text, context)


def apply_need_profile(strategy: dict, profiles: list[dict]) -> dict:
    updated = dict(strategy or {})
    if not profiles:
        updated.setdefault("need_profile_used", False)
        return updated
    profile = profiles[0]
    need = profile.get("need_name", "")
    updated["detected_need"] = need
    updated["need_profile_used"] = True
    updated["active_need_profile"] = profile
    updated["style"] = profile.get("style", "direct")
    updated["output_preference"] = profile.get("output_preference", "main_ui")
    updated["profile_rules_used"] = profile.get("rules", [])[:8]
    updated["confidence"] = max(float(updated.get("confidence", 0.0) or 0.0), float(profile.get("match_confidence", 0.75)))
    if updated.get("chosen_route") in {None, "", "clarify"} or updated.get("chosen_intent") == "unknown":
        updated["chosen_route"] = "brain"
        updated["chosen_intent"] = "need_profile_task"
    print(f"[NEED_TRAINING] profile_applied need={need}", flush=True)
    return updated


def list_need_profiles() -> list[dict]:
    return list_profiles()


def disable_need_profile(query: str) -> dict:
    return disable_profile(query)


def format_need_profiles(limit: int = 8) -> str:
    profiles = [p for p in list_need_profiles() if p.get("enabled", True)]
    if not profiles:
        return "No active training profiles yet."
    chunks = []
    for profile in profiles[-limit:]:
        rules = ", ".join(profile.get("rules", [])[:3])
        chunks.append(f"{profile.get('need_name')}: {rules or profile.get('style', 'direct')}")
    return "Training profiles: " + "; ".join(chunks)
