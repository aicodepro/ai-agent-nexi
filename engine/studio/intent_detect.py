"""Understand that the CEO wants something built — without a magic phrase.

Darsh: "I will not issue commands like 'build this' or 'studio mode'. Nexi should
interpret the request through its own self-understanding."

Today `parse_studio_command` is a keyword grammar: "let's build X" and "studio mode: X"
work, but "I want a python function that reverses a string" is missed entirely. This
module adds the understanding layer while keeping two properties that must not be lost:

  1. AUTHORIZATION IS UNCHANGED. `consume_authorization_audit` still requires a token
     minted by a real CEO turn. This changes WHAT counts as a build request, never WHO
     may authorize one — a model still cannot self-authorize a build.
  2. INFERRED INTENT IS CONFIRMED, EXPLICIT INTENT IS NOT. An 11-stage build kicked off
     by a passing remark ("I want coffee") would be far worse than asking. So an
     explicit trigger runs directly; an inferred one asks a single confirming question
     first. That is the difference between understanding someone and assuming.

Detection is deterministic and free — no model call, so it cannot hallucinate a build
request and costs nothing on every utterance. The LLM tier is only consulted for genuinely
ambiguous middles, behind a flag, and never on the hot path by default.
"""
from __future__ import annotations

import json
import os
import re

# Verbs that signal "produce a software artefact for me".
_BUILD_VERBS = (
    r"build|create|make|implement|develop|write|code|add|set\s?up|scaffold|generate|"
    r"design|refactor|migrate|port|integrate|automate|fix|rewrite|extend"
)
# Things that indicate the artefact is SOFTWARE, not a sandwich.
_ARTIFACTS = (
    r"app|application|script|function|class|module|library|package|api|endpoint|service|"
    r"tool|cli|website|site|page|dashboard|component|feature|system|bot|pipeline|"
    r"database|schema|test|suite|project|program|server|plugin|extension|integration"
)
# First-person wanting, e.g. "I want ...", "I need ...", "can you ..."
_WANT = r"i\s+(?:want|need|would\s+like|wanna)|can\s+you|could\s+you|please|let'?s|lets|help\s+me"

_BUILD_VERB_RE = re.compile(rf"\b(?:{_BUILD_VERBS})\b", re.I)
_ARTIFACT_RE = re.compile(rf"\b(?:{_ARTIFACTS})\b", re.I)
_WANT_RE = re.compile(rf"\b(?:{_WANT})\b", re.I)
# Technical signal: a language/stack name makes "build" almost certainly software.
_TECH_RE = re.compile(
    r"\b(python|javascript|typescript|react|node|java|rust|go|c\+\+|c#|sql|html|css|"
    r"django|flask|fastapi|next\.?js|vue|svelte|docker|kubernetes)\b", re.I)

# Things that look like builds but are NOT a Studio job — routine desktop control, or
# talking ABOUT building. Checked first; a false start is expensive.
_NOT_A_BUILD = re.compile(
    r"^\s*(?:open|close|launch|start|stop|play|pause|mute|unmute|volume|screenshot|"
    r"search|google|what|who|when|where|why|how\s+do|how\s+does|tell\s+me|show\s+me|"
    r"read|summari[sz]e|translate|remind|schedule|email|call|text)\b", re.I)
_ABOUT_BUILDING = re.compile(
    r"\b(?:how\s+(?:do|would|can)\s+(?:i|you|we)\s+build|what\s+is|explain|"
    r"difference\s+between|should\s+i\s+use|which\s+is\s+better)\b", re.I)


def _score(text: str) -> tuple[float, list[str]]:
    """Confidence that this utterance asks for something to be BUILT."""
    signals: list[str] = []
    score = 0.0
    if _BUILD_VERB_RE.search(text):
        score += 0.40
        signals.append("build_verb")
    if _ARTIFACT_RE.search(text):
        score += 0.35
        signals.append("software_artifact")
    if _TECH_RE.search(text):
        score += 0.20
        signals.append("technology_named")
    if _WANT_RE.search(text):
        score += 0.10
        signals.append("request_phrasing")
    # A verb alone ("fix it") is far weaker than verb + artefact.
    if "build_verb" in signals and "software_artifact" not in signals and "technology_named" not in signals:
        score -= 0.25
        signals.append("verb_without_artifact")
    return max(0.0, min(1.0, score)), signals


