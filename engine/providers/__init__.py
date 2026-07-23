"""Intent-routing LLM provider boundary.

Keeps provider HTTP details out of the router. Three providers ship today:

- groq  : groq.com inference (existing GROQ_API_KEY behaviour).
- xai_grok : xAI / Grok (XAI_API_KEY, https://api.x.ai/v1).
- openrouter : one key -> every vendor (OPENROUTER_API_KEY, openrouter.ai). This is
  what lets NEXI switch to any model per task instead of only the Groq-hosted set.

Grok/Groq/OpenRouter classify or request a tool call only — Nexi executes local
actions itself through engine.tool_registry.execute_tool().
"""
from __future__ import annotations

import os

from engine.providers.base import IntentProvider, ProviderResult


class _UnavailableProvider(IntentProvider):
    def __init__(self, name: str):
        self.name = name

    def route_with_schema(self, messages, schema, *, model="", timeout=4.0) -> ProviderResult:
        return ProviderResult.failure("unknown_provider", provider=self.name, model=model)

    def route_with_tools(self, messages, tools, *, model="", timeout=4.0, tool_choice="auto") -> ProviderResult:
        return ProviderResult.failure("unknown_provider", provider=self.name, model=model)


def get_intent_provider(name: str | None = None) -> IntentProvider | None:
    """Return the configured intent provider, or None for deterministic-only."""
    choice = (name or os.getenv("INTENT_ROUTER_PROVIDER", "groq") or "groq").strip().lower()
    if choice in {"none", "deterministic", "off", "disabled"}:
        return None
    if choice in {"xai", "xai_grok", "grok"}:
        from engine.providers.xai_grok_provider import XaiGrokProvider

        return XaiGrokProvider()
    if choice in {"openrouter", "open_router", "or"}:
        from engine.providers.openrouter_provider import OpenRouterProvider

        return OpenRouterProvider()
    if choice == "groq":
        from engine.providers.groq_provider import GroqProvider

        return GroqProvider()
    return _UnavailableProvider(choice)


__all__ = ["IntentProvider", "ProviderResult", "get_intent_provider"]
