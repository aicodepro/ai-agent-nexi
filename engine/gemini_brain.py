from __future__ import annotations

import os
from pathlib import Path

import requests


DEFAULT_GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]
PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "nexi_system_prompt.txt"
GEMINI_PROMPT_PATH = Path(__file__).resolve().parents[1] / "prompts" / "nexi_gemini_brain_system_prompt.txt"
DEFAULT_SYSTEM_PROMPT = (
    "You are Nexi, a concise Windows desktop assistant. Answer directly, "
    "do not reveal hidden reasoning, and never claim to execute local actions."
)


class GeminiConfigurationError(RuntimeError):
    pass


class GeminiRuntimeError(RuntimeError):
    pass


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _api_key() -> str:
    return (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()


def is_gemini_configured() -> bool:
    return bool(_api_key())


def get_gemini_model_chain() -> list[str]:
    raw = (
        os.getenv("GEMINI_MODEL_CHAIN")
        or ",".join([os.getenv("GEMINI_MODEL_PRIMARY", ""), os.getenv("GEMINI_MODEL_FALLBACK", "")]).strip(",")
        or os.getenv("GEMINI_MODEL")
        or ""
    ).strip()
    if not raw:
        return list(DEFAULT_GEMINI_MODELS)
    models = [item.strip() for item in raw.split(",") if item.strip()]
    return models or list(DEFAULT_GEMINI_MODELS)


def _load_system_prompt() -> str:
    from engine.prompt_loader import load_prompt_file

    return load_prompt_file(str(GEMINI_PROMPT_PATH), load_prompt_file(str(PROMPT_PATH), DEFAULT_SYSTEM_PROMPT))


def _extract_text(data: dict) -> str:
    parts = []
    for candidate in data.get("candidates", []) or []:
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            text = part.get("text")
            if text:
                parts.append(str(text))
    return "\n".join(parts).strip()


def _build_cognitive_context(user_prompt: str, max_chars: int = 3500) -> tuple[str, int, int, bool]:
    parts = []
    working_turns = 0
    training_count = 0
    user_model_present = False
    try:
        from engine.conversation_context import get_recent_turns, get_working_memory
        turns = get_recent_turns(10)
        working_turns = len(turns)
        working = get_working_memory(limit=10, max_chars=1400)
        if working:
            parts.append("Working memory:\n" + working)
    except Exception:
        pass
    try:
        from engine.user_model import get_user_model_context
        user_model = get_user_model_context(max_chars=700)
        if user_model:
            user_model_present = True
            parts.append("User model:\n" + user_model)
    except Exception:
        pass
    try:
        from engine.training_rules import get_relevant_training_context, list_training_rules
        training_count = len([r for r in list_training_rules() if r.get("enabled", True)])
        rules = get_relevant_training_context(user_prompt, limit=5, max_chars=700)
        if rules:
            parts.append("Relevant training rules:\n" + rules)
    except Exception:
        pass
    try:
        from engine.cognitive_context import get_last_strategy
        strategy = get_last_strategy()
        if strategy:
            parts.append(
                "Current goal state:\n"
                f"route={strategy.get('chosen_route', '')}; intent={strategy.get('chosen_intent', '')}; "
                f"confidence={float(strategy.get('confidence', 0.0) or 0.0):.2f}; reason={strategy.get('reason', '')}"
            )
            profile = strategy.get("active_need_profile") or {}
            if strategy.get("detected_need") or profile:
                profile_rules = "; ".join(str(rule) for rule in (strategy.get("profile_rules_used") or profile.get("rules") or [])[:6])
                examples = profile.get("examples") or []
                positive = [item.get("text", "")[:120] for item in examples if item.get("type") == "example_rule"][:2]
                negative = [item.get("text", "")[:120] for item in examples if item.get("type") == "negative_example_rule"][:2]
                parts.append(
                    "Training profile context:\n"
                    f"current_need={strategy.get('detected_need') or profile.get('need_name', '')}; "
                    f"training_level={strategy.get('training_level', profile.get('level', 'medium'))}; "
                    f"style={strategy.get('style') or profile.get('style', '')}; "
                    f"output_preference={strategy.get('output_preference') or profile.get('output_preference', '')}\n"
                    f"rules={profile_rules}\n"
                    f"ideal_traits={'; '.join(positive)}\n"
                    f"negative_traits={'; '.join(negative)}"
                )
    except Exception:
        pass
    try:
        from engine.need_training_manager import get_active_need
        active_need = get_active_need()
        if active_need:
            parts.append(f"Active training session: {active_need}. Capture safe corrections and examples only.")
    except Exception:
        pass
    try:
        from engine.training_evaluator import get_training_score, get_weak_areas
        score = get_training_score()
        weak = get_weak_areas()[:3]
        if score.get("evaluation_count", 0):
            parts.append(
                "Training evaluation summary:\n"
                f"score={score.get('overall_score')}; evaluations={score.get('evaluation_count')}; "
                f"weak_areas={', '.join(item.get('area', '') for item in weak)}"
            )
    except Exception:
        pass
    parts.append("Tool boundary: do not claim local actions succeeded unless a verified Nexi tool result is present.")
    compact = "\n\n".join(parts)[:max_chars]
    print(f"[BRAIN] cognitive_context chars={len(compact)}", flush=True)
    print(f"[BRAIN] working_turns={working_turns}", flush=True)
    print(f"[BRAIN] training_rules={training_count}", flush=True)
    print(f"[BRAIN] user_model={str(user_model_present).lower()}", flush=True)
    return compact, working_turns, training_count, user_model_present


def _memory_sections(user_prompt: str, context: str | None, max_chars: int = 4300) -> tuple[str, int, int]:
    parts = []
    turn_count = 0
    memory_count = 0
    cognitive_context, cognitive_turns, _training_count, _user_model = _build_cognitive_context(user_prompt, max_chars=3500)
    if cognitive_context:
        parts.append("Cognitive context:\n" + cognitive_context)
        turn_count = cognitive_turns
    try:
        from engine.conversation_context import get_recent_context_text, get_recent_turns
        turns = get_recent_turns(10)
        recent = get_recent_context_text(limit=10, max_chars=2500)
        turn_count = max(turn_count, len(turns))
        if recent:
            parts.append("Recent conversation:\n" + recent)
    except Exception:
        pass
    try:
        from engine.adaptive_memory import recall, build_memory_context
        memories = recall(user_prompt, limit=8)
        memory_count = len(memories)
        memory_text = build_memory_context(user_prompt, limit=8, max_chars=1800)
        if memory_text:
            parts.append("Relevant user memory:\n" + memory_text)
    except Exception:
        pass
    try:
        from engine.output_actions import get_latest_output
        latest = get_latest_output()
        if latest.get("content"):
            summary = latest.get("summary") or latest.get("content", "")[:240]
            parts.append(f"Current output reference:\n{latest.get('title', 'Nexi Output')} ({latest.get('content_type', 'text')}): {summary}")
    except Exception:
        pass
    extra = str(context or "").strip()
    if extra:
        parts.append(extra)
    compact = "\n\n".join(parts)[:max_chars]
    print(f"[BRAIN] memory_context chars={len(compact)} turns={turn_count} memories={memory_count}", flush=True)
    return compact, turn_count, memory_count


def _build_prompt(prompt: str, context: str | None) -> str:
    user_prompt = str(prompt or "").strip()
    safe_context, _turns, _memories = _memory_sections(user_prompt, context)
    if not safe_context:
        return user_prompt
    return f"{safe_context}\n\nUser question:\n{user_prompt}"


def ask_gemini_vision(prompt: str, image_bytes: bytes, *, mime: str = "image/jpeg",
                      max_tokens: int | None = None) -> str:
    """Send an image + prompt to Gemini and return its text description.

    Gemini 2.5 Flash is multimodal, so screen vision reuses the SAME key and model
    chain as the text brain — no new client, no new dependency. The image rides as an
    inline_data part exactly like the REST docs' example; everything else mirrors
    ask_gemini so failures degrade the same way.
    """
    import base64

    api_key = _api_key()
    if not api_key:
        raise GeminiConfigurationError("gemini_api_key_missing")
    if not image_bytes:
        raise GeminiConfigurationError("empty_image")

    base_url = (os.getenv("GEMINI_API_BASE") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    timeout = _env_float("GEMINI_VISION_TIMEOUT_SECONDS", _env_float("GEMINI_TIMEOUT_SECONDS", 20.0))
    b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": str(prompt or "Describe what is on this screen.")},
                    {"inline_data": {"mime_type": mime, "data": b64}},
                ],
            }
        ],
        "generationConfig": {
            "temperature": _env_float("GEMINI_VISION_TEMPERATURE", 0.2),
            "maxOutputTokens": max_tokens or _env_int("GEMINI_VISION_MAX_TOKENS", 400),
        },
    }

    last_reason = "unknown"
    for model in get_gemini_model_chain():
        print(f"[VISION] provider=gemini model={model} request_started img_kb={len(image_bytes)//1024}")
        try:
            response = requests.post(
                f"{base_url}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},   # header, not ?key= — keeps the key out of URLs/logs
                json=payload,
                timeout=timeout,
            )
            if response.status_code >= 400:
                last_reason = f"http_{response.status_code}"
                print(f"[VISION] provider=gemini model={model} failed reason={last_reason}")
                continue
            text = _extract_text(response.json())
            if text:
                print(f"[VISION] provider=gemini model={model} success")
                return text
            last_reason = "empty_response"
        except requests.Timeout:
            last_reason = "timeout"
        except Exception as e:
            last_reason = type(e).__name__
        print(f"[VISION] provider=gemini model={model} failed reason={last_reason}")
    raise GeminiRuntimeError(last_reason)


