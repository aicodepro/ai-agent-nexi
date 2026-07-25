from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


def _load_prompt(intent: str) -> str:
    return (
        f"You are a parameter extractor for Nexi desktop assistant. "
        f"Given a user command classified as intent '{intent}', extract all parameters from the full text. "
        f"Return strict JSON only. No markdown, no explanation, no chain-of-thought.\n\n"
        f"Schema:\n"
        f'{{"slots": {{"param_name": "value or null"}}, "missing": ["list of required params not found in text"]}}\n\n'
        f"Rules:\n"
        f"- 'location' param: extract from phrases like 'on desktop', 'in documents', 'to downloads'\n"
        f"- 'folder_name' param: extract from phrases like 'named X', 'called X', or a single word after 'folder'\n"
        f"- 'app_name' param: extract the app name after 'open' or 'launch'\n"
        f"- 'url' param: extract the website name after 'open'\n"
        f"- 'query' param: extract the search query after 'search'\n"
        f"- If a param value is not found in text, set it to null and list it in 'missing'.\n"
        f"- Be thorough — extract every possible parameter from the full text.\n"
    )


def _json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        value = match.group(0)
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def extract_parameters(text: str, intent: str) -> dict[str, Any]:
    api_key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not api_key:
        return {"slots": {}, "missing": []}
    if (os.getenv("GROQ_INTENT_V2_ENABLED", "true") or "").strip().lower() in {"0", "false", "no", "off"}:
        return {"slots": {}, "missing": []}
    try:
        from engine.groq_intent_planner import get_model_config, _intent_max_retries, _intent_timeout_seconds
        model = get_model_config().get("intent_model", "openai/gpt-oss-20b")
    except Exception:
        model = "openai/gpt-oss-20b"
        _intent_max_retries = lambda: 1
        _intent_timeout_seconds = lambda: 4.0
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 320,
        "messages": [
            {"role": "system", "content": _load_prompt(intent)},
            {"role": "user", "content": json.dumps({"text": text, "intent": intent})},
        ],
    }
    try:
        response = None
        retries = _intent_max_retries()
        for attempt in range(retries + 1):
            try:
                response = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json=payload,
                    timeout=_intent_timeout_seconds(),
                )
            except Exception:
                if attempt == retries:
                    raise
                continue
            if response.status_code < 500 or attempt == retries:
                break
        if response is None:
            return {"slots": {}, "missing": []}
        if response.status_code >= 400:
            return {"slots": {}, "missing": []}
        raw = _json_object(response.json()["choices"][0]["message"]["content"])
        slots = raw.get("slots") if isinstance(raw.get("slots"), dict) else {}
        missing = raw.get("missing") if isinstance(raw.get("missing"), list) else []
        return {"slots": slots, "missing": missing}
    except Exception:
        return {"slots": {}, "missing": []}
