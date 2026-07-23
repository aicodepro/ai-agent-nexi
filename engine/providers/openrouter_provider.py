"""OpenRouter intent/chat provider (openrouter.ai).

One API key, every model: OpenRouter is an OpenAI-compatible gateway in front of
Anthropic, OpenAI, Google, Meta, and dozens of free models. This is what lets NEXI
actually "switch any model per task" (orchestration / code / test) instead of being
pinned to Groq + Gemini — the model_registry picks the id, this provider dispatches
it. Same REST surface as Groq/xAI, so it reuses openai_compat.chat_completion.
"""
from __future__ import annotations

import os
from typing import Any

from engine.providers.base import IntentProvider, ProviderResult
from engine.providers.openai_compat import chat_completion

BASE_URL = "https://openrouter.ai/api/v1"


def _openrouter_headers() -> dict[str, str]:
    # OpenRouter uses these only for its public leaderboard; both optional. Kept
    # configurable so a deployment can attribute usage, never required to work.
    headers: dict[str, str] = {}
    referer = (os.getenv("OPENROUTER_SITE_URL") or "").strip()
    title = (os.getenv("OPENROUTER_APP_TITLE") or "NEXI").strip()
    if referer:
        headers["HTTP-Referer"] = referer
    if title:
        headers["X-Title"] = title
    return headers


class OpenRouterProvider(IntentProvider):
    name = "openrouter"

    def _model(self, override: str = "") -> str:
        if override:
            return override
        # A sensible free default so it works out of the box with just a key.
        return os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")

    def _api_key(self) -> str:
        return (os.getenv("OPENROUTER_API_KEY") or "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key())

    def route_with_schema(self, messages, schema, *, model="", timeout=8.0) -> ProviderResult:
        # Most OpenRouter models accept json_object; a few reject it, in which case
        # chat_completion returns http_400 and the caller falls back — same contract
        # as Groq's gpt-oss quirk.
        return chat_completion(
            base_url=BASE_URL,
            api_key=self._api_key(),
            model=self._model(model),
            messages=messages,
            provider_name=self.name,
            temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "512")),
            timeout=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", str(timeout))),
            response_format={"type": "json_object"},
            max_retries=max(0, int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))),
            extra_headers=_openrouter_headers(),
        )

    def route_with_tools(self, messages, tools, *, model="", timeout=8.0, tool_choice="auto") -> ProviderResult:
        return chat_completion(
            base_url=BASE_URL,
            api_key=self._api_key(),
            model=self._model(model),
            messages=messages,
            provider_name=self.name,
            temperature=float(os.getenv("OPENROUTER_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("OPENROUTER_MAX_TOKENS", "512")),
            timeout=float(os.getenv("OPENROUTER_TIMEOUT_SECONDS", str(timeout))),
            tools=tools,
            tool_choice=tool_choice,
            max_retries=max(0, int(os.getenv("OPENROUTER_MAX_RETRIES", "2"))),
            extra_headers=_openrouter_headers(),
        )
