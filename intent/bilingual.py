"""Bilingual (Hindi/Hinglish -> English) command normalizer.

Hindi commands are typically verb-final ("chrome kholo" = "open chrome").
This maps common romanized Hindi words to English and moves a trailing
command verb to the front so the deterministic router can match it.
"""

import re

# Trailing/standalone command verbs -> English leading verb
_VERBS = {
    "kholo": "open", "khol": "open", "kholdo": "open", "kholna": "open",
    "band": "close", "bandkaro": "close", "bandkar": "close",
    "bajao": "play", "baja": "play", "chalao": "play", "chala": "play",
    "dikhao": "show", "dikha": "show", "dhundo": "find", "dhoondo": "find",
    "search": "search", "khojo": "search",
}

# Auxiliary/filler tokens dropped before reordering ("kar do", "zara", "please")
_AUX = {"karo", "kardo", "kar", "do", "de", "dedo", "zara", "please", "na"}

# General word replacements
_WORDS = {
    "mausam": "weather", "samay": "time", "waqt": "time",
    "kya": "what", "kaun": "who", "kaise": "how", "kyun": "why", "kahan": "where",
    "batao": "tell me", "bata": "tell me", "sunao": "tell me",
    "screenshot": "screenshot", "gaana": "music", "gana": "music",
    "phone": "phone", "email": "email",
}


def _has_hindi(tokens) -> bool:
    return any(t in _VERBS or t in _WORDS for t in tokens)


def normalize(text: str) -> str:
    """Return an English-normalized command, or the original if no Hindi found."""
    raw = text.strip()
    tokens = re.sub(r"[^\w\s]", "", raw.lower()).split()
    if not tokens or not _has_hindi(tokens):
        return raw

    # Drop trailing auxiliaries ("band karo" -> "band")
    while len(tokens) > 1 and tokens[-1] in _AUX:
        tokens.pop()

    # Trailing command verb -> move to front: "chrome kholo" -> "open chrome"
    if tokens[-1] in _VERBS:
        verb = _VERBS[tokens[-1]]
        rest = [_WORDS.get(t, t) for t in tokens[:-1]]
        return (verb + " " + " ".join(rest)).strip()

    # Otherwise inline-replace known words/verbs in place
    out = []
    for t in tokens:
        if t in _VERBS:
            out.append(_VERBS[t])
        else:
            out.append(_WORDS.get(t, t))
    return " ".join(out).strip()
