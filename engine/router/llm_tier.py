"""Tier 1/2 — gpt-oss escalation brain.

Called by the pipeline ONLY when Tier 0 is unsure (band ASK) or thinks it's chat
but might be wrong. Handles the ambiguous middle and the genuinely hard requests.

Anti-hallucination by construction (the owner's "it should not hallucinate"):
  * tool-RAG — only the top-k candidate tools from the semantic layer go into the
    prompt, never all 115;
  * function-calling — the model must pick one of THOSE tools; the provider
    constrains the returned name to the offered set (it cannot invent a tool);
  * hard cross-check — the returned name must still resolve to a real, enabled
    registry tool, or we reject and keep the Tier-0 decision.

Two tiers: gpt-oss-20b first; escalate to gpt-oss-120b when 20b fails or abstains
on what Tier-0 believed was a confident action (the "hard disagreement" case).

Safe: default OFF (opt-in NEXI_ROUTER_LLM=1). Any failure returns None, so the
pipeline falls back to its Tier-0 decision — the router never breaks or blocks.
"""
from __future__ import annotations

import os
from typing import Optional

from engine import intent_taxonomy as tax
from engine import tool_registry

from .decision import Decision, route_for_intent
from .semantic import SemMatch

_SYSTEM = (
    "You are NEXI's intent router. Choose the ONE tool from the provided list that "
    "best matches the user's command, and fill its arguments from what they said. "
    "Only ever use a tool from the list — never invent a tool or an argument value. "
    "If the user is only chatting or asking a general knowledge question (not "
    "commanding an action), do NOT call any tool."
)

_STAKES_RISK = {"high": "high", "medium": "medium", "low": "low"}


def _enabled() -> bool:
    return (os.getenv("NEXI_ROUTER_LLM", "0") or "").strip().lower() in {"1", "true", "yes", "on"}


def _escalate_model() -> str:
    return os.getenv("NEXI_ROUTER_LLM_ESCALATE_MODEL", "openai/gpt-oss-120b")


def _stakes(spec) -> str:
    if spec.requires_confirmation or spec.safety in ("high", "critical"):
        return "high"
    if spec.safety == "medium":
        return "medium"
    return "low"


class LLMTier:
    """Injectable escalation hook. Pass a fake `provider` in tests."""

    def __init__(self, provider=None, k: int = 6) -> None:
        self._provider = provider
        self.k = k

    def _get_provider(self):
        if self._provider is None:
            from engine.providers.groq_provider import GroqProvider
            self._provider = GroqProvider()
        return self._provider

    def __call__(self, norm, match: SemMatch, ctx: dict) -> Optional[Decision]:
        if not _enabled():
            return None
        # skip the LLM on obviously-conversational input (fast, cheap)
        if match.best.route == "brain" and match.sim >= 0.6:
            return None
        try:
            provider = self._get_provider()
            if not provider.is_available():
                return None
            tools, names = self._candidate_tools(match)
            if not tools:
                return None
            messages = [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": norm.raw or norm.canonical},
            ]
            model = os.getenv("NEXI_ROUTER_LLM_MODEL", "")
            result = provider.route_with_tools(messages, tools, tool_choice="auto", model=model)
            decision = self._from_result(result, match, tier=1)

            # escalate to 120b: 20b failed, OR abstained while Tier-0 saw a confident action
            hard = decision is None or (
                decision.route == "brain"
                and match.best.route in ("tool", "output")
                and match.sim >= 0.4
            )
            if hard:
                escalated = provider.route_with_tools(
                    messages, tools, tool_choice="auto", model=_escalate_model()
                )
                decision2 = self._from_result(escalated, match, tier=2)
                if decision2 is not None:
                    return decision2
            return decision
        except Exception:
            return None  # the LLM tier must never break or block routing

    def _candidate_tools(self, match: SemMatch):
        tools, names = [], []
        for cand in match.candidates:
            if cand.route not in ("tool", "output"):
                continue
            spec = tool_registry._TOOLS.get(cand.intent)
            if spec is not None and spec.enabled:
                tools.append(spec.to_openai_schema())
                names.append(cand.intent)
            if len(tools) >= self.k:
                break
        return tools, names

    def _domain_for(self, name: str, match: SemMatch) -> str:
        for cand in match.candidates:
            if cand.intent == name:
                return cand.domain
        return "desktop"

    def _from_result(self, result, match: SemMatch, tier: int) -> Optional[Decision]:
        if result is None or not getattr(result, "ok", False):
            return None
        call = getattr(result, "tool_call", None)
        if not call:  # model declined to call a tool -> conversation
            res = tax.empty_result(route="brain", intent="general_qa",
                                   domain="conversation", confidence=0.7,
                                   reason=f"tier{tier}:no_tool")
            return self._wrap(res, "chat", tier, match)

        name = call.get("name", "")
        spec = tool_registry._TOOLS.get(name)
        if spec is None or not spec.enabled:  # HARD cross-check — reject hallucinated/disabled
            return None
        raw_args = call.get("arguments") or {}
        slots = {str(k): str(v) for k, v in raw_args.items() if isinstance(k, str) and v is not None}
        stakes = _stakes(spec)
        res = tax.empty_result(
            route=route_for_intent(name), intent=name,
            domain=self._domain_for(name, match), confidence=0.9,
            reason=f"tier{tier}:tool_call",
        )
        res["slots"] = slots
        res["risk_level"] = _STAKES_RISK[stakes]
        res["requires_confirmation"] = stakes == "high"
        res["missing_slots"] = tool_registry.missing_slots(name, slots)
        res = tax.exact_schema(res)
        band = "confirm" if stakes == "high" else "act"
        return self._wrap(res, band, tier, match)

    @staticmethod
    def _wrap(result: dict, band: str, tier: int, match: SemMatch) -> Decision:
        return Decision(
            result=result, band=band, tier=tier, sim=match.sim, margin=match.margin,
            candidates=match.candidates[:5], source=f"llm{tier}", escalated=(tier == 2),
        )


