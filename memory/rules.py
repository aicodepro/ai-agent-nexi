"""Learned trigger -> action rules ("when I say X do Y").

Unlike the free-text 'rules' memory category, these are structured mappings
that the dispatcher matches against and executes.
"""

import json
import re
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent.parent / "data" / "rules.json"

# "when I say <trigger>, <action>"  /  "when I say <trigger> do <action>"
# The action is kept verbatim (its leading verb is part of the command).
_PREFIX_RE = re.compile(r"^when i say\s+(.+)$", re.IGNORECASE)
_SPLIT_RE = re.compile(r"\s*,\s*|\s+(?:do|then|please)\s+", re.IGNORECASE)


def _norm(text: str) -> str:
    return re.sub(r"[^\w\s%]", "", text.strip().lower())


def _parse(text: str):
    m = _PREFIX_RE.match(text.strip())
    if not m:
        return None
    parts = _SPLIT_RE.split(m.group(1), maxsplit=1)
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return _norm(parts[0]), parts[1].strip()


def _load() -> list:
    try:
        if RULES_PATH.exists():
            return json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save(rules: list) -> None:
    RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8")


def learn_rule(text: str) -> str:
    parsed = _parse(text)
    if not parsed:
        return "Say it like: 'when I say <phrase>, <action>'."
    trigger, action = parsed
    rules = _load()
    rules = [r for r in rules if r.get("trigger") != trigger]
    rules.append({"trigger": trigger, "action": action})
    _save(rules)
    return f"Got it. When you say '{trigger}', I'll {action}."


def match_rule(text: str) -> str:
    """Return the action for a learned trigger, or '' if none matches."""
    n = _norm(text)
    for r in _load():
        if r.get("trigger") == n:
            return r.get("action", "")
    return ""


def list_rules() -> list:
    return _load()


def clear_rules() -> int:
    n = len(_load())
    _save([])
    return n
