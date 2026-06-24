"""Provider interface for LLM-assisted intent routing.

Providers are thin HTTP boundaries. They never execute actions and never log
secrets. A provider returns a ProviderResult; the router validates it against
engine.intent_taxonomy before anything runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProviderResult:
    ok: bool
    # Parsed router decision dict (structured-output mode), if any.
    decision: dict[str, Any] | None = None
    # Tool call requested by the model (function-calling mode), if any.
    tool_call: dict[str, Any] | None = None
    error_code: str = ""
    raw_text: str = ""
    provider: str = ""
    model: str = ""

    @classmethod
    def failure(cls, error_code: str, *, provider: str = "", model: str = "") -> "ProviderResult":
        return cls(ok=False, error_code=error_code, provider=provider, model=model)


class IntentProvider:
    """Base class. Subclasses implement route_with_schema / route_with_tools."""

    name: str = "base"

    def is_available(self) -> bool:  # pragma: no cover - trivial
        return False

    def route_with_schema(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
        *,
        model: str = "",
        timeout: float = 4.0,
    ) -> ProviderResult:
        raise NotImplementedError

    def route_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str = "",
        timeout: float = 4.0,
        tool_choice: str = "auto",
    ) -> ProviderResult:
        raise NotImplementedError
