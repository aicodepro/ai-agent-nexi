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

import hashlib
import itertools
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
_APPROVAL_FLOOR = _RISK_ORDER["high"]

# Internal marker injected ONLY by approve(); a plain user/router-supplied "approved"
# slot can never bypass the gate (the intent router cannot emit this key/value).
#
# The value is randomised per process instead of being a fixed literal. Nexi reads its own
# source (Forge, Studio, and the Claude Code integration all get repo access), so a
# hardcoded sentinel is a shared secret sitting in a file the model can open and quote back
# as a slot to self-approve a high-risk action. A per-process token cannot be recovered
# from source. It is never logged, never serialised into a tool schema, and never crosses a
# process boundary — approve() and gate() run in-process.
_APPROVAL_TOKEN_KEY = "_approval_token"
_INTERNAL_APPROVAL = f"__nexi_internal_approved__{secrets.token_urlsafe(24)}"

# Handler prefixes for tools that gate through THIS queue. Their flow is
# submit -> user approves -> re-invoked with the internal token, so the queue IS their
# confirmation step. The generic confirm gates in tool_registry.execute_tool and
# safety_gate must skip them: refusing one there means it is never queued, so
# `approve_action` has nothing to approve and the action becomes unreachable rather than
# merely confirmed. Defined here so both gates read one list instead of drifting apart.
QUEUE_GATED_HANDLER_PREFIXES = ("engine.computer_use.", "engine.browser_intelligence.")


def is_queue_gated(handler: str) -> bool:
    return str(handler or "").startswith(QUEUE_GATED_HANDLER_PREFIXES)


# ── Durability ───────────────────────────────────────────────────────────────
# The queue used to be an in-memory dict, so every pending approval vanished on
# restart WHILE the missions that requested them survived (workflow_runs.jsonl).
# A request could therefore outlive its own approval and silently never happen.
#
# Persisting it introduces the opposite hazard -- an approval that outlives the
# situation it was granted for -- so durability is paired with a TTL, a binding
# hash over (tool, arguments), and single consumption recorded BEFORE execution.
_STORE = Path(__file__).resolve().parents[1] / "data" / "memory" / "approval_queue.json"
_LOCK = threading.RLock()
_counter = itertools.count(1)
_pending: dict[str, dict[str, Any]] = {}

# Terminal states. "rejected"/"executed"/"failed" predate this and are kept so
# existing callers and stored records keep their meaning.
_LIVE = "pending"
_CONSUMED = "consumed"
_EXPIRED = "expired"


def _ttl_seconds() -> float:
    """How long an approval stays valid. Read per call so tests/.env can move it."""
    try:
        return float(os.getenv("NEXI_APPROVAL_TTL_SECONDS", "600"))
    except (TypeError, ValueError):
        return 600.0


def _binding_hash(tool: str, slots: dict | None) -> str:
    """Bind an approval to the exact action. Approving "click Submit" must not
    authorise "click Pay" if the stored record is edited in between."""
    payload = {k: v for k, v in dict(slots or {}).items() if k != _APPROVAL_TOKEN_KEY}
    blob = json.dumps({"tool": str(tool or ""), "slots": payload}, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _persist() -> None:
    # ponytail: best-effort. A storage failure must never block the safety gate --
    # the in-memory copy still gates this process, and a lost record re-queues.
    try:
        from engine.memory.local_memory import atomic_write_json

        atomic_write_json(_STORE, {"version": 1, "actions": _pending})
    except Exception:
        pass


def _expire_locked(now: float | None = None) -> None:
    now = time.time() if now is None else now
    for action in _pending.values():
        if action.get("status") == _LIVE and float(action.get("expires_at") or 0) <= now:
            action["status"] = _EXPIRED
            print(f"[APPROVAL] expired id={action.get('id')} tool={action.get('tool')}", flush=True)


def _load() -> None:
    """Reload persisted approvals. Anything past its TTL loads already expired, so a
    request cannot be silently approved long after the moment that justified it."""
    try:
        if not _STORE.exists():
            return
        with _STORE.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        actions = (data or {}).get("actions")
        if not isinstance(actions, dict):
            return
        with _LOCK:
            _pending.update({str(k): v for k, v in actions.items() if isinstance(v, dict)})
            _expire_locked()
            # Restart resets itertools.count to 1, which would re-issue an id that is
            # already on disk and let "approve act1" hit the wrong action.
            highest = 0
            for key in _pending:
                digits = "".join(ch for ch in str(key) if ch.isdigit())
                if digits:
                    highest = max(highest, int(digits))
            if highest:
                globals()["_counter"] = itertools.count(highest + 1)
    except Exception:
        # Fails closed: an unreadable store leaves nothing approvable, and gate()
        # simply re-queues. It never yields an approval.
        pass


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "approval_queue"), "message": message, **extra}


def requires_approval(risk: str) -> bool:
    return _RISK_ORDER.get(str(risk or "low"), 0) >= _APPROVAL_FLOOR


