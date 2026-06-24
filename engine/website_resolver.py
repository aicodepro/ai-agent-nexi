from __future__ import annotations

import re


WEBSITE_ALIASES = {
    "yt": "youtube.com",
    "youtube": "youtube.com",
    "youtube.com": "youtube.com",
    "gmail": "mail.google.com",
    "mail": "mail.google.com",
    "mail.google.com": "mail.google.com",
    "github": "github.com",
    "github.com": "github.com",
    "chatgpt": "chatgpt.com",
    "chat gpt": "chatgpt.com",
    "chatgpt.com": "chatgpt.com",
}


def _norm(value: str) -> str:
    raw = str(value or "").strip().lower().rstrip(".?!")
    raw = re.sub(r"^https?://", "", raw)
    raw = raw.removeprefix("www.")
    return " ".join(raw.split())


def looks_like_website(value: str) -> bool:
    q = _norm(value)
    return q in WEBSITE_ALIASES or "." in q or q.startswith(("localhost", "127.0.0.1"))


def resolve_website(value: str) -> dict[str, str | bool]:
    raw = str(value or "").strip()
    normalized = _norm(raw)
    url = WEBSITE_ALIASES.get(normalized, normalized or raw)
    return {"matched": normalized in WEBSITE_ALIASES, "input": raw, "url": url}


def normalize_website_slot(slots: dict | None) -> dict:
    values = dict(slots or {})
    target = values.get("url") or values.get("site") or values.get("website") or values.get("target")
    if target:
        values["url"] = str(resolve_website(str(target)).get("url") or target).strip()
    values.pop("site", None)
    values.pop("website", None)
    return values