def detect(text: str, *, act_threshold: float = 0.70, ask_threshold: float = 0.45) -> dict:
    """Classify an utterance.

    action: "build"   -> explicit trigger, start immediately
            "confirm" -> looks like a build; ask ONE question before committing
            "ignore"  -> not a build request
    """
    raw = str(text or "").strip()
    result = {"action": "ignore", "confidence": 0.0, "goal": "", "signals": [],
              "explicit": False, "reason": ""}
    if not raw:
        return result

    # 1. The explicit grammar always wins — it is an unambiguous authorization phrase.
    try:
        from engine.studio.commands import parse_studio_command
        parsed = parse_studio_command(raw)
    except Exception:
        parsed = None
    if parsed:
        result.update({"action": "build", "confidence": 1.0, "goal": parsed.get("goal", ""),
                       "signals": ["explicit_trigger"], "explicit": True,
                       "reason": "explicit Studio trigger"})
        return result

    # 2. Reject the look-alikes before scoring. Someone asking "how do I build X" wants
    #    an answer, not an 11-stage build; "open chrome" is desktop control.
    if _NOT_A_BUILD.match(raw):
        result["reason"] = "routine command or question, not a build request"
        return result
    if _ABOUT_BUILDING.search(raw):
        result["reason"] = "asking ABOUT building, not asking to build"
        return result

    # Round BEFORE comparing: 0.35 + 0.10 is 0.4499999... in float, so a raw
    # `>= 0.45` silently rejected a request that scored exactly the threshold.
    score, signals = _score(raw)
    score = round(score, 2)
    result.update({"confidence": score, "signals": signals, "goal": _goal(raw)})
    if score >= act_threshold:
        # Understood, but NOT an explicit authorization phrase -> confirm once. An
        # 11-stage build started from a misread sentence costs far more than a question.
        result.update({"action": "confirm", "reason": "build intent inferred with high confidence"})
    elif score >= ask_threshold:
        result.update({"action": "confirm", "reason": "possible build intent — needs confirmation"})
    else:
        result["reason"] = "no clear build intent"
    return result


_LLM_PROMPT = """Classify ONE utterance from a user talking to their desktop assistant.
Is the user asking for SOFTWARE TO BE BUILT (a program, script, feature, tool, app)?

NOT a build request: opening apps, playing media, questions ABOUT programming
("how do I build a react app"), search, reminders, chat.
IS a build request: any phrasing that asks for software to be created or changed,
however indirect ("the CSV thing is manual, sort it out for me").

Return STRICT JSON only:
{{"is_build": <bool>, "goal": "<the thing to build, or empty>", "confidence": <0.0-1.0>}}

UTTERANCE: {text}"""


def llm_detect(text: str, generate_fn=None) -> dict | None:
    """Ask a small fast model when the deterministic scorer is unsure.

    Darsh wants NEXI to understand "anything I say", which no keyword list can do.
    But the deterministic pass stays FIRST because it is free, instant, and cannot
    hallucinate a build request — the model is consulted only for the ambiguous middle,
    which is a small fraction of utterances. Returns None on any failure so detection
    degrades to the deterministic verdict rather than breaking the turn.
    """
    if generate_fn is None:
        def generate_fn(prompt: str) -> str:
            # Small/free model by preference — this runs on the voice path, so it must be
            # cheap and fast. Model choice is discovered, never hardcoded.
            from engine.providers import get_intent_provider
            provider = get_intent_provider()
            if provider is None or not provider.is_available():
                raise RuntimeError("no intent provider")
            model = (os.getenv("NEXI_INTENT_DETECT_MODEL") or "").strip()
            res = provider.route_with_schema(
                [{"role": "user", "content": prompt}], {},
                model=model, timeout=float(os.getenv("NEXI_INTENT_DETECT_TIMEOUT", "6")))
            if not res.ok:
                raise RuntimeError(res.reason or "provider failed")
            return res.raw_text or json.dumps(res.decision or {})

    try:
        raw = generate_fn(_LLM_PROMPT.format(text=str(text or "")[:400]))
        blob = raw if isinstance(raw, str) else json.dumps(raw)
        match = re.search(r"\{.*\}", blob, flags=re.S)
        data = json.loads(match.group(0) if match else blob)
        if not isinstance(data, dict) or "is_build" not in data:
            return None
        return {
            "is_build": bool(data.get("is_build")),
            "goal": str(data.get("goal") or "").strip()[:300],
            "confidence": max(0.0, min(1.0, float(data.get("confidence") or 0.0))),
        }
    except Exception as exc:
        print(f"[INTENT_DETECT] llm_tier_skipped reason={type(exc).__name__}", flush=True)
        return None


