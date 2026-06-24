import uuid
from datetime import datetime

_FAILURE_CLASSIFIERS = {
    "transient": [
        "timeout", "timed out", "connection", "network", "unavailable",
        "temporary", "retry", "rate limit",
    ],
    "permission": [
        "denied", "forbidden", "not allowed", "unauthorized", "blocked",
        "requires confirmation", "sandbox",
    ],
    "invalid_input": [
        "invalid", "not found", "missing", "unknown", "unrecognized",
        "malformed", "bad request", "not supported",
    ],
}


def classify_failure(reason):
    if not reason:
        return "unknown"
    r = reason.lower()
    for category, keywords in _FAILURE_CLASSIFIERS.items():
        for kw in keywords:
            if kw in r:
                return category
    return "unknown"


def _retry_recovery_step(failed_action):
    return {
        "step_id": str(uuid.uuid4()),
        "description": f"Retry: {failed_action}",
        "action": failed_action,
        "type": "retry",
        "created_at": datetime.now().isoformat(),
    }


def _alternative_recovery_step(failed_action, failure_type):
    alternatives = {
        "open_chrome": "open_browser",
        "search_youtube": "search_google",
        "open_application": "list_applications",
    }
    alt = alternatives.get(failed_action, "")
    if alt:
        return {
            "step_id": str(uuid.uuid4()),
            "description": f"Try alternative: {alt}",
            "action": alt,
            "type": "alternative",
            "created_at": datetime.now().isoformat(),
        }
    return None


def _input_correction_step(missing_fields):
    return {
        "step_id": str(uuid.uuid4()),
        "description": f"Provide missing input: {', '.join(missing_fields)}",
        "action": "request_input",
        "type": "input_correction",
        "fields": missing_fields,
        "created_at": datetime.now().isoformat(),
    }


def create_recovery_plan(failed_step=None, reason=""):
    if not failed_step:
        return {"strategy": "noop", "steps": [], "message": "No failed step to recover from."}
    failure_type = classify_failure(reason)
    recovery_steps = []
    if failure_type == "transient":
        retry = _retry_recovery_step(failed_step.get("action", ""))
        if retry:
            recovery_steps.append(retry)
    elif failure_type == "permission":
        recovery_steps.append({
            "step_id": str(uuid.uuid4()),
            "description": "Request user permission to proceed",
            "action": "request_permission",
            "type": "permission_request",
            "created_at": datetime.now().isoformat(),
        })
    elif failure_type == "invalid_input":
        missing = failed_step.get("result", {}).get("missing_fields", [])
        if missing:
            recovery_steps.append(_input_correction_step(missing))
        else:
            recovery_steps.append({
                "step_id": str(uuid.uuid4()),
                "description": "Correct input and retry",
                "action": "correct_input",
                "type": "input_correction",
                "created_at": datetime.now().isoformat(),
            })
    else:
        alt = _alternative_recovery_step(failed_step.get("action", ""), failure_type)
        if alt:
            recovery_steps.append(alt)
        recovery_steps.append({
            "step_id": str(uuid.uuid4()),
            "description": "Ask user how to proceed",
            "action": "ask_user",
            "type": "user_guidance",
            "created_at": datetime.now().isoformat(),
        })
    return {
        "strategy": failure_type,
        "steps": recovery_steps,
        "message": f"Recovery strategy: {failure_type} — {len(recovery_steps)} step(s)",
    }


def suggest_next_action(reason):
    failure_type = classify_failure(reason)
    suggestions = {
        "transient": "Retry the action after a short delay.",
        "permission": "Request user permission before retrying.",
        "invalid_input": "Correct the input parameters and retry.",
        "unknown": "Ask the user how to proceed.",
    }
    return suggestions.get(failure_type, "Ask the user for guidance.")
