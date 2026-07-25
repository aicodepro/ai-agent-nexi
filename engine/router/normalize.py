"""Stage 0 — light text normalization.

Fixes ASR slips, strips wake-words/fillers, and folds a few Hinglish command
verbs to English BEFORE matching, so "oren chrom please", "chrome kholo" and
"open Chrome!" all reduce toward the same canonical form.

Deliberately LIGHT: no stemming/lemmatization — aggressive normalization strips
signal the semantic layer needs (research note in the design spec). We keep the
raw text too, so the LLM tier can see exactly what the user said.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# fillers safe to drop (single tokens). NOTE: "like"/"ok" intentionally NOT here
# — they carry meaning too often ("what's it like", "ok computer").
_FILLERS = {"um", "uh", "umm", "uhh", "er", "erm", "please", "pls", "plz", "kindly"}

# leading wake/address prefixes to strip once
_WAKE_PREFIX = re.compile(r"^(?:hey\s+|ok\s+|okay\s+)?nexi[,\s]+", re.I)

# common Hinglish command tokens -> English (verbs + a few particles)
_HINGLISH = {
    "kholo": "open", "khol": "open", "kholna": "open",
    "kardo": "do", "karo": "do", "kar": "do",
    "dikhao": "show", "dikha": "show", "dikhaao": "show",
    "batao": "tell", "bata": "tell", "bta": "tell",
    "bandh": "close", "band": "close", "bandkaro": "close",
    "chalao": "play", "chala": "play", "chalu": "start",
    "dhoondo": "search", "dhundo": "search", "khojo": "search",
    "banao": "create", "bana": "create",
}

_CONTRACTIONS = {
    "what's": "what is", "whats": "what is", "who's": "who is", "whos": "who is",
    "how's": "how is", "hows": "how is", "where's": "where is", "wheres": "where is",
    "i'm": "i am", "im": "i am", "don't": "do not", "dont": "do not",
    "can't": "can not", "cant": "can not", "it's": "it is", "its": "it is",
    "let's": "let us", "lets": "let us", "won't": "will not",
}


@dataclass
class Normalized:
    canonical: str      # cleaned, filler-stripped, Hinglish-folded
    raw: str            # exactly what came in (for the LLM tier)
    tokens: list[str]


def normalize(text: str) -> Normalized:
    raw = (text or "").strip()
    low = raw.lower()
    low = _WAKE_PREFIX.sub("", low, count=1)
    # expand contractions on whole tokens
    low = " ".join(_CONTRACTIONS.get(t, t) for t in low.split())
    # drop punctuation except intra-word apostrophes already handled
    low = re.sub(r"[^\w\s]", " ", low)
    tokens: list[str] = []
    for tok in low.split():
        if tok in _FILLERS:
            continue
        tokens.append(_HINGLISH.get(tok, tok))
    canonical = " ".join(tokens).strip()
    if not canonical:  # never return empty — fall back to the stripped lowercase
        canonical = re.sub(r"[^\w\s]", " ", raw.lower()).strip()
        tokens = canonical.split()
    return Normalized(canonical=canonical, raw=raw, tokens=tokens)


def _demo() -> None:
    assert normalize("Hey Nexi, open Chrome!").canonical == "open chrome"
    assert normalize("chrome kholo").canonical == "chrome open"  # order preserved; folding only
    assert normalize("um please tell me the time").canonical == "tell me the time"
    assert normalize("what's the weather").canonical == "what is the weather"
    assert normalize("   ").canonical == ""
    assert normalize("youtube pe dhoondo cats").canonical == "youtube pe search cats"
    print("normalize._demo OK")


if __name__ == "__main__":
    _demo()
