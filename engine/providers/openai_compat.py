"""Shared OpenAI-compatible chat-completions HTTP for intent providers.

Both Groq (api.groq.com/openai/v1) and xAI Grok (api.x.ai/v1) expose the same
OpenAI REST surface: POST /chat/completions with messages, optional
response_format (json_schema) and tools/tool_choice. We use `requests` directly
because requirements.txt pins openai<1 (modern SDK not available yet).
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import requests

from engine.providers.base import ProviderResult


def _extract_json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        value = match.group(0)
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


def chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    messages: list[dict[str, Any]],
    provider_name: str,
    temperature: float = 0.0,
    max_tokens: int = 512,
    timeout: float = 4.0,
    response_format: dict[str, Any] | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | None = None,
    max_retries: int = 2,
) -> ProviderResult:
    """Call an OpenAI-compatible chat endpoint and normalize into ProviderResult.

    Never logs the api_key, request body, or response body — only status codes
    and error class names.
    """
    if not api_key:
        return ProviderResult.failure("missing_api_key", provider=provider_name, model=model)

    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if tools is not None:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice or "auto"
        payload["parallel_tool_calls"] = False

    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 429:
                # Rate-limited. For real-time intent routing, retrying within
                # seconds rarely clears a per-minute limit and just burns more
                # quota + adds latency — fail fast so the caller falls back to the
                # deterministic router instantly. Opt back in with GROQ_INTENT_RETRY_ON_429=1.
                retry_429 = os.getenv("GROQ_INTENT_RETRY_ON_429", "").strip().lower() in ("1", "true", "yes")
                if retry_429 and attempt < max_retries:
                    backoff = 2 ** attempt
                    print(f"[{provider_name.upper()}] rate_limited retry_in={backoff}s attempt={attempt + 1}/{max_retries}", flush=True)
                    time.sleep(backoff)
                    continue
                print(f"[{provider_name.upper()}] rate_limited status=429 fast_fallback", flush=True)
                return ProviderResult.failure("http_429", provider=provider_name, model=model)
            if response.status_code >= 400:
                print(f"[{provider_name.upper()}] http_failed status={response.status_code}", flush=True)
                return ProviderResult.failure(f"http_{response.status_code}", provider=provider_name, model=model)

            body = response.json()
            message = body["choices"][0]["message"]

            # Tool / function call path.
            calls = message.get("tool_calls") or []
            if calls:
                call = calls[0]
                fn = call.get("function", {})
                args_raw = fn.get("arguments") or "{}"
                try:
                    args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw or {})
                except Exception:
                    args = {}
                return ProviderResult(
                    ok=True,
                    tool_call={"name": str(fn.get("name") or ""), "arguments": args if isinstance(args, dict) else {}},
                    provider=provider_name,
                    model=model,
                )

            content = message.get("content") or ""
            try:
                decision = _extract_json_object(content)
            except json.JSONDecodeError:
                print(f"[{provider_name.upper()}] json_valid=false", flush=True)
                return ProviderResult.failure("invalid_json", provider=provider_name, model=model)
            return ProviderResult(ok=True, decision=decision, raw_text=content, provider=provider_name, model=model)

        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt < max_retries:
                backoff = 2 ** attempt
                print(f"[{provider_name.upper()}] transient={type(exc).__name__} retry_in={backoff}s attempt={attempt + 1}/{max_retries}", flush=True)
                time.sleep(backoff)
                continue
            print(f"[{provider_name.upper()}] failed reason={type(exc).__name__}", flush=True)
            return ProviderResult.failure(type(exc).__name__, provider=provider_name, model=model)
        except Exception as exc:
            print(f"[{provider_name.upper()}] failed reason={type(exc).__name__}", flush=True)
            return ProviderResult.failure(type(exc).__name__, provider=provider_name, model=model)
    return ProviderResult.failure("exhausted_retries", provider=provider_name, model=model)
