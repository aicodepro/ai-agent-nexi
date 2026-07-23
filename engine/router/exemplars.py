"""The exemplar bank — the router's memory of "things that mean X".

Every routable intent gets a bag of example phrasings. It is SEEDED
automatically from `engine.tool_registry` (each tool's name, description,
aliases and examples) so adding a tool in ONE place also teaches the router,
and it GROWS from the user's corrections ("no, I meant X") with no retraining.

A `conversation` bucket holds chit-chat/question exemplars — that bucket is the
"just talking" side of the WHEN gate.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from engine import intent_taxonomy as tax  # noqa: F401  (kept for intent validation parity)
from engine import tool_registry

from .decision import route_for_intent

_CATEGORY_DOMAIN = {
    "web": "web", "browser": "browser", "system": "system", "desktop": "desktop",
    "conversation": "conversation", "workflow": "workflow", "general": "desktop",
}

# (text, intent) — the TALK / conversation bucket (WHEN-gate "just talking" side)
_CONVERSATION: list[tuple[str, str]] = [
    ("hello", "greeting"), ("hi", "greeting"), ("hey there", "greeting"),
    ("good morning", "greeting"), ("good evening", "greeting"),
    ("who are you", "identity"), ("what are you", "identity"), ("what is your name", "identity"),
    ("thanks", "social_close"), ("thank you", "social_close"),
    ("goodbye", "social_close"), ("bye", "social_close"),
    ("what is", "general_qa"), ("who is", "general_qa"), ("what are", "general_qa"),
    ("why is", "general_qa"), ("why do", "general_qa"), ("how does", "general_qa"),
    ("how do i", "general_qa"), ("tell me about", "general_qa"),
    ("what do you think", "general_qa"), ("what is the capital of", "general_qa"),
    ("what is the meaning of", "general_qa"), ("how far is", "general_qa"),
    ("when did", "general_qa"), ("where is", "general_qa"), ("do you know", "general_qa"),
    ("can you tell me", "general_qa"), ("explain", "explain"), ("summarize this", "summarize"),
]

_CORR_PATH = os.path.join("data", "nexi", "router", "corrections.jsonl")


def _stakes(safety: str, confirm: bool) -> str:
    if confirm or safety in ("high", "critical"):
        return "high"
    if safety == "medium":
        return "medium"
    return "low"


@dataclass
class Exemplar:
    text: str
    intent: str
    domain: str
    route: str
    stakes: str


@dataclass
class ExemplarBank:
    entries: list[Exemplar]

    def texts(self) -> list[str]:
        return [e.text for e in self.entries]

    def add(self, text: str, intent: str, domain: str, route: str, stakes: str) -> None:
        text = (text or "").strip().lower()
        if text:
            self.entries.append(Exemplar(text, intent, domain, route, stakes))

    def add_correction(self, utterance: str, corrected_intent: str) -> None:
        spec = tool_registry.get_tool(corrected_intent)
        if spec:
            self.add(
                utterance, corrected_intent,
                _CATEGORY_DOMAIN.get(spec.get("category", "general"), "desktop"),
                route_for_intent(corrected_intent),
                _stakes(spec.get("safety", "low"), spec.get("requires_confirmation", False)),
            )
        else:
            self.add(utterance, corrected_intent, "conversation",
                     route_for_intent(corrected_intent), "low")


def build_bank() -> ExemplarBank:
    """Build the bank from the tool registry + conversation bucket + saved corrections."""
    entries: list[Exemplar] = []
    for spec in tool_registry.list_tools():
        if not spec.get("enabled", True):
            continue
        intent = spec["name"]
        domain = _CATEGORY_DOMAIN.get(spec.get("category", "general"), "desktop")
        route = route_for_intent(intent)
        stakes = _stakes(spec.get("safety", "low"), spec.get("requires_confirmation", False))
        phrases: set[str] = {intent.replace("_", " ")}
        desc = (spec.get("description") or "").strip().lower()
        if desc:
            phrases.add(desc)
        for alias in spec.get("aliases") or ():
            if alias.strip():
                phrases.add(alias.strip().lower())
        for example in spec.get("examples") or ():
            if example.strip():
                phrases.add(example.strip().lower())
        for phrase in phrases:
            entries.append(Exemplar(phrase, intent, domain, route, stakes))
    for text, intent in _CONVERSATION:
        entries.append(Exemplar(text, intent, "conversation", route_for_intent(intent), "low"))
    bank = ExemplarBank(entries)
    _load_corrections(bank)
    return bank


def _load_corrections(bank: ExemplarBank) -> None:
    try:
        with open(_CORR_PATH, encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                bank.add_correction(rec["utterance"], rec["corrected_intent"])
    except FileNotFoundError:
        return
    except Exception:  # a corrupt corrections file must never break routing
        return


def save_correction(utterance: str, corrected_intent: str) -> None:
    """Persist a correction so it seeds the bank on next build (learns the user)."""
    os.makedirs(os.path.dirname(_CORR_PATH), exist_ok=True)
    with open(_CORR_PATH, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(
            {"utterance": (utterance or "").strip().lower(), "corrected_intent": corrected_intent}
        ) + "\n")


def _demo() -> None:
    bank = build_bank()
    intents = {e.intent for e in bank.entries}
    assert "open_app" in intents and "general_qa" in intents
    assert len(bank.entries) > 300, len(bank.entries)
    # correction growth
    n = len(bank.entries)
    bank.add_correction("fire up the browser", "open_app")
    assert len(bank.entries) == n + 1
    print(f"exemplars._demo OK  ({len(bank.entries)} exemplars, {len(intents)} intents)")


if __name__ == "__main__":
    _demo()
