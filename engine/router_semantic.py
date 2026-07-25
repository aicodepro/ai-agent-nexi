"""Router V3 semantic tier - structured LLM routing over retrieved capabilities.

This is the real LLM-first path. It replaces phrase matching for normal
language: the model receives a *retrieved subset* of capability manifests and
must return a structured RouteDecision, which is then validated against the
registry so a hallucinated capability can never execute.

Boundaries:
  - Lifecycle/safety commands never reach the model (see LIFECYCLE_COMMANDS).
  - The model proposes; deterministic policy decides risk and approval.
  - A capability the registry does not define is rejected, not executed.
  - On any failure the caller falls back to the V2 tier - the two never both
    execute for one utterance.
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

# Commands that must stay deterministic: they are how a user stops or cancels
# the assistant, so they can never depend on a network round-trip or a model's
# judgement.
LIFECYCLE_COMMANDS: dict[str, tuple[str, str]] = {
    "stop": ("system", "stop_speaking"),
    "stop talking": ("system", "stop_speaking"),
    "be quiet": ("system", "stop_speaking"),
    "shut up": ("system", "stop_speaking"),
    "cancel": ("system", "cancel"),
    "never mind": ("system", "cancel"),
    "nevermind": ("system", "cancel"),
    "emergency stop": ("system", "emergency_stop"),
    "shutdown": ("system", "shutdown"),
    "shut down": ("system", "shutdown"),
    "go to sleep": ("sleep", "sleep"),
    "sleep": ("sleep", "sleep"),
    "wake up": ("system", "wake"),
}

APPROVAL_YES = {"yes", "yeah", "yep", "confirm", "approve", "do it", "go ahead", "ok", "okay"}
APPROVAL_NO = {"no", "nope", "cancel that", "don't", "dont", "stop that", "deny"}

_TOKEN_RE = re.compile(r"[a-z0-9]+")


@dataclass
class RouteDecision:
    """Structured routing decision. Mirrors the mandate's required fields."""
    request_status: str = "complete"
    user_goal: str = ""
    subgoals: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    arguments: dict[str, Any] = field(default_factory=dict)
    missing_information: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risk: str = "low"
    approval_requirement: str = "none"
    success_conditions: list[str] = field(default_factory=list)
    fallback_strategy: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_status": self.request_status,
            "user_goal": self.user_goal,
            "subgoals": list(self.subgoals),
            "capabilities": list(self.capabilities),
            "arguments": dict(self.arguments),
            "missing_information": list(self.missing_information),
            "assumptions": list(self.assumptions),
            "risk": self.risk,
            "approval_requirement": self.approval_requirement,
            "success_conditions": list(self.success_conditions),
            "fallback_strategy": self.fallback_strategy,
            "confidence": self.confidence,
        }


