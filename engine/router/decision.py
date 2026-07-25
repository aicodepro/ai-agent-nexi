"""The Decision object the Master Router returns.

It wraps the canonical intent_taxonomy schema dict (`.result`) so downstream
dispatch (`engine.command`, `engine.tool_registry.execute_tool`) keeps working
unchanged, and adds router-only observability fields (tier/band/margin/…) that
the fixed 14-field schema can't hold. Non-invasive: we do NOT change the live
schema in engine.intent_taxonomy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from engine import intent_taxonomy as tax


@dataclass
class Candidate:
    """One ranked intent option from the semantic layer."""
    intent: str
    domain: str
    route: str
    score: float
    stakes: str = "low"  # low | medium | high


@dataclass
class Decision:
    result: dict[str, Any]                       # canonical intent_taxonomy schema dict
    band: str = "chat"                           # act | confirm | ask | chat
    tier: int = 0                                # 0 semantic, 1 gpt-oss-20b, 2 gpt-oss-120b
    sim: float = 0.0                             # top similarity
    margin: float = 0.0                          # top1 - top2 similarity
    candidates: list[Candidate] = field(default_factory=list)
    source: str = "semantic"                     # which layer decided
    escalated: bool = False
    plan: list = field(default_factory=list)     # for route=="react": ordered sub-Decisions

    # dict-like conveniences so callers can treat it like the old result dict
    def __getitem__(self, key: str) -> Any:
        return self.result[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.result.get(key, default)

    @property
    def route(self) -> str:
        return self.result["route"]

    @property
    def intent(self) -> str:
        return self.result["intent"]

    @property
    def confidence(self) -> float:
        return self.result["confidence"]


def route_for_intent(intent: str) -> str:
    """Map an intent name to its canonical route bucket."""
    if intent in tax.OUTPUT_INTENTS:
        return "output"
    if intent in tax.BRAIN_INTENTS or intent == "general_qa":
        return "brain"
    if intent in tax.TOOL_INTENTS:
        return "tool"
    # greetings/identity/social live outside the tool/brain sets — treat as chat
    return "brain"
