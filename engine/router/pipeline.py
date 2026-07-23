"""The pipeline — orchestrates the stages into one Decision.

    normalize -> guards(hook) -> semantic match -> WHEN gate + band policy
              -> [escalate(hook) if ambiguous] -> canonical Decision

`guards` and `escalate` are injectable hooks so the deterministic guard layer
(Tier 0a) and the gpt-oss-20b/120b tiers (Tier 1/2) plug in later without
touching this file. Today they are None, so the router runs Tier-0-only — enough
to shadow the live router and be scored.
"""
from __future__ import annotations

from typing import Callable, Optional

from engine import intent_taxonomy as tax
from engine import tool_registry

from .compound import split_steps
from .confidence import ACT, ASK, CHAT, CONFIRM, ConfidencePolicy
from .decision import Decision
from .embedder import Embedder
from .exemplars import build_bank
from .normalize import Normalized, normalize
from .semantic import SemanticRouter, SemMatch
from .slots import extract_slots

_STAKES_RISK = {"high": "high", "medium": "medium", "low": "low"}
_AUTO = object()  # sentinel: "auto-wire the LLM tier" vs. escalate=None ("disable")

# hook signatures (documented for the later tiers):
#   GuardHook(normalized, ctx) -> Decision | None      (short-circuit on hard match)
#   EscalateHook(normalized, match, ctx) -> Decision | None
GuardHook = Callable[..., Optional[Decision]]
EscalateHook = Callable[..., Optional[Decision]]


def _humanize(intent: str) -> str:
    return intent.replace("_", " ")


class Pipeline:
    def __init__(
        self,
        semantic: SemanticRouter,
        policy: ConfidencePolicy,
        guards: Optional[GuardHook] = None,
        escalate: Optional[EscalateHook] = None,
    ) -> None:
        self.semantic = semantic
        self.policy = policy
        self.guards = guards
        self.escalate = escalate

    @classmethod
    def build(
        cls,
        embedder: Embedder | None = None,
        guards: Optional[GuardHook] = None,
        escalate: Optional[EscalateHook] = _AUTO,
    ) -> "Pipeline":
        # auto-wire the gpt-oss escalation tier (dormant unless NEXI_ROUTER_LLM=1);
        # pass escalate=None to disable entirely.
        if escalate is _AUTO:
            from .llm_tier import LLMTier
            escalate = LLMTier()
        return cls(SemanticRouter(build_bank(), embedder), ConfidencePolicy(), guards, escalate)

    def route(self, text: str, ctx: dict | None = None) -> Decision:
        ctx = ctx or {}
        norm = normalize(text)

        if self.guards is not None:  # Tier 0a — deterministic hard rules (whole utterance)
            guarded = self.guards(norm, ctx)
            if guarded is not None:
                return guarded

        steps = split_steps(norm.raw)  # Stage 2a — multi-tasking / compound
        if len(steps) > 1:
            return self._route_plan(steps, ctx)
        return self._route_single(norm, ctx)

    def _route_single(self, norm: Normalized, ctx: dict) -> Decision:
        match = self.semantic.match(norm.canonical)  # Tier 0b — semantic
        band = self.policy.decide(match)
        if band.band in (ASK, CHAT) and self.escalate is not None:  # Tier 1/2 escalation
            escalated = self.escalate(norm, match, ctx)
            if escalated is not None:
                escalated.escalated = True
                return escalated
        return self._build(band.band, band.reason, match, norm)

    def _route_plan(self, steps: list[str], ctx: dict) -> Decision:
        sub = [self._route_single(normalize(step), ctx) for step in steps]
        sims = [d.sim for d in sub] or [0.0]
        result = tax.empty_result(
            route="react", intent="react_multi_step", domain="workflow",
            confidence=round(min(d.confidence for d in sub) if sub else 0.0, 3),
            reason=f"tier0:compound {len(sub)} steps",
        )
        return Decision(
            result=result, band=ACT, tier=0, sim=round(min(sims), 3), margin=0.0,
            candidates=[], source="compound", plan=sub,
        )

    def _build(self, band: str, reason: str, match: SemMatch, norm: Normalized) -> Decision:
        best = match.best
        sim = round(float(match.sim), 3)
        margin = round(float(match.margin), 3)
        out_band = band

        if band in (ACT, CONFIRM):
            route = best.route if best.route in tax.ALLOWED_ROUTES else "tool"
            slots = extract_slots(best.intent, norm)                    # Stage 5
            missing = tool_registry.missing_slots(best.intent, slots)
            if missing:  # a required argument is still unknown -> ask exactly for it
                slot = missing[0]
                result = tax.empty_result(
                    route="clarify", intent="clarify", domain=best.domain, confidence=sim,
                    reason=f"tier0:missing:{slot}",
                    clarification_question=tool_registry.clarification_for_missing_slot(best.intent, slot),
                )
                out_band = ASK
            else:
                result = tax.empty_result(
                    route=route, intent=best.intent, domain=best.domain,
                    confidence=sim, reason=f"tier0:{reason}",
                )
                result["slots"] = slots
                result["risk_level"] = _STAKES_RISK.get(best.stakes, "low")
                result["requires_confirmation"] = band == CONFIRM
                result["missing_slots"] = []
                result = tax.exact_schema(result)
        elif band == ASK:
            second = match.candidates[1] if len(match.candidates) > 1 else None
            if second is not None and second.intent != best.intent:
                question = (
                    f"Did you want me to {_humanize(best.intent)} "
                    f"or {_humanize(second.intent)}?"
                )
            else:
                question = f"Do you want me to {_humanize(best.intent)}?"
            result = tax.empty_result(
                route="clarify", intent="clarify", domain=best.domain,
                confidence=sim, reason=f"tier0:{reason}", clarification_question=question,
            )
        else:  # CHAT
            intent = best.intent if best.route == "brain" else "general_qa"
            result = tax.empty_result(
                route="brain", intent=intent, domain="conversation",
                confidence=sim, reason=f"tier0:{reason}",
            )

        return Decision(
            result=result, band=out_band, tier=0, sim=sim, margin=margin,
            candidates=match.candidates[:5], source="semantic",
        )


def _demo() -> None:
    from engine.router import route

    # cases chosen to be stable under the numpy fallback embedder
    cases = {
        "how much battery do i have left": ("tool", "get_battery_status"),
        "what time is it": ("tool", "tell_time"),
        "what is the capital of france": ("brain", "general_qa"),
        "hello there": ("brain", None),
    }
    for text, (exp_route, exp_intent) in cases.items():
        d = route(text)
        assert d.route == exp_route, f"{text!r} -> route {d.route} (wanted {exp_route}); band={d.band}"
        if exp_intent:
            assert d.intent == exp_intent, f"{text!r} -> intent {d.intent} (wanted {exp_intent})"

    # multi-step / compound -> a react plan of routed sub-steps
    plan = route("open notepad then take a screenshot")
    assert plan.route == "react", plan.route
    assert len(plan.plan) == 2, len(plan.plan)
    assert plan.plan[1].intent == "take_screenshot", plan.plan[1].intent
    print("pipeline._demo OK")


if __name__ == "__main__":
    _demo()