# --------------------------------------------------------------------------- #
# self-test with a stubbed provider (no network) — exercises the logic that
# runs on the user's machine, so the mapping/cross-check/fallback are verified.
# --------------------------------------------------------------------------- #
class _FakeResult:
    def __init__(self, ok=True, tool_call=None):
        self.ok = ok
        self.tool_call = tool_call
        self.decision = None
        self.error_code = ""


class _FakeProvider:
    def __init__(self, script):
        self.script = list(script)   # list of _FakeResult, popped per call
        self.calls = 0

    def is_available(self):
        return True

    def route_with_tools(self, messages, tools, *, model="", timeout=4.0, tool_choice="auto"):
        self.calls += 1
        return self.script.pop(0) if self.script else _FakeResult(ok=False)


def _demo() -> None:
    from .decision import Candidate

    os.environ["NEXI_ROUTER_LLM"] = "1"
    match = SemMatch(
        best=Candidate("open_app", "desktop", "tool", 0.42, "low"),
        margin=0.02, sim=0.42,
        candidates=[
            Candidate("open_app", "desktop", "tool", 0.42, "low"),
            Candidate("open_website", "web", "tool", 0.40, "low"),
        ],
    )

    class N:  # minimal normalized stand-in
        raw = "fire up chrome"
        canonical = "fire up chrome"

    # 1. valid tool_call -> ACT with slots
    tier = LLMTier(provider=_FakeProvider([
        _FakeResult(tool_call={"name": "open_app", "arguments": {"app_name": "chrome"}})
    ]))
    d = tier(N(), match, {})
    assert d is not None and d.route == "tool" and d.intent == "open_app", d
    assert d.result["slots"].get("app_name") == "chrome", d.result["slots"]

    # 2. hallucinated tool name -> rejected -> None (pipeline keeps Tier-0)
    tier = LLMTier(provider=_FakeProvider([
        _FakeResult(tool_call={"name": "make_coffee", "arguments": {}}),
        _FakeResult(ok=False),  # 120b escalation also fails
    ]))
    assert tier(N(), match, {}) is None

    # 3. no tool_call -> chat
    tier = LLMTier(provider=_FakeProvider([_FakeResult(tool_call=None)]))
    d = tier(N(), match, {})
    assert d is not None and d.route == "brain", d

    # 4. disabled via env -> None regardless of provider
    os.environ["NEXI_ROUTER_LLM"] = "0"
    assert LLMTier(provider=_FakeProvider([_FakeResult(tool_call={"name": "open_app", "arguments": {}})]))(N(), match, {}) is None
    print("llm_tier._demo OK")


if __name__ == "__main__":
    _demo()
