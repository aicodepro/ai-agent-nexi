"""Safety boundary for Nexi Agency agents. NO agent touches the PC directly.

Every workflow tool call routes here, gated by the autonomy mode AND the action risk:
  locked          -> refuse all tools
  manual          -> every tool needs approval
  supervised      -> low-risk auto, write/risky -> approval  (default)
  autonomous_safe -> low-risk auto, medium/high/critical -> approval
Low-risk executes via the real registry + verifier; risky goes through Nexi's approval gate
(queued, never executed directly); unknown tools are refused. Reuses engine.tool_registry +
engine.approval_queue — no new safety logic invented.
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

    try:
        from engine.agency.workflow_engine import autonomy_mode
        mode = autonomy_mode()
    except Exception:
        mode = "supervised"
    risk = str(risk or "low").lower()

    if mode == "locked":
        return {"success": False, "verified": False, "tool": tool_name,
                "status": "rejected", "message": "Agency is in locked mode; no tools may run."}

    needs_approval = (mode == "manual") or (risk not in _SAFE)
    if needs_approval:
        try:
            from engine import approval_queue
            gated = approval_queue.gate(tool_name, args, risk, reason or f"agency tool {tool_name}")
            if gated:  # queued for approval — NOT executed
                return {**gated, "status": "waiting_for_approval"}
        except Exception:
            return {"success": False, "verified": False, "tool": tool_name,
                    "status": "rejected", "message": "Approval gate unavailable; refusing action."}

    result = execute_tool(tool_name, args)  # low-risk in supervised/autonomous_safe (or approved)
    result["status"] = "executed" if result.get("verified") else "failed"
    return result


if __name__ == "__main__":
    assert request_tool("definitely_not_a_tool")["status"] == "tool_not_available"
    r = request_tool("click_ui_element", {"target": "Pay"}, risk="critical", reason="test")
    assert r["status"] == "waiting_for_approval" and r.get("verified") is not True, r
    print("OK nexi tool proxy")
