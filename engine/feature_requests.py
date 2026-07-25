"""Feature-gap system (Roadmap orchestrator) — log capabilities Nexi doesn't have yet.

Tool cards
----------
request_feature       role: feature gap | risk: LOW | confirm: never | verifier: request stored | memory: never store
list_feature_requests role: feature gap | risk: LOW | confirm: never | verifier: store read     | memory: never store

When the user asks for a capability that doesn't exist, Nexi should NOT say "I can't" — it
logs a FeatureRequest (status="proposed") and tells the user it needs approval before being
built. This is PROPOSE-ONLY: runtime Nexi never writes or executes new feature code. Actual
implementation is a separate, human-approved, dev-mode step (intentionally not automated here).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_STORE = Path(__file__).resolve().parents[1] / "data" / "feature_requests.json"


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "feature_requests"), "message": message, **extra}


def _fail(message: str, tool: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": False, "success": False, "verified": False,
            "tool": tool, "message": message, **extra}


def _load() -> list[dict[str, Any]]:
    try:
        data = json.loads(Path(_STORE).read_text(encoding="utf-8"))
        return [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
    except Exception:
        return []


def _save(items: list[dict[str, Any]]) -> None:
    try:
        path = Path(_STORE)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(items, indent=2), encoding="utf-8")
    except Exception:
        pass


def create_request(capability: str, user_input: str = "", reason: str = "") -> dict[str, Any]:
    items = _load()
    rec = {
        "id": f"fr{len(items) + 1}",
        "capability": capability.strip(),
        "user_input": (user_input or capability).strip(),
        "reason": reason.strip(),
        "status": "proposed",  # proposed -> approved -> built -> enabled (all human-gated)
        "created": time.time(),
    }
    items.append(rec)
    _save(items)
    print(f"[FEATURE_GAP] logged id={rec['id']} capability={rec['capability'][:60]}", flush=True)
    return rec


def list_requests(status: str | None = None) -> list[dict[str, Any]]:
    items = _load()
    return [r for r in items if status is None or r.get("status") == status]


def set_status(request_id: str, status: str) -> bool:
    items = _load()
    for r in items:
        if r.get("id") == request_id:
            r["status"] = status
            _save(items)
            return True
    return False


# ── Voice tools ──────────────────────────────────────────────────────────────
def request_feature(slots: dict | None = None) -> dict[str, Any]:
    capability = str((slots or {}).get("capability") or (slots or {}).get("text") or "").strip()
    if not capability:
        return _fail("What capability would you like me to add?", "request_feature",
                     expects_user_reply=True, missing_slot="capability")
    rec = create_request(capability, user_input=str((slots or {}).get("user_input") or capability))
    msg = (f"I don't have that yet, so I've logged feature request {rec['id']}: \"{capability}\". "
           f"It needs your approval before I build it.")
    return _ok(msg, tool="request_feature", request_id=rec["id"], capability=capability, status="proposed")


def list_feature_requests(slots: dict | None = None) -> dict[str, Any]:
    items = list_requests()
    if not items:
        return _ok("There are no feature requests yet.", tool="list_feature_requests", count=0, requests=[])
    preview = "; ".join(f"{r['id']}: {r['capability']} ({r['status']})" for r in items[:5])
    return _ok(f"{len(items)} feature request(s): {preview}.", tool="list_feature_requests",
               count=len(items), requests=items)