def submit(tool: str, slots: dict | None, risk: str, description: str,
           *, conversation_id: str = "", mission_id: str = "", actor_id: str = "") -> str:
    now = time.time()
    with _LOCK:
        aid = f"act{next(_counter)}"
        _pending[aid] = {
            "id": aid, "tool": tool, "slots": dict(slots or {}), "risk": str(risk or "low"),
            "description": description or tool, "status": _LIVE, "created": now,
            "requested_at": now, "expires_at": now + _ttl_seconds(),
            "binding_hash": _binding_hash(tool, slots),
            "decided_at": 0.0, "decided_by": "", "consumed_at": 0.0,
            "conversation_id": conversation_id, "mission_id": mission_id, "actor_id": actor_id,
            "version": 1,
        }
        _persist()
    print(f"[APPROVAL] queued id={aid} tool={tool} risk={risk}", flush=True)
    return aid


def list_pending() -> list[dict[str, Any]]:
    with _LOCK:
        _expire_locked()
        return [a for a in _pending.values() if a.get("status") == _LIVE]


def get(aid: str) -> dict[str, Any] | None:
    return _pending.get(aid)


def reject(aid: str) -> bool:
    with _LOCK:
        action = _pending.get(aid)
        if action and action.get("status") == _LIVE:
            action["status"] = "rejected"
            action["decided_at"] = time.time()
            _persist()
            print(f"[APPROVAL] rejected id={aid}", flush=True)
            return True
    return False


def _deny(aid: str, message: str) -> dict[str, Any]:
    return {"success": False, "verified": False, "tool": "approve_action", "message": message}


def approve(aid: str, *, decided_by: str = "user") -> dict[str, Any]:
    """Consume an approval exactly once, then run the stored action.

    Consumption is recorded and persisted BEFORE execution. If the process dies
    mid-run the approval is already spent, so the action can never execute twice
    off one grant -- the safe direction to fail.
    """
    with _LOCK:
        _expire_locked()
        action = _pending.get(aid)
        if not action:
            return _deny(aid, f"No pending action '{aid}'.")
        status = action.get("status")
        if status == _EXPIRED:
            return _deny(aid, f"Action {aid} expired before it was approved. Ask again if you still want it.")
        if status != _LIVE:
            return _deny(aid, f"Action {aid} is already {status}.")
        # The record is on disk between submit and approve; re-derive the binding so
        # an edited tool/arguments cannot ride in on an approval granted for something else.
        if action.get("binding_hash") and _binding_hash(action.get("tool"), action.get("slots")) != action["binding_hash"]:
            action["status"] = "cancelled"
            _persist()
            return _deny(aid, f"Action {aid} changed after it was queued, so the approval no longer applies.")
        action["status"] = _CONSUMED
        action["decided_at"] = time.time()
        action["consumed_at"] = time.time()
        action["decided_by"] = str(decided_by or "user")
        _persist()
        tool, slots = action.get("tool"), dict(action.get("slots") or {})

    from engine.tool_registry import execute_tool
    result = execute_tool(tool, {**slots, _APPROVAL_TOKEN_KEY: _INTERNAL_APPROVAL})
    with _LOCK:
        record = _pending.get(aid)
        if record is not None:
            record["status"] = "executed" if result.get("success") else "failed"
            _persist()
    print(f"[APPROVAL] {'executed' if result.get('success') else 'failed'} id={aid} tool={tool}", flush=True)
    return result


def clear() -> None:
    with _LOCK:
        _pending.clear()
        _persist()


def gate(tool: str, slots: dict | None, risk: str, description: str) -> dict[str, Any] | None:
    """Return a requires-approval result if this action must be approved first, else None to proceed."""
    if (slots or {}).get(_APPROVAL_TOKEN_KEY) == _INTERNAL_APPROVAL:
        return None  # already approved via approve() — proceed
    if not requires_approval(risk):
        return None
    aid = submit(tool, slots, risk, description)
    # Phrase as a question (ends with '?') and flag expects_user_reply so the assistant's
    # auto-listen path re-arms the mic for the approve/reject answer instead of going idle.
    # A critical action must be named to approve it, so ask for the id up front --
    # otherwise the prompt invites "approve" and then refuses it.
    if str(risk or "").lower() == "critical":
        question = (f"\"{description}\" is critical — risk {risk}. "
                    f"Say \"approve {aid}\" to confirm, or reject?")
    else:
        question = f"\"{description}\" needs your approval — risk {risk}. Approve or reject?"
    return {"handled": True, "ok": False, "success": False, "verified": False, "tool": tool,
            "requires_approval": True, "approval_id": aid, "risk": risk,
            "expects_user_reply": True, "clarification_question": question,
            "message": question}


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
        # A bare "approve" is a casual yes. It may stand in for an ordinary high-risk
        # action, but a critical one (clicking an arbitrary UI target, spending, deleting)
        # must be named, so a stray "yes" during another conversation cannot fire it.
        if str(items[0].get("risk") or "").lower() == "critical":
            return {"handled": True, "ok": False, "success": False, "verified": False,
                    "tool": "approve_action", "expects_user_reply": True,
                    "message": (f"{items[0]['description']} is critical, so say the action id to approve it: "
                                f"\"approve {items[0]['id']}\".")}
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


_load()