def ask_gemini(prompt: str, *, context: str | None = None) -> str:
    api_key = _api_key()
    if not api_key:
        raise GeminiConfigurationError("gemini_api_key_missing")
    user_prompt = str(prompt or "").strip()
    if not user_prompt:
        raise GeminiConfigurationError("empty_prompt")

    base_url = (os.getenv("GEMINI_API_BASE") or "https://generativelanguage.googleapis.com/v1beta").rstrip("/")
    timeout = _env_float("GEMINI_TIMEOUT_SECONDS", 20.0)
    payload = {
        "systemInstruction": {"parts": [{"text": _load_system_prompt()}]},
        "contents": [
            {
                "role": "user",
                "parts": [{"text": _build_prompt(user_prompt, context)}],
            }
        ],
        "generationConfig": {
            "temperature": _env_float("GEMINI_TEMPERATURE", 0.35),
            "maxOutputTokens": _env_int("GEMINI_MAX_OUTPUT_TOKENS", 512),
        },
    }

    last_reason = "unknown"
    for model in get_gemini_model_chain():
        print(f"[BRAIN] provider=gemini model={model} request_started")
        try:
            response = requests.post(
                f"{base_url}/models/{model}:generateContent",
                headers={"x-goog-api-key": api_key},   # header, not ?key= — keeps the key out of URLs/logs
                json=payload,
                timeout=timeout,
            )
            if response.status_code >= 400:
                last_reason = f"http_{response.status_code}"
                print(f"[BRAIN] provider=gemini model={model} failed reason={last_reason}")
                continue
            text = _extract_text(response.json())
            if text:
                print(f"[BRAIN] provider=gemini model={model} success")
                return text
            last_reason = "empty_response"
            print(f"[BRAIN] provider=gemini model={model} failed reason=empty_response")
        except requests.Timeout:
            last_reason = "timeout"
            print(f"[BRAIN] provider=gemini model={model} failed reason=timeout")
        except Exception as e:
            last_reason = type(e).__name__
            print(f"[BRAIN] provider=gemini model={model} failed reason={last_reason}")
    raise GeminiRuntimeError(last_reason)
