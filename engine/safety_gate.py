from __future__ import annotations

import json
import os
import re

import requests

RISKY_WORDS = re.compile(
    r"\b(delete|overwrite|move|terminal|powershell|cmd|execute|run code|send email|send message|credential|password|token|api key|secret)\b",
    re.I,
)


def should_safety_check(text: str, route: str = "", intent: str = "") -> bool:
    if (os.getenv("SAFETY_GATE_ENABLED", "true") or "").lower() in {"0", "false", "no", "off"}:
        return False
    haystack = " ".join([text or "", route or "", intent or ""])
    return bool(RISKY_WORDS.search(haystack))


def _fallback_decision(text: str) -> dict:
    if should_safety_check(text):
        return {
            "allowed": True,
            "risk": "medium",
            "category": "risky_action",
            "reason": "Risky action requires confirmation.",
            "requires_confirmation": True,
        }
    return {"allowed": True, "risk": "none", "category": "none", "reason": "No safety check needed.", "requires_confirmation": False}


def classify_safety(text: str, *, action: str = "", context: dict | None = None) -> dict:
    if not should_safety_check(text, intent=action):
        return _fallback_decision(text)
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    model = (os.getenv("SAFETY_MODEL") or "openai/gpt-oss-safeguard-20b").strip()
    if not api_key:
        return _fallback_decision(text)
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Classify safety. Return JSON only with allowed, risk, category, reason, requires_confirmation."},
            {"role": "user", "content": json.dumps({"text": (text or "")[:800], "action": action, "context": context or {}})},
        ],
    }
    try:
        response = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=float(os.getenv("SAFETY_GATE_TIMEOUT_SECONDS", "4")),
        )
        if response.status_code >= 400:
            return _fallback_decision(text)
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return enforce_safety(data)
    except Exception:
        return _fallback_decision(text)


def enforce_safety(decision: dict) -> dict:
    data = dict(decision or {})
    risk = str(data.get("risk") or "none").lower()
    data["risk"] = risk if risk in {"none", "low", "medium", "high", "blocked"} else "medium"
    data["allowed"] = bool(data.get("allowed", data["risk"] not in {"high", "blocked"}))
    data["requires_confirmation"] = bool(data.get("requires_confirmation", data["risk"] == "medium"))
    data["category"] = str(data.get("category") or "unknown")[:80]
    data["reason"] = str(data.get("reason") or "Safety decision.")[:160]
    if data["risk"] in {"high", "blocked"}:
        data["allowed"] = False
    return data


def _tool_requires_confirmation(tool: dict, values: dict) -> bool:
    if not tool.get("requires_confirmation"):
        return False
    mode = str(values.get("mode") or "").strip().lower()
    if tool.get("name") in {"hand_gesture_control", "eye_mouse_control"} and mode != "control":
        return False
    return True


def execution_is_safe(tool_name: str, tool_input: dict | None = None, *, user_text: str = "", context: dict | None = None) -> dict:
    values = tool_input or {}
    try:
        from engine.tool_registry import get_tool
        tool = get_tool(tool_name) or {}
    except Exception:
        tool = {}
    if not tool:
        return {"allowed": False, "risk": "blocked", "category": "unknown_tool", "reason": "Unknown tool.", "requires_confirmation": False}
    if _tool_requires_confirmation(tool, values) and not values.get("confirmed"):
        return {
            "allowed": False,
            "risk": str(tool.get("safety") or "medium"),
            "category": "confirmation_required",
            "reason": "This action requires confirmation.",
            "requires_confirmation": True,
        }
    action_text = " ".join([str(user_text or ""), str(tool_name or ""), json.dumps(values, sort_keys=True)[:500]])
    decision = classify_safety(action_text, action=tool_name, context=context)
    if decision.get("requires_confirmation") and not values.get("confirmed"):
        decision = {**decision, "allowed": False}
    return enforce_safety(decision)