def act_threshold_llm() -> float:
    """Above this the deterministic pass is confident enough; no model call needed."""
    try:
        return float(os.getenv("NEXI_INTENT_DETECT_LLM_CEILING", "0.70"))
    except (TypeError, ValueError):
        return 0.70


def detect_smart(text: str, *, generate_fn=None, use_llm: bool | None = None) -> dict:
    """Deterministic detection, escalating to the LLM only for the ambiguous middle.

    Escalation band is deliberately narrow: a clear yes or a clear no never costs a
    model call, so the common case stays free and instant on the voice path.
    """
    result = detect(text)
    if result["explicit"] or result["action"] == "build":
        return result
    if use_llm is None:
        use_llm = str(os.getenv("NEXI_INTENT_DETECT_LLM", "1")).strip().lower() not in {"0", "false", "no", "off"}
    if not use_llm:
        return result

    conf = result["confidence"]
    # Escalate anything the scorer is not already confident about. The floor is 0, not
    # 0.15, because the whole point of the tier is phrasing no keyword list scores —
    # "the CSV thing is manual, sort it out for me" scores 0.0 and is still a build
    # request. That is affordable because the obvious non-builds (routine commands,
    # questions about programming) were already rejected above and never reach here.
    # Very short utterances are skipped: "hi", "thanks", "yes" cannot be a brief.
    if conf >= act_threshold_llm():
        return result
    if len(str(text or "").split()) < 4:
        return result

    verdict = llm_detect(text, generate_fn=generate_fn)
    if verdict is None:
        return result
    result["llm_consulted"] = True
    if verdict["is_build"] and verdict["confidence"] >= 0.6:
        result.update({
            "action": "confirm",            # inferred -> still confirm, never auto-start
            "confidence": max(conf, verdict["confidence"]),
            "goal": verdict["goal"] or result["goal"] or _goal(text),
            "reason": "build intent understood by the language model",
            "signals": result["signals"] + ["llm"],
        })
    elif not verdict["is_build"]:
        # The model actively says this is not a build — trust it over a weak keyword hit.
        result.update({"action": "ignore", "reason": "language model: not a build request"})
    return result


_LEAD_STRIP = re.compile(
    rf"^\s*(?:{_WANT})\s*(?:to\s+)?", re.I)


def _goal(text: str) -> str:
    """The buildable goal, with the request scaffolding removed."""
    goal = _LEAD_STRIP.sub("", str(text or "").strip())
    goal = re.sub(r"^\s*(?:a|an|the)\s+project\s+(?:regarding|about|for)\s+", "", goal, flags=re.I)
    return goal.strip(" .!?")


def confirmation_question(detection: dict) -> str:
    """What NEXI says before committing to an inferred build."""
    goal = detection.get("goal") or "that"
    return (f"It sounds like you want me to build {goal[:120]}. "
            f"Shall I put the team on it?")


def _demo() -> None:
    # explicit -> straight to build
    d = detect("let's build a python function that reverses a string")
    assert d["action"] == "build" and d["explicit"], d

    # natural phrasing -> understood, but confirmed first
    for phrase in ("I want a python function that reverses a string",
                   "can you make me a tool that renames files",
                   "I need a dashboard that shows revenue",
                   "create a REST api for orders"):
        d = detect(phrase)
        assert d["action"] == "confirm", (phrase, d)
        assert d["goal"], d

    # routine control and questions must NOT start a build
    for phrase in ("open chrome", "what time is it", "play music",
                   "how do I build a react app", "what is a closure",
                   "search for python tutorials"):
        d = detect(phrase)
        assert d["action"] == "ignore", (phrase, d)

    # goal extraction strips the ask
    assert "reverses a string" in detect("I want a python function that reverses a string")["goal"]
    print("intent_detect._demo OK")


if __name__ == "__main__":
    _demo()
