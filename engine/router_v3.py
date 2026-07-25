"""Authoritative Nexi Access routing facade.

Router V3 is the only live semantic-routing entry point. The mature V2 router is
kept as an internal compatibility tier while the semantic pipeline is calibrated;
callers must not invoke it directly.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from engine.intent_taxonomy import exact_schema


def _safe_log(message: str) -> None:
    print(message, flush=True)


@dataclass(frozen=True)
class RouterTrace:
    source: str
    duration_ms: float
    manifest_sha256: str
    route: str
    intent: str
    confidence: float


def _manifest_sha256() -> str:
    from engine.tool_registry import router_tool_manifest

    payload = json.dumps(
        router_tool_manifest(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class RouterV3:
    """One routing authority over the current compatibility tiers."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._last_trace: RouterTrace | None = None
        self._last_semantic_trace: dict | None = None

    def _route_text(self, clean: str, *, source: str, context: dict) -> tuple[dict[str, Any], str]:
        """Tiered routing. Exactly ONE tier produces the executed decision.

        1. lifecycle/approval - deterministic, never a network round-trip;
        2. semantic - structured LLM over retrieved capability manifests;
        3. v2 - fallback only when the semantic tier cannot decide.

        The V2 tier never runs when the semantic tier succeeds.
        """
        from engine.intent_taxonomy import empty_result
        from engine import router_semantic as semantic

        lifecycle = semantic.match_lifecycle(clean)
        if lifecycle:
            route, intent = lifecycle
            return exact_schema(empty_result(
                route=route, intent=intent, domain="system", confidence=1.0,
                reason="router_v3:lifecycle",
            )), "deterministic_lifecycle"

        approval = semantic.match_approval(clean, bool(context.get("awaiting_approval")))
        if approval:
            return exact_schema(empty_result(
                route="system", intent=approval, domain="system", confidence=1.0,
                reason="router_v3:approval",
            )), "deterministic_approval"

        if semantic.semantic_enabled():
            try:
                decided, trace = semantic.semantic_route(clean, context=context)
            except Exception as exc:
                decided, trace = None, {"tier": "semantic", "ok": False,
                                        "reason": f"unhandled:{type(exc).__name__}"}
            self._last_semantic_trace = trace
            if decided is not None:
                return exact_schema(decided), "semantic"
            _safe_log(f"[ROUTER_V3] semantic_fallback reason={trace.get('reason', 'unknown')}")

        # Fallback tier. V2 owns the deterministic pre-router, registry
        # validation and clarification policy that the semantic tier defers to
        # when it cannot decide.
        from engine.groq_intent_router_v2 import route_intent_v2

        return exact_schema(route_intent_v2(clean, source=source, context=context)), "v2_fallback"

    def route(self, text: str, *, source: str = "voice", context: dict | None = None) -> dict[str, Any]:
        started = time.perf_counter()
        clean = " ".join(str(text or "").strip().split())
        if not clean:
            from engine.intent_taxonomy import empty_result

            result = exact_schema(empty_result(
                route="reject",
                intent="unknown",
                domain="unknown",
                confidence=1.0,
                reason="router_v3:empty_input",
            ))
            authority = "deterministic"
        else:
            result, authority = self._route_text(clean, source=source, context=context or {})

        trace = RouterTrace(
            source=authority,
            duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
            manifest_sha256=_manifest_sha256(),
            route=str(result.get("route") or ""),
            intent=str(result.get("intent") or ""),
            confidence=float(result.get("confidence") or 0.0),
        )
        with self._lock:
            self._last_trace = trace
        return result

    def last_trace(self) -> RouterTrace | None:
        with self._lock:
            return self._last_trace


_ROUTER = RouterV3()


def get_router_v3() -> RouterV3:
    return _ROUTER


def route_intent_v3(
    text: str,
    *,
    source: str = "voice",
    context: dict | None = None,
) -> dict[str, Any]:
    return _ROUTER.route(text, source=source, context=context)
