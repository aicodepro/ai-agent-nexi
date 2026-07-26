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


# A single voice turn calls this module 4-6 times (router semantic tier, V2
# pre-router, tool-RAG, ReAct, studio intent). When the key is rate-limited each
# of those was a separate dead round-trip, so one turn paid ~6x the timeout and
# still fell back. The first 429 now opens a short breaker and the rest of the
# turn short-circuits locally.
# ponytail: process-local dict, no lock - worst case two threads both probe once.
_BREAKER_UNTIL: dict[str, float] = {}
_BREAKER_DEFAULT_S = 20.0


def _breaker_open_for(provider_name: str) -> float:
    """Seconds remaining on this provider's cooldown, 0.0 if it may be called."""
    return max(0.0, _BREAKER_UNTIL.get(provider_name, 0.0) - time.monotonic())


def _trip_breaker(provider_name: str, retry_after: str | None) -> None:
    cooldown = _BREAKER_DEFAULT_S
    try:
        # Providers report the real reset window; prefer it over our guess.
        if retry_after:
            cooldown = max(1.0, min(300.0, float(retry_after)))
    except (TypeError, ValueError):
        pass
    _BREAKER_UNTIL[provider_name] = time.monotonic() + cooldown
    print(f"[{provider_name.upper()}] breaker_open cooldown={cooldown:.0f}s", flush=True)


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
    extra_headers: dict[str, str] | None = None,
) -> ProviderResult:
    """Call an OpenAI-compatible chat endpoint and normalize into ProviderResult.

    Never logs the api_key, request body, or response body — only status codes
    and error class names.
    """
    if not api_key:
        return ProviderResult.failure("missing_api_key", provider=provider_name, model=model)

    cooling = _breaker_open_for(provider_name)
    if cooling > 0:
        print(f"[{provider_name.upper()}] breaker_skip retry_in={cooling:.0f}s", flush=True)
        return ProviderResult.failure("rate_limited", provider=provider_name, model=model)

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
    if extra_headers:
        # provider-specific, non-auth headers (e.g. OpenRouter's HTTP-Referer/X-Title).
        # Never let them clobber Authorization/Content-Type.
        for k, v in extra_headers.items():
            if k not in ("Authorization", "Content-Type"):
                headers[k] = v

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
                _trip_breaker(provider_name, response.headers.get("Retry-After"))
                return ProviderResult.failure("rate_limited", provider=provider_name, model=model)
            if response.status_code >= 400:
                print(f"[{provider_name.upper()}] http_failed status={response.status_code}", flush=True)
                return ProviderResult.failure(f"http_{response.status_code}", provider=provider_name, model=model)

            body = response.json()
            message = body["choices"][0]["message"]
            if not isinstance(message, dict):
                return ProviderResult.failure("invalid_message", provider=provider_name, model=model)
            assistant_message = dict(message)
            assistant_message["role"] = "assistant"

            # Tool / function call path.
            calls = message.get("tool_calls") or []
            if calls:
                if not isinstance(calls, list) or len(calls) != 1:
                    return ProviderResult.failure("parallel_tool_calls_not_supported", provider=provider_name, model=model)
                call = calls[0]
                if not isinstance(call, dict):
                    return ProviderResult.failure("invalid_tool_call", provider=provider_name, model=model)
                fn = call.get("function", {})
                if not isinstance(fn, dict) or not isinstance(fn.get("name"), str) or not fn.get("name"):
                    return ProviderResult.failure("invalid_tool_call", provider=provider_name, model=model)
                # Normalize the arguments. Different models return "no arguments"
                # differently: {} (gpt-oss, scout), "" or the literal "null"
                # (llama-3.3), or JSON null — all of which mean an empty argument
                # object for a zero-slot tool. Only genuinely malformed, non-object
                # arguments are rejected.
                args_raw = fn.get("arguments")
                if isinstance(args_raw, dict):
                    args = dict(args_raw)
                else:
                    text = (args_raw if isinstance(args_raw, str) else "").strip()
                    if text.lower() in ("", "null", "none"):
                        args = {}
                    else:
                        try:
                            parsed = json.loads(text)
                        except Exception:
                            return ProviderResult.failure("invalid_tool_arguments", provider=provider_name, model=model)
                        if parsed is None:
                            args = {}
                        elif isinstance(parsed, dict):
                            args = parsed
                        else:
                            return ProviderResult.failure("invalid_tool_arguments", provider=provider_name, model=model)
                return ProviderResult(
                    ok=True,
                    tool_call={"id": str(call.get("id") or ""), "name": fn["name"], "arguments": args},
                    assistant_message=assistant_message,
                    provider=provider_name,
                    model=model,
                )

            content = str(message.get("content") or "")
            try:
                decision = _extract_json_object(content)
            except json.JSONDecodeError:
                if tools is not None and content:
                    return ProviderResult(
                        ok=True,
                        raw_text=content,
                        assistant_message=assistant_message,
                        provider=provider_name,
                        model=model,
                    )
                print(f"[{provider_name.upper()}] json_valid=false", flush=True)
                return ProviderResult.failure("invalid_json", provider=provider_name, model=model)
            return ProviderResult(ok=True, decision=decision, raw_text=content, assistant_message=assistant_message, provider=provider_name, model=model)

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
