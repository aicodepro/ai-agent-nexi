from __future__ import annotations

from pathlib import Path
from typing import Any


def _norm_proc(name: str) -> str:
    n = (name or "").strip().lower().replace("\\", "/").split("/")[-1]
    return n[:-4] if n.endswith(".exe") else n


def _app_process_running(app_name: str) -> bool | None:
    """Read-only: True if a process plausibly matching app_name is running.

    Never launches anything. ponytail: name-substring heuristic over psutil — good
    enough to confirm an app opened; upgrade to exact APP_COMMANDS->process map if
    false positives ever bite.
    """
    base = _norm_proc(app_name)
    if not base:
        return False
    tokens = {t for t in base.split() if len(t) >= 3} or {base}
    try:
        import psutil
        for p in psutil.process_iter(["name"]):
            pname = _norm_proc(p.info.get("name") or "")
            if pname and (pname == base or any(tok in pname for tok in tokens)):
                return True
    except Exception:
        return None
    return False


def verify_tool_result(tool_name: str, result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        raw = dict(result)
    else:
        raw = {"success": bool(result), "message": str(result or ""), "verified": False}

    raw_success = bool(raw.get("success") is True or raw.get("ok") is True)
    verified = False
    reason = "not_success"
    if raw_success and tool_name == "open_app":
        # Don't trust the handler's self-reported verified flag — confirm a real process exists.
        app = str(raw.get("app") or raw.get("app_name") or "").strip()
        if app:
            process_running = _app_process_running(app)
            verified = bool(process_running)
            reason = "verification_unavailable" if process_running is None else ("process_running" if verified else "process_not_found")
        else:
            reason = "unverified_success"  # no app name to check against
    elif raw_success and tool_name in {"create_file", "create_folder", "create_project_folder", "save_latest_output", "create_file_from_latest_output"}:
        if raw.get("path"):
            try:
                verified = Path(str(raw.get("path"))).exists()
                reason = "path_exists" if verified else "path_missing"
            except OSError:
                reason = "verification_unavailable"
        else:
            reason = "verification_data_missing"
    elif raw_success and raw.get("verified") is True:
        verified = True
        reason = "explicit_verified"
    elif raw_success:
        reason = "verification_unavailable"
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
