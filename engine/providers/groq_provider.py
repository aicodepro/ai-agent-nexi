"""Groq intent provider (groq.com). Preserves existing GROQ_API_KEY behaviour."""
from __future__ import annotations

import os
from typing import Any

from engine.providers.base import IntentProvider, ProviderResult
from engine.providers.openai_compat import chat_completion

BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(IntentProvider):
    name = "groq"

    def _model(self, override: str = "") -> str:
        if override:
            return override
        return os.getenv("GROQ_INTENT_MODEL", "openai/gpt-oss-20b")

    def _api_key(self) -> str:
        return (os.getenv("GROQ_API_KEY") or "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key())

    def route_with_schema(self, messages, schema, *, model="", timeout=4.0) -> ProviderResult:
        # Groq's gpt-oss models accept response_format json_object reliably; we
        # still validate against the taxonomy downstream.
        response_format: dict[str, Any] = {"type": "json_object"}
        return chat_completion(
            base_url=BASE_URL,
            api_key=self._api_key(),
            model=self._model(model),
            messages=messages,
            provider_name=self.name,
            temperature=float(os.getenv("GROQ_INTENT_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("GROQ_INTENT_MAX_TOKENS", "512")),
            timeout=float(os.getenv("GROQ_INTENT_TIMEOUT_SECONDS", str(timeout))),
            response_format=response_format,
            max_retries=max(0, int(os.getenv("GROQ_INTENT_MAX_RETRIES", "2"))),
        )

    def route_with_tools(self, messages, tools, *, model="", timeout=4.0, tool_choice="auto") -> ProviderResult:
        return chat_completion(
            base_url=BASE_URL,
            api_key=self._api_key(),
            model=self._model(model),
            messages=messages,
            provider_name=self.name,
            temperature=float(os.getenv("GROQ_INTENT_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("GROQ_INTENT_MAX_TOKENS", "512")),
            timeout=float(os.getenv("GROQ_INTENT_TIMEOUT_SECONDS", str(timeout))),
            tools=tools,
            tool_choice=tool_choice,
            max_retries=max(0, int(os.getenv("GROQ_INTENT_MAX_RETRIES", "2"))),
        )
