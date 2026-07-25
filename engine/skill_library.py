"""Skill Library (Roadmap Feature #13, read-only surface) — Nexi's capability catalog.

Tool cards
----------
list_skills    role: procedure memory | risk: LOW | confirm: never | verifier: catalog built from registry | memory: never store
describe_skill role: procedure memory | risk: LOW | confirm: never | verifier: skill looked up             | memory: never store

READ-ONLY introspection over the live tool registry — "what can you do?" and "how do I use
<skill>?". Durable workflow recording/replay (create_skill_from_trace) is intentionally
deferred: per the audit, build the data model + read surface first, gate replay behind the
verifier. These tools never execute or modify a skill — they only describe capabilities.
"""

from __future__ import annotations

from typing import Any


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "skill_library"), "message": message, **extra}


def _fail(message: str, tool: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": False, "success": False, "verified": False,
            "tool": tool, "message": message, **extra}


def capability_catalog() -> dict[str, Any]:
    """Group every enabled registered tool by category. Pure / read-only."""
    try:
        from engine.tool_registry import router_tool_manifest
        cards = router_tool_manifest()
    except Exception:
        cards = []
    categories: dict[str, dict[str, Any]] = {}
    for card in cards:
        cat = str(card.get("category") or "general")
        bucket = categories.setdefault(cat, {"count": 0, "tools": []})
        bucket["count"] += 1
        bucket["tools"].append(card.get("name"))
    return {"total": len(cards), "categories": categories}


def list_skills(slots: dict | None = None) -> dict[str, Any]:
    catalog = capability_catalog()
    cats = catalog["categories"]
    if not catalog["total"]:
        return _ok("I don't have any skills registered yet.", tool="list_skills", total=0, categories={})
    summary = ", ".join(f"{name} ({info['count']})"
                        for name, info in sorted(cats.items(), key=lambda kv: -kv[1]["count"]))
    msg = (f"I can do {catalog['total']} things across {len(cats)} areas — {summary}. "
           f"Ask 'tool help <name>' for any of them.")
    return _ok(msg, tool="list_skills", total=catalog["total"], categories=cats)


def describe_skill(slots: dict | None = None) -> dict[str, Any]:
    name = str((slots or {}).get("name") or (slots or {}).get("skill") or (slots or {}).get("text") or "").strip()
    if not name:
        return _fail("Which skill should I describe?", "describe_skill",
                     expects_user_reply=True, missing_slot="name")
    try:
        from engine.tool_registry import get_tool, alias_index
        tool = get_tool(name)
        if not tool:
            canonical = alias_index().get(name.lower())
            tool = get_tool(canonical) if canonical else None
    except Exception:
        tool = None
    if not tool:
        return _ok(f"I don't have a skill called '{name}'. Say 'what can you do' to hear my skills.",
                   tool="describe_skill", found=False, query=name)
    examples = tool.get("examples") or []
    example = examples[0] if examples else ""
    risk = tool.get("safety", "low")
    desc = tool.get("description", "")
    msg = f"{tool.get('name')}: {desc}." + (f" For example, '{example}'." if example else "") + f" Risk level: {risk}."
    return _ok(msg, tool="describe_skill", found=True, skill=tool.get("name"),
               description=desc, examples=examples, risk=risk)
