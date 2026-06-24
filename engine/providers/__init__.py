"""Intent-routing LLM provider boundary.

Keeps provider HTTP details out of the router. Two providers ship today:

- groq  : groq.com inference (existing GROQ_API_KEY behaviour).
- xai_grok : xAI / Grok (XAI_API_KEY, https://api.x.ai/v1).

Grok/Groq classify or request a tool call only — Nexi executes local actions
itself through engine.tool_registry.execute_tool().
"""
from __future__ import annotations

import os

from engine.providers.base import IntentProvider, ProviderResult


def get_intent_provider(name: str | None = None) -> IntentProvider | None:
    """Return the configured intent provider, or None for deterministic-only."""
    choice = (name or os.getenv("INTENT_ROUTER_PROVIDER", "groq") or "groq").strip().lower()
    if choice in {"none", "deterministic", "off", "disabled"}:
        return None
    if choice in {"xai", "xai_grok", "grok"}:
        from engine.providers.xai_grok_provider import XaiGrokProvider

        return XaiGrokProvider()
    from engine.providers.groq_provider import GroqProvider

    return GroqProvider()


__all__ = ["IntentProvider", "ProviderResult", "get_intent_provider"]
