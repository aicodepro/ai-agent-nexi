"""Safety gate — risk assessment for dangerous actions."""

import re
import os
import json
from core.config import cfg

RISKY_WORDS = re.compile(
    r"\b(delete|remove|overwrite|move|terminal|powershell|cmd\.exe|execute|run\s+code"
    r"|send\s+email|send\s+message|credential|password|token|api\s*key|secret"
    r"|format\s+disk|drop\s+table|rm\s+-rf|shutdown|reboot)\b",
    re.IGNORECASE,
)


def should_safety_check(text: str, route: str = "", intent: str = "") -> bool:
    if not cfg.safety_gate_enabled:
        return False
    combined = f"{text} {route} {intent}"
    return bool(RISKY_WORDS.search(combined))


def classify_safety(text: str, action: str = "", context: str = "") -> dict:
    """Classify risk level using keyword analysis (local, fast). Optionally uses LLM for nuanced cases."""
    if not should_safety_check(text):
        return {"risk": "low", "requires_confirmation": False, "reason": "no_risky_words"}

    # Local keyword-based classification (instant, no network call)
    text_lower = text.lower()
    
    # High risk keywords
    high_risk = re.compile(r"\b(format\s+disk|drop\s+table|rm\s+-rf|shutdown|reboot)\b", re.IGNORECASE)
    if high_risk.search(text_lower):
        return {"risk": "high", "requires_confirmation": True, "reason": "high_risk_keyword"}
    
    # Medium risk keywords
    medium_risk = re.compile(r"\b(delete|remove|overwrite|move|terminal|powershell|cmd\.exe|execute|run\s+code"
                             r"|send\s+email|credential|password|token|api\s*key|secret)\b", re.IGNORECASE)
    if medium_risk.search(text_lower):
        return {"risk": "medium", "requires_confirmation": True, "reason": "medium_risk_keyword"}
    
    return {"risk": "low", "requires_confirmation": False, "reason": "safe_after_analysis"}


def enforce_safety(decision: dict) -> dict:
    risk = decision.get("risk", "low").lower()
    if risk in {"high", "blocked"}:
        decision["allowed"] = False
        decision["requires_confirmation"] = True
    elif risk == "medium":
        decision["allowed"] = True
        decision["requires_confirmation"] = True
    else:
        decision["allowed"] = True
        decision["requires_confirmation"] = False
    return decision
