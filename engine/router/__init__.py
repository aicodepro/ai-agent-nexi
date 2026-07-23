"""Master Intent Router — a single, tiered, calibrated front door for NEXI.

Design: docs/superpowers/specs/2026-07-13-master-intent-router-design.md

Tiers (cheapest-first, fail-open downward):
    0a  deterministic guards       (see engine.intent_pre_router — wired later)
    0b  local semantic router      (this package: embeddings + exemplar bank)   ← built
    1   gpt-oss-20b adjudication    (injectable llm hook — wired later)
    2   gpt-oss-120b escalation     (injectable llm hook — wired later)

Public entry:
    from engine.router import route
    decision = route("open chrome")      # -> engine.router.decision.Decision

The Decision carries the canonical intent_taxonomy schema dict at `.result`
(so existing dispatch keeps working) plus router metadata (tier/band/margin).

This package runs in SHADOW MODE first: it produces a decision alongside the
live router without taking the wheel, so it can be scored before going live.
"""
from __future__ import annotations

import threading

from .decision import Decision, Candidate  # noqa: F401

__all__ = ["route", "Decision", "Candidate", "get_router"]

_ROUTER = None
_ROUTER_LOCK = threading.Lock()


def get_router():
    """Lazily build the process-wide router (builds the exemplar bank once).

    Double-checked lock: the shadow observer routes from background threads, so
    two first-calls must not both build (and double-load the embedding model).
    """
    global _ROUTER
    if _ROUTER is None:
        with _ROUTER_LOCK:
            if _ROUTER is None:
                from .pipeline import Pipeline
                _ROUTER = Pipeline.build()
    return _ROUTER


def route(text: str, ctx: dict | None = None) -> Decision:
    """Route one utterance to a Decision. Never raises for ordinary input."""
    return get_router().route(text, ctx or {})
