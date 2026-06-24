from __future__ import annotations

from pathlib import Path
from typing import Any


def verify_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        raw = dict(result)
    else:
        raw = {"success": bool(result), "message": str(result or ""), "verified": False}

    raw_success = bool(raw.get("success") is True or raw.get("ok") is True)
    verified = False
    reason = "not_success"
    if raw_success and tool_name in {"create_file", "create_folder", "save_latest_output", "create_file_from_latest_output"} and raw.get("path"):
        verified = Path(str(raw.get("path"))).exists()
        reason = "path_exists" if verified else "path_missing"
    elif raw_success and raw.get("verified") is True:
        verified = True
        reason = "explicit_verified"
    elif raw_success:
        reason = "unverified_success"
    else:
        reason = str(raw.get("reason") or raw.get("error") or "not_success")[:80]

    message = str(raw.get("message") or ("Done." if raw_success else "I couldn't verify that action."))
    if not verified:
        try:
            from engine.assistant_response import guard_unverified_action_message

            message = guard_unverified_action_message(message, {"success": raw_success, "verified": verified})
        except Exception:
            if raw_success:
                message = "I couldn't verify that action, so I won't claim it completed."

    print(f"[VERIFY] tool={tool_name} verified={str(verified).lower()} reason={reason}", flush=True)
    normalized = dict(raw)
    normalized.update({
        "handled": True,
        "ok": verified,
        "success": verified,
        "raw_success": raw_success,
        "verified": verified,
        "verification_reason": reason,
        "tool": tool_name,
        "message": message,
    })
    return normalized
