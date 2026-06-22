"""Gemini brain — primary LLM Q&A engine with context injection."""

import os
import re
from pathlib import Path
from core.config import cfg

DEFAULT_SYSTEM_PROMPT = (
    f"You are {cfg.name}, an intelligent desktop AI assistant. "
    "Be concise, accurate, and helpful. If you don't know something, say so. "
    "Do not claim local actions succeeded unless a verified tool result is present. "
    "Keep responses under 500 words unless asked for more detail."
)


def is_configured() -> bool:
    return bool(cfg.gemini_api_key)


def _load_system_prompt() -> str:
    paths = [
        Path(__file__).resolve().parent.parent / "prompts" / "nexi_system_prompt.txt",
        Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt",
    ]
    for p in paths:
        if p.exists():
            text = p.read_text(encoding="utf-8").strip()
            if text:
                return text
    return DEFAULT_SYSTEM_PROMPT


def _extract_text(resp_json: dict) -> str:
    try:
        candidates = resp_json.get("candidates", [])
        if candidates:
            parts = candidates[0].get("content", {}).get("parts", [])
            if parts:
                return parts[0].get("text", "").strip()
    except (KeyError, IndexError, TypeError):
        pass
    return ""


def _build_context() -> str:
    """Build cognitive context from memory, conversation, and user model."""
    sections = []

    # Conversation context
    try:
        from memory.context import get_working_memory
        wm = get_working_memory(limit=8, max_chars=1800)
        if wm:
            sections.append(f"[Recent Conversation]\n{wm}")
    except Exception:
        pass

    # Adaptive memory
    try:
        from memory.manager import build_memory_context
        mc = build_memory_context("", limit=6, max_chars=600)
        if mc:
            sections.append(f"[Memory]\n{mc}")
    except Exception:
        pass

    # User model
    try:
        from memory.user_model import get_user_model_context
        uc = get_user_model_context(max_chars=400)
        if uc:
            sections.append(f"[User Preferences]\n{uc}")
    except Exception:
        pass

    return "\n\n".join(sections)


def _strip_reasoning(text: str) -> str:
    """Remove <think>...</think> tags from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"<reasoning>.*?</reasoning>", "", text, flags=re.DOTALL).strip()
    return text


def ask_gemini(query: str, context: str = "") -> str:
    """Ask Gemini with full context injection. Tries model chain with fallback."""
    if not is_configured():
        raise RuntimeError("Gemini API key not configured")

    system_prompt = _load_system_prompt()
    cognitive_context = _build_context()

    parts = [system_prompt]
    if cognitive_context:
        parts.append(cognitive_context)
    if context:
        parts.append(f"[Additional Context]\n{context}")
    parts.append(f"User: {query}")
    full_prompt = "\n\n".join(parts)

    api_key = cfg.gemini_api_key
    models = cfg.gemini_model_chain

    import requests
    last_error = None

    for model in models:
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model}:generateContent?key={api_key}"
            )
            body = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "temperature": cfg.gemini_temperature,
                    "maxOutputTokens": cfg.gemini_max_tokens,
                },
            }
            resp = requests.post(url, json=body, timeout=15)
            resp.raise_for_status()
            text = _extract_text(resp.json())
            if text:
                text = _strip_reasoning(text)
                print(f"[BRAIN] gemini ok model={model} len={len(text)}", flush=True)
                return text
            print(f"[BRAIN] gemini empty model={model}", flush=True)
        except Exception as e:
            last_error = e
            print(f"[BRAIN] gemini failed model={model} reason={type(e).__name__}", flush=True)

    raise RuntimeError(f"All Gemini models failed: {last_error}")


def ask_brain(query: str, context: str = "") -> str:
    """Public brain API — tries Gemini, returns answer text or error message."""
    try:
        return ask_gemini(query, context)
    except Exception as e:
        print(f"[BRAIN] all_failed reason={type(e).__name__}", flush=True)
        return "I'm having trouble connecting to my brain right now. Please try again."
