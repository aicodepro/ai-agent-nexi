"""Read-only Nexi tools for agent-runtime discovery."""

from __future__ import annotations

from typing import Any

from engine.agent_runtime import registry


def runtime_status_tool(slots: dict | None = None) -> dict[str, Any]:
    requested = str((slots or {}).get("provider") or "").strip()
    try:
        if requested:
            providers = [registry.provider_status(requested)]
            selected = registry.selected_provider_id()
        else:
            selected = registry.selected_provider_id()
            providers = registry.all_provider_statuses()
    except ValueError as exc:
        return {
            "handled": True,
            "ok": False,
            "success": False,
            "verified": False,
            "tool": "nexi_agent_runtime_status",
            "message": str(exc),
        }
    current = next(item for item in providers if item["provider_id"] == selected) if not requested else providers[0]
    state = "ready" if current["enabled"] and current["available"] else "disabled" if not current["enabled"] else "unavailable"
    return {
        "handled": True,
        "ok": True,
        "success": True,
        "verified": True,
        "tool": "nexi_agent_runtime_status",
        "message": f"Nexi agent runtime is using {selected}; selected provider state is {state}.",
        "selected_provider": selected,
        "selected_state": state,
        "providers": providers,
    }
