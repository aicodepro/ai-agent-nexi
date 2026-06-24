from __future__ import annotations

import re


_ALIASES = {
    "coding": ["fix code", "debug", "bug", "patch", "refactor", "test failure", "python error", "next.js component", "react component"],
    "seo": ["seo", "seo audit", "rank", "ranking", "technical seo", "metadata", "schema markup", "search console"],
    "sales": ["sales", "sales call", "client message", "lead", "follow up", "cta", "proposal"],
    "client demo": ["client demo", "demo", "presentation", "pitch", "polished", "walkthrough"],
    "founder": ["founder", "strategy", "pitch deck", "investor", "positioning"],
    "nexi debugging": ["nexi is not", "nexi failed", "nexi debugging", "voice not", "tts", "asr", "hotword"],
    "ui design": ["ui", "ux", "design", "layout", "visual", "component"],
    "content writing": ["content", "blog", "copy", "write", "caption"],
}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def get_need_aliases() -> dict:
    return {key: list(value) for key, value in _ALIASES.items()}


def score_need_match(user_text: str, profile: dict) -> float:
    text = _norm(user_text)
    if not text:
        return 0.0
    aliases = list(profile.get("aliases", []) or [])
    need = _norm(profile.get("need_name") or profile.get("need") or "")
    if need:
        aliases.append(need)
    matched = [alias for alias in aliases if alias and _norm(alias) in text]
    if not matched:
        return 0.0
    return min(0.99, 0.70 + 0.08 * len(matched))


def detect_need(user_text: str, context: dict | None = None) -> dict:
    text = _norm(user_text)
    best = {"need": "", "confidence": 0.0, "matched_aliases": [], "reason": "no need detected"}
    for need, aliases in _ALIASES.items():
        matched = [alias for alias in aliases if alias in text]
        if matched:
            confidence = min(0.95, 0.68 + 0.07 * len(matched))
            if confidence > best["confidence"]:
                best = {"need": need, "confidence": confidence, "matched_aliases": matched, "reason": f"{need} language detected"}
    try:
        from engine.training_profile_store import list_profiles
        profile_available = any(p.get("enabled", True) and _norm(p.get("need_name")) == best.get("need") for p in list_profiles())
    except Exception:
        profile_available = False
    print(f"[NEED] detected={best.get('need') or 'none'} confidence={float(best.get('confidence', 0.0)):.2f}", flush=True)
    print(f"[NEED] profile_available={str(profile_available).lower()}", flush=True)
    best["profile_available"] = profile_available
    return best
