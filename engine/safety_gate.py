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


def _provider_unavailable_decision(action: str, text: str = "", context: dict | None = None) -> dict:
    """No safety provider reachable.

    A named ACTION fails closed — blocking is the only safe answer when the classifier that
    would have vetted it is unavailable.

    With no action it depends on what the text is FOR. A brain question performs nothing, so
    demanding confirmation to answer "what is an API key?" is pure noise (and the phrase
    trips RISKY_WORDS on "api key"). Anything else is treated as an imperative and keeps the
    heuristic: a flat "allowed, no confirmation" would be LOOSER than the pre-existing
    behaviour, where "delete notes" with no provider came back medium / requires-confirmation.
    """
    if not action:
        if str((context or {}).get("route") or "").strip().lower() == "brain":
            return {"allowed": True, "risk": "none", "category": "qa", "reason": "No action requested.", "requires_confirmation": False}
        return _fallback_decision(text)
    return {
        "allowed": False,
        "risk": "blocked",
        "category": "safety_unavailable",
        "reason": "The safety check is unavailable, so this action was blocked.",
        "requires_confirmation": False,
    }


def _safety_timeout_seconds() -> float:
    try:
        value = float(os.getenv("SAFETY_GATE_TIMEOUT_SECONDS", "4"))
    except (TypeError, ValueError):
        value = 4.0
    return max(0.1, min(value, 10.0))


def classify_safety(text: str, *, action: str = "", context: dict | None = None) -> dict:
    if (os.getenv("SAFETY_GATE_ENABLED", "true") or "").lower() in {"0", "false", "no", "off"}:
        return {"allowed": True, "risk": "none", "category": "disabled", "reason": "Safety gate disabled.", "requires_confirmation": False}
    requires_check = should_safety_check(text, intent=action)
    if action:
        try:
            from engine.tool_registry import get_tool
            requires_check = requires_check or str((get_tool(action) or {}).get("safety") or "low").lower() in {"medium", "high", "critical"}
        except Exception:
            pass
    if not requires_check:
        return _fallback_decision(text)
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    model = (os.getenv("SAFETY_MODEL") or "openai/gpt-oss-safeguard-20b").strip()
    if not api_key:
        return _provider_unavailable_decision(action, text, context)
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
            timeout=_safety_timeout_seconds(),
        )
        if response.status_code >= 400:
            return _provider_unavailable_decision(action, text, context)
        content = response.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        if not isinstance(data, dict) or not {"allowed", "risk", "requires_confirmation"}.issubset(data):
            return _provider_unavailable_decision(action, text, context)
        if not isinstance(data["allowed"], bool) or not isinstance(data["requires_confirmation"], bool):
            return _provider_unavailable_decision(action, text, context)
        return enforce_safety(data)
    except Exception:
        return _provider_unavailable_decision(action, text, context)


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
    # engine.computer_use tools gate through approval_queue — that queue IS their
    # confirmation step (submit -> user approves -> re-invoked with the internal token).
    # Refusing them here means they are never queued, so approve_action has nothing to
    # approve and the action is unreachable instead of merely confirmed. Mirrors the same
    # carve-out in tool_registry.execute_tool.
    try:
        from engine.approval_queue import is_queue_gated
        if is_queue_gated(tool.get("handler")):
            return False
    except Exception:
        pass
    # Studio tools are gated by an authorization token the owner alone can mint, which is
    # stronger than a spoken "confirm". Intercepting them here means an authorized build
    # can never start. Mirrors the same carve-out in tool_registry.execute_tool.
    try:
        from engine.tool_registry import STUDIO_AUTH_TOOLS
        if tool.get("name") in STUDIO_AUTH_TOOLS:
            return False
    except Exception:
        pass
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
    studio_auth = values.get("_studio_auth")
    if tool_name == "nexi_start_studio_build" and isinstance(studio_auth, str) and studio_auth:
        # The supervisor remains authoritative and validates/consumes this one-time token.
        return {
            "allowed": True,
            "risk": str(tool.get("safety") or "high"),
            "category": "studio_authorization_delegated",
            "reason": "Studio authorization is delegated to Studio governance.",
            "requires_confirmation": False,
        }
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
