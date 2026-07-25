"""NEXI as intake manager: ask first, plan second, only then build.

Darsh's brief: "whenever we start building, NEXI acts as a questioner — asks
different-perspective questions, then creates a proper workflow, plan, architecture,
requirements. That whole data NEXI creates on its own. Then it hands the data to the
agents: the research agent reads everything and researches; then the NEXT agent gets the
original data PLUS the research. So context accumulates step by step."

Two failure modes this exists to prevent, both observed in this project:

  * BUILDING THE WRONG THING. A vague request ("make it better") reaches an agent that
    confidently implements a guess. Questions are cheaper than a wrong sprint.
  * BUILDING WITHOUT A BRIEF. Studio already forwards prior stage handoffs
    (supervisor._prior_handoffs), so the architect does see research — the gap was
    UPSTREAM of that: no requirements/acceptance artefact existed before stage one, so
    the pipeline accumulated context around an unexamined request. ContextLedger below
    carries that brief; it complements the existing handoff chain rather than replacing it.

Questions are generated from what is MISSING in the request, not from a fixed list —
asking "what is your budget?" about a bug fix is noise, and noise trains the user to
skip the questions. Nothing here calls a model: it is deterministic gap analysis, so it
costs no tokens and cannot hallucinate a requirement.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

# What a buildable brief needs. Each probe: (dimension, detector, question, why it matters)
_DIMENSIONS: list[tuple[str, str, str, str]] = [
    ("outcome",
     r"\b(so that|in order to|because|goal is|need to|want to|should be able)\b",
     "What does success look like — what can you do after this ships that you cannot do now?",
     "Without a success condition there is nothing to verify against, so QA cannot fail."),
    ("scope",
     r"\b(only|just|limited to|scope|not include|exclude|out of scope)\b",
     "What is explicitly OUT of scope for this piece of work?",
     "Unbounded scope is the main cause of a build that never converges."),
    ("users",
     r"\b(user|customer|admin|team|me|myself|operator|client|visitor)\b",
     "Who uses this, and what is their skill level?",
     "Interface and error-handling decisions depend entirely on the audience."),
    ("constraints",
     r"\b(must|cannot|offline|free|no api|budget|latency|privacy|secure|windows|linux)\b",
     "What constraints are non-negotiable (cost, offline, privacy, platform, latency)?",
     "A constraint discovered late invalidates the architecture, not just the code."),
    ("data",
     r"\b(data|database|file|input|api|source|store|schema|record)\b",
     "What data does this read or write, and where does it live?",
     "Data shape drives the design; guessing it is the most expensive mistake to undo."),
    ("existing",
     r"\b(existing|current|already|refactor|replace|extend|integrate|legacy)\b",
     "Does this replace or extend something that already exists?",
     "Rebuilding something already present is the most common wasted sprint."),
    ("done",
     r"\b(test|verify|accept|criteria|definition of done|prove|measure)\b",
     "How will we prove it works — what test or observation counts as done?",
     "A build with no acceptance test cannot be gated, only guessed at."),
]

_TRIVIAL = re.compile(
    r"^\s*(open|close|launch|start|stop|play|pause|mute|screenshot|what time|what's the time)\b",
    re.I)


def needs_intake(request: str) -> bool:
    """Should NEXI interview before building?

    Routine desktop commands ("open chrome") must NEVER trigger an interview — that is
    the behaviour that makes an assistant exhausting. Only development-shaped work does.
    """
    text = str(request or "").strip()
    if not text or _TRIVIAL.match(text):
        return False
    build_words = re.search(
        r"\b(build|create|implement|develop|design|add|refactor|migrate|integrate|"
        r"fix|rewrite|architect|feature|system|app|service|api|pipeline)\b", text, re.I)
    return bool(build_words)


def analyse(request: str) -> dict:
    """Deterministic gap analysis: which dimensions the request does NOT answer."""
    text = str(request or "")
    answered, missing = [], []
    for dim, pattern, question, why in _DIMENSIONS:
        (answered if re.search(pattern, text, re.I) else missing).append(
            {"dimension": dim, "question": question, "why": why})
    coverage = len(answered) / float(len(_DIMENSIONS))
    return {"request": text[:2000], "answered": [a["dimension"] for a in answered],
            "missing": missing, "coverage": round(coverage, 2)}


def questions(request: str, limit: int = 4) -> list[dict]:
    """The questions worth asking — highest-value gaps only.

    Capped deliberately: a wall of questions gets skipped, and a skipped interview is
    worse than no interview because it looks like consent.
    """
    gaps = analyse(request)["missing"]
    return gaps[:max(1, limit)] if gaps else []


def build_brief(request: str, answers: dict[str, str] | None = None) -> dict:
    """The artefact NEXI produces before any agent runs: plan, flow, requirements.

    This is the "whole data" that gets handed down the pipeline. Deterministic — the
    plan's shape comes from the governance stages that will actually execute it, so the
    brief can never describe a workflow the supervisor does not run.
    """
    from engine.studio import governance

    answers = {k: str(v) for k, v in (answers or {}).items() if str(v).strip()}
    gap = analyse(request)
    resolved = sorted(set(gap["answered"]) | set(answers))
    still_open = [m for m in gap["missing"] if m["dimension"] not in answers]

    stages = list(governance.CANONICAL_STAGES)
    flow = [{"step": i + 1, "stage": s,
             "agent": governance.CANONICAL_STAGE_AGENTS[s],
             "mode": governance.permission_mode_for(s)} for i, s in enumerate(stages)]

    return {
        "created_at": time.time(),
        "request": str(request or "")[:2000],
        "answers": answers,
        "resolved_dimensions": resolved,
        "open_questions": [m["question"] for m in still_open],
        "readiness": round(len(resolved) / float(len(_DIMENSIONS)), 2),
        "flow": flow,
        "requirements": _requirements(request, answers),
        "acceptance": _acceptance(request, answers),
    }


def _requirements(request: str, answers: dict[str, str]) -> list[str]:
    out = [f"Deliver: {str(request or '').strip()[:300]}"]
    for dim in ("outcome", "scope", "constraints", "data", "users"):
        if answers.get(dim):
            out.append(f"{dim.title()}: {answers[dim][:300]}")
    return out


def _acceptance(request: str, answers: dict[str, str]) -> list[str]:
    stated = answers.get("done")
    if stated:
        return [stated[:300]]
    # Never invent a specific acceptance test — say plainly that it is missing.
    return ["ACCEPTANCE NOT DEFINED — QA cannot gate this until success is stated."]


# ---- accumulating context ledger --------------------------------------------------

class ContextLedger:
    """Carries the brief PLUS every prior stage's output to the next agent.

    Darsh's example: research reads everything and researches; the next agent gets
    the original data AND the research. Previously each stage saw only the brief, so the
    architect never learned what research found — five agents guessing in parallel
    instead of a pipeline that compounds.
    """

    def __init__(self, brief: dict):
        self.brief = dict(brief or {})
        self.entries: list[dict] = []

    def add(self, stage: str, agent: str, output: str, *, verified: bool = False) -> None:
        self.entries.append({
            "stage": str(stage), "agent": str(agent),
            "output": str(output or "")[:4000],
            "verified": bool(verified), "at": time.time(),
        })

    def for_stage(self, stage: str, max_chars: int = 6000) -> str:
        """The prompt context for the NEXT agent: brief + everything learned so far."""
        parts = [
            "## ORIGINAL REQUEST", self.brief.get("request", ""), "",
            "## REQUIREMENTS", *[f"- {r}" for r in self.brief.get("requirements", [])], "",
            "## ACCEPTANCE", *[f"- {a}" for a in self.brief.get("acceptance", [])], "",
        ]
        if self.brief.get("open_questions"):
            # Carry unknowns forward explicitly so an agent cannot silently invent them.
            parts += ["## STILL UNANSWERED (do not invent answers — flag if blocking)",
                      *[f"- {q}" for q in self.brief["open_questions"]], ""]
        if self.entries:
            parts.append("## WORK COMPLETED SO FAR (build on this, do not redo it)")
            for e in self.entries:
                flag = "verified" if e["verified"] else "unverified"
                parts.append(f"### {e['stage']} — {e['agent']} ({flag})")
                parts.append(e["output"])
                parts.append("")
        parts += [f"## YOUR STAGE: {stage}"]
        return "\n".join(parts)[:max_chars]

    def as_dict(self) -> dict:
        return {"brief": self.brief, "entries": self.entries}


def _demo() -> None:
    # routine commands must not trigger an interview
    assert not needs_intake("open chrome")
    assert not needs_intake("what time is it")
    assert needs_intake("build a login system for the web app")

    vague = "build a dashboard"
    qs = questions(vague)
    assert 1 <= len(qs) <= 4, qs
    assert all("question" in q and "why" in q for q in qs)

    detailed = ("build a dashboard so that the admin user can see revenue; "
                "must be offline and free; reads data from the sqlite database; "
                "extends the existing UI; done when the test passes; scope excludes mobile")
    assert analyse(detailed)["coverage"] > analyse(vague)["coverage"]

    brief = build_brief(vague, {"outcome": "see revenue at a glance"})
    assert brief["flow"][0]["stage"] == "requirements"
    assert "ACCEPTANCE NOT DEFINED" in brief["acceptance"][0], "must not invent acceptance"

    led = ContextLedger(brief)
    led.add("research", "research-analyst", "Found existing chart lib in repo.", verified=True)
    ctx = led.for_stage("architecture")
    assert "ORIGINAL REQUEST" in ctx and "existing chart lib" in ctx, "context did not accumulate"
    assert "STILL UNANSWERED" in ctx
    print("intake._demo OK -> readiness", brief["readiness"], "| questions", len(qs))


if __name__ == "__main__":
    _demo()