def semantic_enabled() -> bool:
    """Opt-out flag. Defaults on; set 0/false/no/off to force the V2 tier."""
    raw = (os.getenv("NEXI_ROUTER_V3_SEMANTIC", "true") or "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _tokens(value: str) -> set[str]:
    return set(_TOKEN_RE.findall(str(value or "").lower()))


def _fuzzy_overlap(query: set[str], target: set[str], threshold: float = 0.75) -> float:
    """Count near-matching token pairs (ASR mishears: tak~take, krome~chrome)."""
    if not query or not target:
        return 0.0
    from difflib import SequenceMatcher

    hits = 0.0
    for q in query:
        if len(q) < 3:
            continue
        best = max((SequenceMatcher(None, q, t).ratio() for t in target if len(t) >= 3),
                   default=0.0)
        if best >= threshold:
            hits += best
    return hits


def _is_empty_decision(raw: dict) -> bool:
    """A structurally valid but contentless reply.

    Providers sometimes return the schema skeleton with everything blank. That
    is a provider failure, not a genuine 'incomplete request' - emitting a
    clarification for it would ask the user to repeat a request the model never
    actually read.
    """
    return (
        not (raw.get("capabilities") or [])
        and not str(raw.get("user_goal") or "").strip()
        and not (raw.get("missing_information") or [])
        and float(raw.get("confidence") or 0.0) <= 0.0
    )


def match_lifecycle(text: str) -> tuple[str, str] | None:
    """Exact-match only. A lifecycle verb inside a longer sentence is a normal
    request ('cancel my meeting' must not hit the cancel control)."""
    key = " ".join(str(text or "").strip().lower().rstrip(".!?").split())
    return LIFECYCLE_COMMANDS.get(key)


def match_approval(text: str, awaiting_approval: bool) -> str | None:
    """Yes/no is only an approval when something is actually awaiting one."""
    if not awaiting_approval:
        return None
    key = " ".join(str(text or "").strip().lower().rstrip(".!?").split())
    if key in APPROVAL_YES:
        return "approve"
    if key in APPROVAL_NO:
        return "deny"
    return None


def retrieve_capabilities(text: str, manifest: list[dict], limit: int = 12) -> list[dict]:
    """Rank capability cards by lexical overlap with the request.

    Deliberately dependency-free: sending 100+ full manifests to the model each
    turn is slow and dilutes attention, and an embedding model would add a heavy
    import to the voice path. Name/alias/example hits are weighted highest
    because those are what users actually say.
    """
    query = _tokens(text)
    if not query:
        return manifest[:limit]

    scored: list[tuple[float, dict]] = []
    for card in manifest:
        name_tokens = _tokens(card.get("name", "")) | _tokens(" ".join(card.get("aliases", []) or []))
        example_tokens = _tokens(" ".join(card.get("examples", []) or []))
        desc_tokens = _tokens(card.get("description", ""))

        score = (
            3.0 * len(query & name_tokens)
            + 2.0 * len(query & example_tokens)
            + 1.0 * len(query & desc_tokens)
        )
        # Exact overlap alone misses the case this router exists for: misheard
        # speech. "tak a screen shot" shares no token with "take_screenshot",
        # so add a fuzzy pass over name/alias tokens.
        score += 2.5 * _fuzzy_overlap(query, name_tokens)
        score += 1.0 * _fuzzy_overlap(query, example_tokens)

        if score > 0:
            scored.append((score, card))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    top = [card for _score, card in scored[:limit]]
    if len(top) < limit:
        # Always leave room for unmatched capabilities so a poorly-phrased
        # request can still reach the right tool.
        seen = {c.get("name") for c in top}
        for card in manifest:
            if card.get("name") not in seen:
                top.append(card)
                if len(top) >= limit:
                    break
    return top


def build_schema() -> dict[str, Any]:
    """JSON schema the provider must satisfy."""
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["request_status", "user_goal", "capabilities", "confidence"],
        "properties": {
            "request_status": {"type": "string",
                               "enum": ["complete", "incomplete", "ambiguous", "unsupported"]},
            "user_goal": {"type": "string"},
            "subgoals": {"type": "array", "items": {"type": "string"}},
            "capabilities": {"type": "array", "items": {"type": "string"}},
            "arguments": {"type": "object"},
            "missing_information": {"type": "array", "items": {"type": "string"}},
            "assumptions": {"type": "array", "items": {"type": "string"}},
            "risk": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
            "approval_requirement": {"type": "string", "enum": ["none", "confirm", "explicit"]},
            "success_conditions": {"type": "array", "items": {"type": "string"}},
            "fallback_strategy": {"type": "string"},
            "confidence": {"type": "number"},
        },
    }


def build_messages(text: str, candidates: list[dict], context: dict | None) -> list[dict]:
    cards = [{
        "name": c.get("name"),
        "description": c.get("description"),
        "examples": (c.get("examples") or [])[:3],
        "required_slots": c.get("required_slots") or [],
        "risk_level": c.get("risk_level"),
    } for c in candidates]

    system = (
        "You are NEXI's intent router. Map the user's request to capabilities "
        "from the provided list.\n"
        "Rules:\n"
        "- Use ONLY capability names that appear in the list. Never invent one.\n"
        "- Speech may be misheard; infer the intended request.\n"
        "- If the request is cut off or missing required information, set "
        "request_status to 'incomplete' and list what is missing. Do NOT guess.\n"
        "- If nothing in the list fits, return an empty capabilities array and "
        "request_status 'unsupported'.\n"
        "- risk/approval_requirement are advisory; NEXI's policy engine decides.\n"
        "Return strict JSON matching the schema."
    )
    payload = {"request": text, "capabilities": cards}
    if context:
        payload["context"] = {
            k: context[k] for k in ("active_app", "window_title", "url", "pending_question")
            if k in context
        }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def validate_decision(raw: dict[str, Any], allowed: set[str]) -> tuple[RouteDecision | None, str]:
    """Reject hallucinated capabilities before anything can execute."""
    if not isinstance(raw, dict):
        return None, "not_a_dict"

    caps_raw = raw.get("capabilities") or []
    if not isinstance(caps_raw, list):
        return None, "capabilities_not_a_list"

    # Models legitimately return either ["tell_time"] or
    # [{"name": "tell_time", "arguments": {...}}]. Accept both, and lift any
    # inline arguments so a dict-shaped reply does not silently lose its slots.
    caps: list[str] = []
    inline_args: dict[str, Any] = {}
    for entry in caps_raw:
        if isinstance(entry, str):
            caps.append(entry)
        elif isinstance(entry, dict):
            name = entry.get("name") or entry.get("capability") or entry.get("tool")
            if not isinstance(name, str):
                return None, "capability_entry_without_name"
            caps.append(name)
            for key in ("arguments", "args", "slots", "parameters"):
                if isinstance(entry.get(key), dict):
                    inline_args.update(entry[key])
        else:
            return None, f"capability_entry_not_str_or_dict:{type(entry).__name__}"

    unknown = [c for c in caps if c not in allowed]
    if unknown:
        return None, f"hallucinated_capability:{unknown[0]}"

    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0

    decision = RouteDecision(
        request_status=str(raw.get("request_status") or "complete"),
        user_goal=str(raw.get("user_goal") or ""),
        subgoals=[str(s) for s in (raw.get("subgoals") or []) if s],
        capabilities=[str(c) for c in caps],
        arguments={**inline_args,
                   **(raw.get("arguments") if isinstance(raw.get("arguments"), dict) else {})},
        missing_information=[str(m) for m in (raw.get("missing_information") or []) if m],
        assumptions=[str(a) for a in (raw.get("assumptions") or []) if a],
        risk=str(raw.get("risk") or "low"),
        approval_requirement=str(raw.get("approval_requirement") or "none"),
        success_conditions=[str(s) for s in (raw.get("success_conditions") or []) if s],
        fallback_strategy=str(raw.get("fallback_strategy") or ""),
        confidence=max(0.0, min(1.0, confidence)),
    )
    return decision, ""


