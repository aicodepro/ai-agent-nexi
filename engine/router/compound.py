"""Stage 2a — compound command splitting (multi-tasking).

Turns "open chrome then go to youtube.com and play techno gamer" into the ordered
steps ["open chrome", "go to youtube.com", "play techno gamer"] so each can be
routed and executed in turn.

Deterministic + offline. Splits on explicit sequence markers (then / and then /
after that / next / ;) and on "and <action-verb>" — but NOT on a bare "and" that
merely joins objects ("search for cats and dogs" stays one command). The verb
guard is what keeps it from over-splitting.
"""
from __future__ import annotations

import re

# strong, order-indicating separators
_SEQ = re.compile(
    # NOTE: bare "next" was removed — it split ordinary phrases ("what is the next
    # step", "play the next song", "open the next tab") into fake multi-step tasks.
    # "then" / "and then" / "after that" cover real sequencing without the homograph.
    r"\s*(?:;|,\s*(?=then\b)|\bthen\b|\band then\b|\bafter that\b|\bafter which\b|\bfollowed by\b)\s*",
    re.I,
)

# Action verbs that legitimately start a new step after "and".
# NOTE: "go" and "google" were removed — as the LAST word they are almost always
# NOUNS ("python and go", "bing and google"), which produced fake react plans on
# plain questions. Real intents are covered by goto/navigate/visit and search.
_VERBS = (
    "open", "close", "launch", "start", "stop", "goto", "visit", "navigate",
    "play", "pause", "resume", "search", "find", "look", "show", "tell",
    "take", "create", "make", "turn", "set", "mute", "unmute", "read", "write",
    "send", "check", "run", "kill", "minimize", "maximize", "switch", "type", "click",
    "save", "download", "upload", "install", "delete", "remove", "copy", "move",
    "email", "remind", "record", "screenshot", "summarize", "translate", "paste",
)
_AND_VERB = re.compile(r"\s+and\s+(?=(?:" + "|".join(_VERBS) + r")\b)", re.I)

_LEAD = re.compile(r"^(?:and|then|also|please|,)\s+", re.I)


def split_steps(text: str) -> list[str]:
    """Split a compound utterance into ordered atomic commands.

    Returns a single-element list if the text isn't compound.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    parts: list[str] = []
    for chunk in _SEQ.split(raw):
        parts.extend(_AND_VERB.split(chunk))
    steps: list[str] = []
    for part in parts:
        part = _LEAD.sub("", (part or "").strip()).strip(" ,.")
        if part:
            steps.append(part)
    return steps or [raw]


def _demo() -> None:
    assert split_steps("open chrome then go to youtube.com and play techno gamer") == \
        ["open chrome", "go to youtube.com", "play techno gamer"]
    assert split_steps("open chrome and mute") == ["open chrome", "mute"]
    # must NOT over-split objects joined by 'and'
    assert split_steps("search for cats and dogs") == ["search for cats and dogs"]
    assert split_steps("turn up the volume and brightness") == ["turn up the volume and brightness"]
    # not compound
    assert split_steps("what time is it") == ["what time is it"]
    assert split_steps("take a screenshot; open notepad") == ["take a screenshot", "open notepad"]
    print("compound._demo OK")


if __name__ == "__main__":
    _demo()
