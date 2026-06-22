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
    """Classify risk level. Returns {risk, requires_confirmation, reason}."""
    if not should_safety_check(text):
        return {"risk": "low", "requires_confirmation": False, "reason": "no_risky_words"}

    # Try Groq LLM classification
    api_key = cfg.groq_api_key
    model = os.getenv("SAFETY_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    if api_key:
        try:
            import requests
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": (
                            "Classify the safety risk of this user action. "
                            "Return JSON: {\"risk\": \"low|medium|high|blocked\", \"reason\": \"...\"}. "
                            "Only return valid JSON."
                        )},
                        {"role": "user", "content": f"Action: {text}\nContext: {action} {context}"},
                    ],
                    "temperature": 0.0,
                    "max_tokens": 100,
                },
                timeout=6,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            match = re.search(r"\{[^}]+\}", content)
            if match:
                data = json.loads(match.group())
                risk = data.get("risk", "medium").lower()
                if risk in {"high", "blocked"}:
                    return {"risk": risk, "requires_confirmation": True,
                            "reason": data.get("reason", "llm_classified")}
                if risk == "medium":
                    return {"risk": "medium", "requires_confirmation": True,
                            "reason": data.get("reason", "llm_classified")}
                return {"risk": "low", "requires_confirmation": False,
                        "reason": data.get("reason", "llm_classified")}
        except Exception:
            pass

    # Fallback: risky words found → require confirmation
    return {"risk": "medium", "requires_confirmation": True, "reason": "risky_words_detected"}


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
