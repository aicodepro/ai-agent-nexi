"""Adapter registry and runtime capability discovery."""

from __future__ import annotations

import os
import threading
from typing import Any

from engine.agent_runtime.adapters import BUILTIN_ADAPTERS
from engine.agent_runtime.contracts import AgentRuntimeAdapter


_ALIASES = {
    "claude": "claude-code",
    "claude_code": "claude-code",
    "open-code": "opencode",
    "hermes-agent": "hermes",
    "open-claw": "openclaw",
    "anti-gravity": "antigravity",
    "google-antigravity": "antigravity",
    "custom": "custom-cli",
}
_ADAPTERS: dict[str, AgentRuntimeAdapter] = {}
_LOCK = threading.RLock()


def canonical_provider_id(value: str | None) -> str:
    provider = str(value or "claude-code").strip().lower()
    provider = _ALIASES.get(provider, provider)
    if provider not in BUILTIN_ADAPTERS and provider not in _ADAPTERS:
        raise ValueError(f"Unknown Nexi agent runtime provider: {provider}")
    return provider


def selected_provider_id() -> str:
    return canonical_provider_id(os.getenv("NEXI_AGENT_RUNTIME_PROVIDER") or "claude-code")


def register_adapter(adapter: AgentRuntimeAdapter) -> None:
    provider = canonical_provider_id(adapter.provider_id) if adapter.provider_id in BUILTIN_ADAPTERS else str(adapter.provider_id)
    with _LOCK:
        _ADAPTERS[provider] = adapter


def get_adapter(provider_id: str | None = None) -> AgentRuntimeAdapter:
    provider = canonical_provider_id(provider_id or selected_provider_id())
    with _LOCK:
        adapter = _ADAPTERS.get(provider)
        if adapter is None:
            adapter = BUILTIN_ADAPTERS[provider]()
            _ADAPTERS[provider] = adapter
        return adapter


def runtime_enabled(provider_id: str | None = None) -> bool:
    provider = canonical_provider_id(provider_id or selected_provider_id())
    generic = os.getenv("NEXI_AGENT_RUNTIME_ENABLED")
    if generic is not None and str(generic).strip() != "":
        return str(generic).strip().lower() in {"1", "true", "yes", "on"}
    if provider == "claude-code":
        return str(os.getenv("NEXI_CLAUDE_CODE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}
    return False


def validate_session_id(provider_id: str, value: str | None) -> str:
    return get_adapter(provider_id).validate_session_id(value)


def provider_status(provider_id: str | None = None) -> dict[str, Any]:
    provider = canonical_provider_id(provider_id or selected_provider_id())
    adapter = get_adapter(provider)
    return {
        "provider_id": provider,
        "selected": provider == selected_provider_id(),
        "enabled": runtime_enabled(provider),
        "available": adapter.available(),
        "capabilities": adapter.capabilities.as_dict(),
    }


def all_provider_statuses() -> list[dict[str, Any]]:
    return [provider_status(provider) for provider in BUILTIN_ADAPTERS]


def reset_for_tests() -> None:
    with _LOCK:
        _ADAPTERS.clear()
