"""Safety boundary for CrewAI-style agents. NO agent touches the PC directly.

Every workflow tool call routes here: low-risk executes via the real registry+verifier;
medium/high/critical goes through Nexi's approval gate (queued, never executed directly);
unknown/unsafe tools are refused. Reuses engine.tool_registry + engine.approval_queue —
no new safety logic invented.
"""

from __future__ import annotations

from typing import Any

_SAFE = {"low", "none"}


def request_tool(tool_name: str, args: dict | None = None, risk: str = "low", reason: str = "") -> dict[str, Any]:
    args = dict(args or {})
    try:
        from engine.tool_registry import get_tool, execute_tool
    except Exception:
        return {"success": False, "verified": False, "tool": tool_name,
                "status": "tool_not_available", "message": "Tool registry unavailable."}
    if get_tool(tool_name) is None:
        return {"success": False, "verified": False, "tool": tool_name,
                "status": "tool_not_available", "message": f"Tool '{tool_name}' is not available."}

    if str(risk or "low").lower() not in _SAFE:
        try:
            from engine import approval_queue
            gated = approval_queue.gate(tool_name, args, str(risk).lower(), reason or f"workflow tool {tool_name}")
            if gated:  # queued for approval — NOT executed
                return {**gated, "status": "waiting_for_approval"}
        except Exception:
            return {"success": False, "verified": False, "tool": tool_name,
                    "status": "rejected", "message": "Approval gate unavailable; refusing risky action."}

    result = execute_tool(tool_name, args)  # low-risk (or approved) -> real execute + verify
    result["status"] = "executed" if result.get("verified") else "failed"
    return result


if __name__ == "__main__":
    assert request_tool("definitely_not_a_tool")["status"] == "tool_not_available"
    r = request_tool("click_ui_element", {"target": "Pay"}, risk="critical", reason="test")
    assert r["status"] == "waiting_for_approval" and r.get("verified") is not True, r
    print("OK tool proxy")
