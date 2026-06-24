from __future__ import annotations

import re


def get_last_spoken_words(text: str, count: int = 2) -> str:
    words = re.findall(r"[\w']+", str(text or ""))
    if not words or count <= 0:
        return ""
    return " ".join(words[-count:])
