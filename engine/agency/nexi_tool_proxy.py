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


def _failure(tool_name: str, status: str, code: str, message: str, exc: Exception | None = None) -> dict[str, Any]:
    return {
        "success": False,
        "verified": False,
        "tool": tool_name,
        "status": status,
        "message": message,
        "error": {
            "code": code,
            "type": type(exc).__name__ if exc else "",
            "message": str(exc) if exc else message,
        },
    }


def request_tool(tool_name: str, args: dict | None = None, risk: str = "low", reason: str = "") -> dict[str, Any]:
    args = dict(args or {})
    try:
        from engine.tool_registry import get_tool, execute_tool
    except Exception as exc:
        return _failure(tool_name, "tool_not_available", "tool_registry_unavailable",
                        "Tool registry unavailable.", exc)
    try:
        tool = get_tool(tool_name)
    except Exception as exc:
        return _failure(tool_name, "tool_not_available", "tool_registry_unavailable",
                        "Tool registry unavailable.", exc)
    if tool is None:
        return _failure(tool_name, "tool_not_available", "tool_not_found",
                        f"Tool '{tool_name}' is not available.")

    try:
        from engine.agency.workflow_engine import autonomy_mode
        mode = autonomy_mode()
    except Exception:
        mode = "supervised"
    risk = str(risk or "low").lower()

    if mode == "locked":
        return _failure(tool_name, "rejected", "agency_locked",
                        "Agency is in locked mode; no tools may run.")

    needs_approval = (mode == "manual") or (risk not in _SAFE)
    if needs_approval:
        try:
            from engine import approval_queue
            gated = approval_queue.gate(tool_name, args, risk, reason or f"agency tool {tool_name}")
            if gated:  # queued for approval — NOT executed
                return {**gated, "status": "waiting_for_approval"}
            return _failure(tool_name, "rejected", "approval_not_recorded",
                            "Approval gate did not record the request; refusing action.")
        except Exception as exc:
            return _failure(tool_name, "rejected", "approval_gate_unavailable",
                            "Approval gate unavailable; refusing action.", exc)

    try:
        result = execute_tool(tool_name, args)  # low-risk in supervised/autonomous_safe (or approved)
    except Exception as exc:
        return _failure(tool_name, "failed", "tool_execution_failed", str(exc), exc)
    if not isinstance(result, dict):
        return _failure(tool_name, "failed", "invalid_tool_result",
                        "Tool returned a non-structured result.")
    result["status"] = "executed" if result.get("verified") else "failed"
    if not result.get("verified"):
        result.setdefault("error", {
            "code": "tool_not_verified",
            "type": "",
            "message": str(result.get("message") or "Tool result was not verified."),
        })
    return result


if __name__ == "__main__":
    assert request_tool("definitely_not_a_tool")["status"] == "tool_not_available"
    r = request_tool("click_ui_element", {"target": "Pay"}, risk="critical", reason="test")
    assert r["status"] == "waiting_for_approval" and r.get("verified") is not True, r
    print("OK nexi tool proxy")
