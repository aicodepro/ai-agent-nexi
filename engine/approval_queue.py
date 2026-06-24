"""Human Approval Queue v2 (Roadmap Feature #10) — gate risky actions behind approval.

Tool cards
----------
pending_approvals role: action gate | risk: LOW | confirm: never | verifier: queue read        | memory: never store
approve_action    role: action gate | risk: LOW | confirm: never | verifier: action executed     | memory: never store
reject_action     role: action gate | risk: LOW | confirm: never | verifier: action removed       | memory: never store

Risk policy (per roadmap): low → execute, medium → confirm, high → explicit approval,
critical → explicit approval (treated as high+). Dangerous tools call `gate(...)`; if the
action needs approval and isn't yet approved, it is queued and a requires-approval result is
returned instead of acting. `approve_action` re-runs the stored action with approved=True.
The gate is invoked BY the dangerous tools — the core execute_tool path is unchanged, so
existing low/medium tools are entirely unaffected.
"""

from __future__ import annotations

import itertools
import time
from typing import Any

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_APPROVAL_FLOOR = _RISK_ORDER["high"]

_counter = itertools.count(1)
_pending: dict[str, dict[str, Any]] = {}


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "approval_queue"), "message": message, **extra}


def requires_approval(risk: str) -> bool:
    return _RISK_ORDER.get(str(risk or "low"), 0) >= _APPROVAL_FLOOR


def submit(tool: str, slots: dict | None, risk: str, description: str) -> str:
    aid = f"act{next(_counter)}"
    _pending[aid] = {
        "id": aid, "tool": tool, "slots": dict(slots or {}), "risk": str(risk or "low"),
        "description": description or tool, "status": "pending", "created": time.time(),
    }
    print(f"[APPROVAL] queued id={aid} tool={tool} risk={risk}", flush=True)
    return aid


def list_pending() -> list[dict[str, Any]]:
    return [a for a in _pending.values() if a["status"] == "pending"]


def get(aid: str) -> dict[str, Any] | None:
    return _pending.get(aid)


def reject(aid: str) -> bool:
    action = _pending.get(aid)
    if action and action["status"] == "pending":
        action["status"] = "rejected"
        print(f"[APPROVAL] rejected id={aid}", flush=True)
        return True
    return False


def approve(aid: str) -> dict[str, Any]:
    action = _pending.get(aid)
    if not action:
        return {"success": False, "verified": False, "tool": "approve_action", "message": f"No pending action '{aid}'."}
    if action["status"] != "pending":
        return {"success": False, "verified": False, "tool": "approve_action", "message": f"Action {aid} is already {action['status']}."}
    action["status"] = "approved"
    from engine.tool_registry import execute_tool
    result = execute_tool(action["tool"], {**action["slots"], "approved": True})
    action["status"] = "executed" if result.get("success") else "failed"
    print(f"[APPROVAL] {action['status']} id={aid} tool={action['tool']}", flush=True)
    return result


def clear() -> None:
    _pending.clear()


def gate(tool: str, slots: dict | None, risk: str, description: str) -> dict[str, Any] | None:
    """Return a requires-approval result if this action must be approved first, else None to proceed."""
    if (slots or {}).get("approved"):
        return None
    if not requires_approval(risk):
        return None
    aid = submit(tool, slots, risk, description)
    return {"handled": True, "ok": False, "success": False, "verified": False, "tool": tool,
            "requires_approval": True, "approval_id": aid, "risk": risk,
            "message": f"\"{description}\" needs approval (risk: {risk}). Say 'approve' to proceed or 'reject' to cancel."}


# ── Voice tools ──────────────────────────────────────────────────────────────
def pending_approvals(slots: dict | None = None) -> dict[str, Any]:
    items = list_pending()
    if not items:
        return _ok("There are no actions waiting for approval.", tool="pending_approvals", count=0, pending=[])
    preview = "; ".join(f"{a['id']}: {a['description']} ({a['risk']})" for a in items[:5])
    return _ok(f"{len(items)} action(s) waiting for approval: {preview}.",
               tool="pending_approvals", count=len(items),
               pending=[{"id": a["id"], "description": a["description"], "risk": a["risk"]} for a in items])


def approve_action(slots: dict | None = None) -> dict[str, Any]:
    aid = str((slots or {}).get("id") or (slots or {}).get("approval_id") or "").strip()
    items = list_pending()
    if not aid:
        if not items:
            return _ok("There's nothing to approve.", tool="approve_action", count=0)
        aid = items[0]["id"]
    result = approve(aid)
    if result.get("success"):
        return _ok(f"Approved and done. {result.get('message', '')}".strip(), tool="approve_action",
                   approved=aid, result_message=result.get("message", ""))
    return {"handled": True, "ok": False, "success": False, "verified": False, "tool": "approve_action",
            "message": result.get("message", "I couldn't approve that action.")}


def reject_action(slots: dict | None = None) -> dict[str, Any]:
    aid = str((slots or {}).get("id") or (slots or {}).get("approval_id") or "").strip()
    items = list_pending()
    if not aid:
        if not items:
            return _ok("There's nothing to reject.", tool="reject_action", count=0)
        aid = items[0]["id"]
    ok = reject(aid)
    if ok:
        return _ok(f"Rejected action {aid}.", tool="reject_action", rejected=aid)
    return {"handled": True, "ok": False, "success": False, "verified": False, "tool": "reject_action",
            "message": f"I couldn't find a pending action '{aid}' to reject."}
