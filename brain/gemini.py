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


def _get_brain_config() -> dict:
    provider = cfg.jarvis.jarvis_brain_provider
    if provider == "claude":
        return {
            "api_base": "https://api.anthropic.com/v1",
            "model": "claude-opus-4-8",
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "max_tokens": 4096,
        }
    if provider == "deepseek":
        return {
            "api_base": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "api_key": cfg.jarvis.jarvis_brain_api_key,
        }
    return {
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "model": cfg.gemini_model_chain[0] if cfg.gemini_model_chain else "gemini-2.5-flash",
        "api_key": cfg.gemini_api_key,
    }


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

    # MCP available tools
    try:
        from tools.mcp import list_tools
        mcp = list_tools()
        if mcp:
            tool_lines = []
            for server, tools in mcp.items():
                if tools:
                    tool_lines.append(f"  {server}: {', '.join(tools)}")
            if tool_lines:
                sections.append(f"[Available Tools]\n" + "\n".join(tool_lines))
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
                f"{model}:generateContent"
            )
            body = {
                "contents": [{"parts": [{"text": full_prompt}]}],
                "generationConfig": {
                    "temperature": cfg.gemini_temperature,
                    "maxOutputTokens": cfg.gemini_max_tokens,
                },
            }
            headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
            resp = requests.post(url, json=body, headers=headers, timeout=15)
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