def decision_to_schema(decision: RouteDecision, manifest_by_name: dict[str, dict]) -> dict[str, Any]:
    """Project a RouteDecision onto the taxonomy result the dispatcher expects.

    Risk and confirmation come from the REGISTRY, never from the model - a model
    must not be able to talk its way out of an approval gate.
    """
    from engine.intent_taxonomy import empty_result

    if decision.request_status == "incomplete" or decision.missing_information:
        missing = decision.missing_information or ["details"]
        return empty_result(
            route="clarify",
            intent=decision.capabilities[0] if decision.capabilities else "unknown",
            confidence=max(0.5, decision.confidence),
            reason="router_v3:incomplete_request",
        ) | {
            "missing_slots": missing,
            "expects_user_reply": True,
            "clarification_question": _clarification_for(decision, missing),
            "slots": decision.arguments,
        }

    if not decision.capabilities:
        return empty_result(
            route="brain",
            intent="general_qa",
            domain="conversation",
            confidence=max(0.4, decision.confidence),
            reason="router_v3:no_capability_match",
        ) | {"slots": {}}

    name = decision.capabilities[0]
    card = manifest_by_name.get(name, {})
    return empty_result(
        route="tool",
        intent=name,
        domain=card.get("category") or "unknown",
        confidence=decision.confidence,
        reason="router_v3:semantic",
    ) | {
        "slots": decision.arguments,
        # Registry is authoritative for risk/confirmation.
        "risk_level": card.get("risk_level") or "none",
        "requires_confirmation": bool(card.get("requires_confirmation")),
    }


def _clarification_for(decision: RouteDecision, missing: list[str]) -> str:
    goal = decision.user_goal or "that"
    first = missing[0].replace("_", " ")
    return f"I heard '{goal}', but I need the {first}. Nothing was done yet — what should it be?"


def semantic_route(text: str, *, context: dict | None = None,
                   timeout: float | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Run the semantic tier. Returns (taxonomy_result | None, trace)."""
    trace: dict[str, Any] = {"tier": "semantic", "ok": False, "reason": "", "duration_ms": 0.0}
    started = time.perf_counter()

    try:
        from engine.tool_registry import router_tool_manifest
        manifest = router_tool_manifest()
    except Exception as exc:
        trace["reason"] = f"manifest_unavailable:{type(exc).__name__}"
        return None, trace

    if not manifest:
        trace["reason"] = "empty_manifest"
        return None, trace

    try:
        from engine.providers import get_intent_provider
        provider = get_intent_provider()
    except Exception as exc:
        trace["reason"] = f"provider_init_failed:{type(exc).__name__}"
        return None, trace

    if provider is None or not provider.is_available():
        trace["reason"] = "provider_unavailable"
        return None, trace

    candidates = retrieve_capabilities(text, manifest)
    trace["candidates"] = [c.get("name") for c in candidates]

    try:
        result = provider.route_with_schema(
            build_messages(text, candidates, context),
            build_schema(),
            timeout=timeout or float(os.getenv("NEXI_ROUTER_V3_TIMEOUT", "4")),
        )
    except Exception as exc:
        trace["reason"] = f"provider_error:{type(exc).__name__}"
        return None, trace

    trace["duration_ms"] = round((time.perf_counter() - started) * 1000.0, 3)

    if not result.ok or result.decision is None:
        trace["reason"] = f"provider_not_ok:{getattr(result, 'error_code', '') or 'no_decision'}"
        return None, trace

    if _is_empty_decision(result.decision):
        # Fall through to the V2 tier rather than inventing a clarification.
        trace["reason"] = "empty_decision"
        trace["decision"] = result.decision
        return None, trace

    decision, error = validate_decision(result.decision, {c.get("name") for c in candidates})
    if decision is None:
        trace["reason"] = f"invalid_decision:{error}"
        return None, trace

    trace["ok"] = True
    trace["decision"] = decision.to_dict()
    manifest_by_name = {c.get("name"): c for c in manifest}
    return decision_to_schema(decision, manifest_by_name), trace
