from __future__ import annotations

import json
from pathlib import Path
from typing import Any


MANIFEST_PATH = Path(__file__).resolve().parents[1] / "config" / "tool_manifest.json"


def _read_manifest(path: str | Path | None = None) -> dict[str, Any]:
    target = Path(path) if path else MANIFEST_PATH
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception as exc:
        print(f"[TOOL_MANIFEST] load_failed reason={type(exc).__name__}", flush=True)
        return {}


def _registered_tool(name: str) -> dict | None:
    try:
        from engine.tool_registry import get_tool

        return get_tool(name)
    except Exception:
        return None


def validate_manifest_entry(entry: dict[str, Any]) -> tuple[bool, str]:
    if not isinstance(entry, dict):
        return False, "entry_not_object"
    name = str(entry.get("name") or "").strip()
    if not name:
        return False, "missing_name"
    tool = _registered_tool(name)
    if not tool:
        return False, "tool_not_registered"
    required = entry.get("required_slots", [])
    if not isinstance(required, list):
        return False, "required_slots_not_list"
    optional = entry.get("optional_slots", [])
    if not isinstance(optional, list):
        return False, "optional_slots_not_list"
    aliases = entry.get("aliases", [])
    if not isinstance(aliases, list):
        return False, "aliases_not_list"
    handler = str(entry.get("handler") or "").strip()
    if not handler:
        return False, "missing_handler"
    registered_required = set(tool.get("required_slots") or [])
    if not set(str(slot) for slot in required).issubset(registered_required):
        return False, "required_slot_not_registered"
    risk = str(entry.get("risk_level") or entry.get("safety") or "none").lower()
    if risk not in {"none", "low", "medium", "high", "critical"}:
        return False, "invalid_risk"
    confirmation = bool(entry.get("confirmation_required", entry.get("requires_confirmation", False)))
    if risk in {"medium", "high", "critical"} and not confirmation:
        return False, "risky_tool_without_confirmation"
    return True, "ok"


def load_tool_manifest(path: str | Path | None = None) -> dict[str, Any]:
    raw = _read_manifest(path)
    entries = raw.get("tools", {}) if isinstance(raw, dict) else {}
    valid: list[dict[str, Any]] = []
    invalid = 0
    if isinstance(entries, list):
        iterable = entries
    elif isinstance(entries, dict):
        iterable = entries.values()
    else:
        iterable = []
    for entry in iterable:
        ok, reason = validate_manifest_entry(entry)
        if ok:
            valid.append(dict(entry))
        else:
            invalid += 1
            print(f"[TOOL_MANIFEST] invalid_entry reason={reason}", flush=True)
    print(f"[TOOL_MANIFEST] loaded valid={len(valid)} invalid={invalid}", flush=True)
    return {"schema_version": str(raw.get("schema_version") or "1.0"), "tools": valid}


def get_manifest_tool(name: str) -> dict[str, Any] | None:
    target = str(name or "").strip()
    for entry in load_tool_manifest().get("tools", []):
        if entry.get("name") == target:
            return dict(entry)
    return None


def tool_names_for_router() -> list[str]:
    return [str(entry.get("name")) for entry in load_tool_manifest().get("tools", []) if entry.get("name")]


def router_capability_manifest() -> list[dict[str, Any]]:
    """Registry-sourced compact tool cards for the LLM router.

    The runtime registry is the source of truth so the router can never be blind
    to a registered, executable feature. The JSON manifest is treated only as an
    optional overlay that contributes extra aliases/examples — it can never hide
    or drop a registered tool.
    """
    try:
        from engine.tool_registry import router_tool_manifest

        cards = {card["name"]: dict(card) for card in router_tool_manifest()}
    except Exception as exc:
        print(f"[TOOL_MANIFEST] registry_unavailable reason={type(exc).__name__}", flush=True)
        return []
    # Overlay JSON manifest aliases/examples without dropping registry tools.
    for entry in load_tool_manifest().get("tools", []):
        name = str(entry.get("name") or "")
        if name in cards:
            extra_aliases = [a for a in (entry.get("aliases") or []) if a not in cards[name]["aliases"]]
            cards[name]["aliases"] = cards[name]["aliases"] + extra_aliases
    return list(cards.values())


def router_tool_names() -> list[str]:
    """Every enabled, executable tool name the router may select."""
    return [card["name"] for card in router_capability_manifest()]
