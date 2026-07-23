"""The single confidence + band policy — the one authority.

Replaces the three disagreeing confidence checks in the legacy router. It reads
the semantic match (similarity + top1-top2 margin) and the winning intent's
stakes, and returns exactly one band:

    ACT      — do it now (high confidence, low stakes)
    CONFIRM  — do it, but confirm first (destructive/irreversible, any confidence)
    ASK      — one clarifying question (ambiguous / near-tie / weak)
    CHAT     — this was conversation, not a command (or nothing matched)

Confidence and stakes are two separate axes: a cheap reversible action fires at
a low bar; a destructive one confirms even when confidence is high.

All thresholds are calibration knobs (env-overridable) — tune against the
calibration set, not by feel. Defaults are tuned for the numpy fallback
embedder; the e5 model runs on a higher similarity scale (see design spec).
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from .decision import Candidate
from .semantic import SemMatch

ACT = "act"
CONFIRM = "confirm"
ASK = "ask"
CHAT = "chat"


def _envf(name: str, default: float) -> float:
    try:
        return float(os.environ[name])
    except (KeyError, ValueError):
        return default


@dataclass
class Thresholds:
    floor: float = 0.18          # below -> out of scope (chat / escalate)
    accept: float = 0.30         # above -> confident enough to consider acting
    high: float = 0.44           # above (+ margin) -> high confidence
    margin_tie: float = 0.03     # top1-top2 below this = genuine tie -> ASK
    margin_clear: float = 0.07   # top1-top2 above this = clear winner

    @classmethod
    def from_env(cls) -> "Thresholds":
        base = cls()
        return cls(
            floor=_envf("NEXI_ROUTER_FLOOR", base.floor),
            accept=_envf("NEXI_ROUTER_ACCEPT", base.accept),
            high=_envf("NEXI_ROUTER_HIGH", base.high),
            margin_tie=_envf("NEXI_ROUTER_MARGIN_TIE", base.margin_tie),
            margin_clear=_envf("NEXI_ROUTER_MARGIN_CLEAR", base.margin_clear),
        )


@dataclass
class BandDecision:
    band: str
    candidate: Candidate
    reason: str


class ConfidencePolicy:
    def __init__(self, thresholds: Thresholds | None = None) -> None:
        self.t = thresholds or Thresholds.from_env()

    def decide(self, match: SemMatch) -> BandDecision:
        t = self.t
        best = match.best
        sim, margin = match.sim, match.margin

        # 1. nothing is close enough -> out of scope -> chat (LLM tier may override)
        if sim < t.floor:
            return BandDecision(CHAT, best, f"oos sim={sim:.2f}<{t.floor}")
        # 2. best match is conversational -> talk, don't act.
        # NOTE: gate on the ROUTE, not the domain — a tool can have category/domain
        # "conversation" (e.g. tell_joke) yet still be an action.
        if best.route == "brain":
            return BandDecision(CHAT, best, "conversation")
        # 3. two different actions nearly tie -> ask which
        if margin < t.margin_tie and sim < t.high:
            return BandDecision(ASK, best, f"tie margin={margin:.2f}")
        # 4. high confidence
        if sim >= t.high and margin >= t.margin_clear:
            if best.stakes == "high":
                return BandDecision(CONFIRM, best, "high-conf/high-stakes")
            return BandDecision(ACT, best, "high-conf")
        # 5. medium band
        if sim >= t.accept:
            if best.stakes == "high":
                return BandDecision(CONFIRM, best, "medium/high-stakes")
            if margin < t.margin_tie:
                return BandDecision(ASK, best, "medium/tie")
            return BandDecision(ACT, best, "medium")
        # 6. weak but above floor -> ask (LLM tier may override)
        return BandDecision(ASK, best, f"weak sim={sim:.2f}")


def _demo() -> None:
    def m(sim, margin, route="tool", domain="desktop", stakes="low"):
        best = Candidate("open_app", domain, route, sim, stakes)
        return SemMatch(best=best, margin=margin, sim=sim,
                        candidates=[best, Candidate("open_website", "web", "tool", sim - margin, "low")])

    p = ConfidencePolicy()
    assert p.decide(m(0.6, 0.2)).band == ACT
    assert p.decide(m(0.6, 0.2, stakes="high")).band == CONFIRM
    assert p.decide(m(0.5, 0.01)).band == ASK            # tie
    assert p.decide(m(0.05, 0.0)).band == CHAT           # below floor
    assert p.decide(m(0.6, 0.2, route="brain", domain="conversation")).band == CHAT
    print("confidence._demo OK")


if __name__ == "__main__":
    _demo()
