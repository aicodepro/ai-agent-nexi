"""Cognitive Admission Gate — decides whether an unresolved utterance is admitted
to reasoning, and with WHICH capabilities.

Replaces the blunt `unknown + provider available -> ReAct` rule. Live evaluation
showed that rule fails two ways: it escalated noise ("zzxq camera blue whatever")
into a reasoning loop, and it handed the loop the entire ~120-tool catalog, so a
near-miss capability could be selected for a request that never named it.

Two invariants:
  1. Never reason without a BOUNDED capability set. If retrieval cannot narrow
     the catalog, ask a targeted question instead — an unbounded loop is exactly
     the hijack surface (a model asked to pick 1-of-120 picks badly).
  2. Never place a high-risk capability in a reasoning allowlist. Reasoning may
     conclude one is needed, but selecting it requires the approval path.

Fails closed: no provider, cold index, or any error yields a question, never a
loop. The gate only decides admission — it never executes anything.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

# Bounded decision vocabulary. There is deliberately no UNKNOWN.
DIRECT_RESPONSE = "DIRECT_RESPONSE"
DIRECT_ACTION = "DIRECT_ACTION"
REASONED_RESPONSE = "REASONED_RESPONSE"
CREATE_MISSION = "CREATE_MISSION"
ASK_TARGETED_QUESTION = "ASK_TARGETED_QUESTION"
REQUEST_APPROVAL = "REQUEST_APPROVAL"
REJECT_UNUSABLE_INPUT = "REJECT_UNUSABLE_INPUT"

_HIGH_RISK = {"high", "critical"}
_VOWELS = set("aeiouy")


@dataclass
class AdmissionDecision:
    mode: str
    reason: str = ""
    goal: str = ""
    candidate_capabilities: list[str] = field(default_factory=list)
    allowed_capabilities: list[str] = field(default_factory=list)
    blocked_capabilities: list[str] = field(default_factory=list)
    risk: str = "none"
    approval_required: bool = False
    reasoning_required: bool = False

    @property
    def admits_reasoning(self) -> bool:
        return self.mode in {REASONED_RESPONSE, CREATE_MISSION}

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "reason": self.reason, "goal": self.goal,
            "candidate_capabilities": list(self.candidate_capabilities),
            "allowed_capabilities": list(self.allowed_capabilities),
            "blocked_capabilities": list(self.blocked_capabilities),
            "risk": self.risk, "approval_required": self.approval_required,
            "reasoning_required": self.reasoning_required,
        }


def _enabled() -> bool:
    return (os.getenv("NEXI_ADMISSION_GATE", "1") or "").strip().lower() not in {"0", "false", "no", "off"}


def _has_noise_token(text: str) -> bool:
    """True if any word looks non-lexical, e.g. 'zzxq'.

    ponytail: vowel-presence heuristic, no dictionary. English words of 3+ letters
    essentially always contain a vowel (y counts, so 'rhythm'/'why' are fine).
    Ceiling: it will not catch noise made of real words; upgrade to a lexicon or a
    perplexity score if that becomes the observed failure.
    """
    for token in re.findall(r"[a-z]{3,}", str(text or "").lower()):
        if not (set(token) & _VOWELS):
            return True
    return False


def _usable(text: str) -> bool:
    raw = str(text or "").strip()
    if len(raw.split()) < 2:
        return False  # a one-word mystery is a mishear, not a goal
    if _has_noise_token(raw):
        return False
    try:
        from engine.transcript_filter import is_gibberish_or_wrong_language

        if is_gibberish_or_wrong_language(raw):
            return False
    except Exception:
        pass
    return True


def _retrieve(text: str) -> tuple[list[str], bool]:
    """Return (candidate tool names, bounded). bounded is False when retrieval
    could not narrow the catalog — the caller must then refuse to reason."""
    try:
        from engine.tool_registry import model_visible_tools

        specs = model_visible_tools()
        capabilities = [{"name": spec.name} for spec in specs]
        if not capabilities:
            return [], False

        from engine.groq_intent_router_v2 import _rag_filter_capabilities

        picked = _rag_filter_capabilities(text, capabilities)
        names = [c.get("name", "") for c in picked if c.get("name")]
        # Same length back == the index was cold or nothing matched, so the RAG
        # degraded to the full list. That is safe for prompting but NOT bounded.
        bounded = 0 < len(names) < len(capabilities)
        return names, bounded
    except Exception:
        return [], False


def _field(spec: Any, key: str, default: Any) -> Any:
    """tool_registry.get_tool returns asdict(ToolSpec) -- a dict, not the object.
    Read both shapes: attribute access on a dict silently yields the default,
    which would classify every high-risk capability as allowed."""
    if isinstance(spec, dict):
        return spec.get(key, default)
    return getattr(spec, key, default)


def _partition(names: list[str]) -> tuple[list[str], list[str]]:
    """Split candidates into (allowed for reasoning, blocked behind approval)."""
    allowed: list[str] = []
    blocked: list[str] = []
    try:
        from engine.tool_registry import get_tool
    except Exception:
        return [], list(names)
    for name in names:
        spec = get_tool(name)
        if not spec:
            continue
        safety = str(_field(spec, "safety", "") or "").lower()
        if safety in _HIGH_RISK or bool(_field(spec, "requires_confirmation", False)):
            blocked.append(name)
        else:
            allowed.append(name)
    return allowed, blocked


def admit(text: str, *, reasoning_available: bool = True) -> AdmissionDecision:
    """Decide whether this unresolved utterance may enter reasoning."""
    if not _enabled():
        # Explicit opt-out restores the previous unconditional behaviour.
        return AdmissionDecision(mode=REASONED_RESPONSE, reason="gate_disabled", reasoning_required=True)
    if not reasoning_available:
        return AdmissionDecision(mode=ASK_TARGETED_QUESTION, reason="no_reasoning_provider")
    if not _usable(text):
        return AdmissionDecision(mode=REJECT_UNUSABLE_INPUT, reason="unusable_input")

    candidates, bounded = _retrieve(text)
    if not bounded:
        # Invariant 1: refuse to reason over an unbounded catalog.
        return AdmissionDecision(
            mode=ASK_TARGETED_QUESTION, reason="capabilities_unbounded",
            candidate_capabilities=candidates,
        )

    allowed, blocked = _partition(candidates)
    if not allowed:
        # Invariant 2: the only plausible capabilities are gated ones.
        if blocked:
            return AdmissionDecision(
                mode=REQUEST_APPROVAL, reason="only_high_risk_capabilities",
                candidate_capabilities=candidates, blocked_capabilities=blocked,
                risk="high", approval_required=True,
            )
        return AdmissionDecision(
            mode=ASK_TARGETED_QUESTION, reason="no_usable_capability",
            candidate_capabilities=candidates,
        )

    return AdmissionDecision(
        mode=REASONED_RESPONSE, reason="bounded_capabilities",
        goal=str(text or "").strip()[:200],
        candidate_capabilities=candidates,
        allowed_capabilities=allowed, blocked_capabilities=blocked,
        risk="low", reasoning_required=True,
    )


# ── Allowlist handoff to the ReAct loop ─────────────────────────────────────
# Keyed by utterance so a stale allowlist can never bound an unrelated later turn.
_LAST: dict[str, Any] = {"text": "", "allowed": frozenset()}


def set_admission(text: str, allowed: list[str]) -> None:
    _LAST["text"] = str(text or "").strip()
    _LAST["allowed"] = frozenset(allowed or ())


def allowed_for(text: str) -> frozenset[str] | None:
    """The capability allowlist admitted for exactly this utterance, else None."""
    if _LAST["allowed"] and _LAST["text"] and str(text or "").strip() == _LAST["text"]:
        return _LAST["allowed"]
    return None


def clear_admission() -> None:
    _LAST["text"] = ""
    _LAST["allowed"] = frozenset()
