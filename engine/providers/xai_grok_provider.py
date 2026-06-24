"""xAI / Grok intent provider (https://api.x.ai/v1).

Uses XAI_API_KEY. OpenAI-REST-compatible, so it supports response_format
json_schema and tools/tool_choice. Grok only classifies or requests a tool
call — it never executes OS actions. Jarvis executes locally via the registry.
"""
from __future__ import annotations

import os
from typing import Any

from engine.providers.base import IntentProvider, ProviderResult
from engine.providers.openai_compat import chat_completion


class XaiGrokProvider(IntentProvider):
    name = "xai_grok"

    def _base_url(self) -> str:
        return (os.getenv("XAI_GROK_BASE_URL", "https://api.x.ai/v1") or "https://api.x.ai/v1").strip()

    def _model(self, override: str = "") -> str:
        if override:
            return override
        return os.getenv("XAI_GROK_INTENT_MODEL", "grok-3-mini")

    def _api_key(self) -> str:
        return (os.getenv("XAI_API_KEY") or "").strip()

    def is_available(self) -> bool:
        return bool(self._api_key())

    def _timeout(self, timeout: float) -> float:
        return float(os.getenv("XAI_GROK_TIMEOUT_SECONDS", str(timeout)))

    def route_with_schema(self, messages, schema, *, model="", timeout=4.0) -> ProviderResult:
        response_format: dict[str, Any] = {
            "type": "json_schema",
            "json_schema": {
                "name": "router_decision",
                "strict": True,
                "schema": schema,
            },
        }
        return chat_completion(
            base_url=self._base_url(),
            api_key=self._api_key(),
            model=self._model(model),
            messages=messages,
            provider_name=self.name,
            temperature=float(os.getenv("XAI_GROK_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("XAI_GROK_MAX_TOKENS", "512")),
            timeout=self._timeout(timeout),
            response_format=response_format,
            max_retries=max(0, int(os.getenv("XAI_GROK_MAX_RETRIES", "2"))),
        )

    def route_with_tools(self, messages, tools, *, model="", timeout=4.0, tool_choice="auto") -> ProviderResult:
        return chat_completion(
            base_url=self._base_url(),
            api_key=self._api_key(),
            model=self._model(model),
            messages=messages,
            provider_name=self.name,
            temperature=float(os.getenv("XAI_GROK_TEMPERATURE", "0")),
            max_tokens=int(os.getenv("XAI_GROK_MAX_TOKENS", "512")),
            timeout=self._timeout(timeout),
            tools=tools,
            tool_choice=tool_choice,
            max_retries=max(0, int(os.getenv("XAI_GROK_MAX_RETRIES", "2"))),
        )
