"""Stage 5 — deterministic slot extraction.

Pulls a tool's argument values out of the utterance ("open [chrome]",
"search for [python tutorials]", "play [techno gamer] on youtube") so an action
carries real parameters. When the gpt-oss tier is on it extracts slots itself
(function-call arguments); this is the offline/Tier-0 path.

If a required slot is still missing after extraction, the pipeline asks exactly
for it ("Which app should I open?") instead of acting blind.
"""
from __future__ import annotations

import re

from engine import tool_registry

from .normalize import Normalized

# leading trigger phrases to strip so the remainder is the free-text argument.
# longest first so "search the web for" wins over "search".
_LEAD = sorted([
    "fire up", "open up", "go to", "navigate to", "search youtube for",
    "search the web for", "search for", "look up", "take a note that",
    "take a note", "note that", "remember that", "create a folder called",
    "create folder", "create a file called", "create file", "open", "launch",
    "start", "run", "play", "visit", "search", "google", "find", "note",
    "remember", "forget", "make",
], key=len, reverse=True)
_LEAD_RE = re.compile(r"^(?:" + "|".join(re.escape(p) for p in _LEAD) + r")\b\s*", re.I)
_DOMAIN_RE = re.compile(r"[\w-]+\.\w{2,}")


def _strip_lead(text: str) -> str:
    match = _LEAD_RE.match(text.strip())
    return text.strip()[match.end():].strip() if match else text.strip()


def _youtube_query(norm: Normalized) -> dict:
    text = re.sub(r"\b(?:on|at)\s+(?:youtube|yt)\b", "", norm.canonical, flags=re.I)
    text = re.sub(r"^\s*(?:play|search youtube for|search for|search|youtube)\b\s*", "", text, flags=re.I)
    text = text.strip()
    return {"query": text} if text else {}


def _website(norm: Normalized) -> dict:
    domain = _DOMAIN_RE.search(norm.raw)  # raw preserves the dot ("youtube.com")
    url = domain.group(0).lower() if domain else _strip_lead(norm.canonical)
    return {"url": url} if url else {}


_SPECIFIC = {
    "search_youtube": _youtube_query,
    "play_youtube": _youtube_query,
    "open_website": _website,
}


def extract_slots(intent: str, norm: Normalized) -> dict:
    spec = tool_registry._TOOLS.get(intent)
    if spec is None or not spec.required_slots:
        return {}
    specific = _SPECIFIC.get(intent)
    if specific:
        return specific(norm)
    if len(spec.required_slots) == 1:
        slot = spec.required_slots[0]
        stripped = _strip_lead(norm.canonical)
        # only fill if a lead verb was actually removed (so a bare trigger word
        # like "open" stays unfilled -> pipeline asks "which app?")
        if stripped and stripped != norm.canonical.strip():
            return {slot: stripped}
        if stripped and slot in ("query", "text"):  # query/note tools take the whole phrase
            return {slot: stripped}
    return {}


def _demo() -> None:
    def n(text):
        from .normalize import normalize
        return normalize(text)

    assert extract_slots("open_app", n("open google chrome")) == {"app_name": "google chrome"}
    assert extract_slots("open_app", n("open")) == {}                     # bare -> ask
    assert extract_slots("web_search", n("search for python tutorials")) == {"query": "python tutorials"}
    assert extract_slots("search_youtube", n("play techno gamer on youtube")) == {"query": "techno gamer"}
    assert extract_slots("open_website", n("go to youtube.com")) == {"url": "youtube.com"}
    assert extract_slots("tell_time", n("what time is it")) == {}         # zero-slot tool
    print("slots._demo OK")


if __name__ == "__main__":
    _demo()
