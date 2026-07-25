"""Explicit command grammar for Nexi Studio."""

from __future__ import annotations

import re
import secrets
import hashlib
import getpass
import threading
import time


_INVOCATION_PREFIX_RE = re.compile(r"^(?:Nexi,|Hey Nexi,)\s*", re.I)
_IN_DIR_RE = re.compile(r'^\s*(studio|exotic)\s+mode\s+in\s+"([^"]+)"\s*:\s*(.*)$', re.I | re.S)
_BUILD_RE = re.compile(r"^\s*(?:let's|lets)\s+build\b(?:\s+me\b)?(?:\s*:?[\s]*(.*))?$", re.I | re.S)
_START_BUILDING_RE = re.compile(r"^\s*start\s+building\b(?:\s*:?[\s]*(.*))?$", re.I | re.S)
_MODE_RE = re.compile(r"^\s*(studio|exotic)\s+mode\s*(?::\s*(.*))?$", re.I | re.S)
_STUDIO_STATUS_COMMANDS = {"studio status", "studio build status", "show studio status"}
_STUDIO_CANCEL_COMMANDS = {"cancel studio", "cancel studio build", "stop studio build"}
_STUDIO_CONTINUE_RE = re.compile(r"^(?:studio continue|continue studio|resume studio build)\b(?:\s*:?\s*(.*))?$", re.I | re.S)
_VAGUE_BUILD_GOALS = {
    "a thing",
    "anything",
    "some thing",
    "something",
    "something cool",
    "something new",
    "something useful",
    "stuff",
}
_AUTHORIZATIONS: dict[str, dict[str, object]] = {}
_AUTH_LOCK = threading.Lock()


def studio_command_body(text: str) -> str:
    """Remove only the supported direct-address prefixes."""
    raw = str(text or "").strip()
    return _INVOCATION_PREFIX_RE.sub("", raw, count=1).strip()


def _studio_goal(value: str | None) -> str:
    goal = str(value or "").strip()
    normalized = " ".join(goal.lower().rstrip(".?!").split())
    return "" if normalized in _VAGUE_BUILD_GOALS else goal


def parse_studio_command(text: str) -> dict[str, str] | None:
    """Parse only phrases that explicitly authorize a Studio build."""
    raw = str(text or "").strip()
    directly_addressed = _INVOCATION_PREFIX_RE.match(raw) is not None
    body = studio_command_body(raw)
    match = _IN_DIR_RE.match(body)
    if match:
        return {
            "trigger": match.group(1).lower(),
            "project_dir": match.group(2).strip(),
            "goal": _studio_goal(match.group(3)),
            "raw_text": raw,
        }
    match = _BUILD_RE.match(body)
    if match:
        return {"trigger": "lets_build", "project_dir": "", "goal": _studio_goal(match.group(1)), "raw_text": raw}
    match = _START_BUILDING_RE.match(body)
    if match and directly_addressed:
        return {"trigger": "start_building", "project_dir": "", "goal": _studio_goal(match.group(1)), "raw_text": raw}
    match = _MODE_RE.match(body)
    if match:
        return {
            "trigger": match.group(1).lower(),
            "project_dir": "",
            "goal": _studio_goal(match.group(2)),
            "raw_text": raw,
        }
    return None


def explicit_studio_action(text: str) -> str | None:
    """Classify an explicit Studio command without minting authorization."""
    body = studio_command_body(text)
    normalized = " ".join(body.lower().rstrip(".?!").split())
    if normalized in _STUDIO_STATUS_COMMANDS:
        return "status"
    if normalized in _STUDIO_CANCEL_COMMANDS:
        return "cancel"
    if _STUDIO_CONTINUE_RE.match(body):
        return "continue"
    if parse_studio_command(text):
        return "start"
    return None


def is_explicit_studio_command(text: str) -> bool:
    return explicit_studio_action(text) is not None


def current_os_principal() -> str:
    """Return the current local OS account identifier (not speaker identity)."""
    try:
        return str(getpass.getuser() or "unknown").strip() or "unknown"
    except Exception:
        return "unknown"


def _command_source(source: str | None) -> str:
    return str(source or "unknown").strip().lower() or "unknown"


def issue_authorization(raw_text: str, action: str, *, source: str | None = None) -> str:
    """Mint a short-lived, one-use capability from a trusted exact matcher."""
    token = secrets.token_urlsafe(24)
    with _AUTH_LOCK:
        monotonic_now = time.monotonic()
        issued_at = time.time()
        expired = [
            key for key, value in _AUTHORIZATIONS.items()
            if float(value.get("expires_at_monotonic") or 0.0) < monotonic_now
        ]
        for key in expired:
            _AUTHORIZATIONS.pop(key, None)
        command = str(raw_text or "").strip()
        principal = current_os_principal()
        command_source = _command_source(source)
        _AUTHORIZATIONS[token] = {
            "authorization_id": f"auth_{secrets.token_hex(12)}",
            "action": str(action),
            "command": command,
            "command_sha256": hashlib.sha256(command.encode("utf-8")).hexdigest(),
            "principal": principal,
            "source": command_source,
            "identity_assurance": "local_os_principal_only_not_speaker_verification",
            "issued_at": issued_at,
            "expires_at_monotonic": monotonic_now + 60.0,
        }
    return token


def consume_authorization_audit(
    token: str,
    raw_text: str,
    action: str,
    *,
    source: str | None = None,
) -> dict[str, object] | None:
    """Consume a capability and return non-secret audit data; never return the token."""
    with _AUTH_LOCK:
        record = _AUTHORIZATIONS.pop(str(token or ""), None)
    if not record:
        return None
    expected_action = str(record.get("action") or "")
    expected_text = str(record.get("command") or "")
    expected_principal = str(record.get("principal") or "")
    expected_source = str(record.get("source") or "")
    expires_at = float(record.get("expires_at_monotonic") or 0.0)
    if (
        expires_at < time.monotonic()
        or expected_action != str(action)
        or expected_text != str(raw_text or "").strip()
        or expected_principal != current_os_principal()
        or expected_source != _command_source(source)
    ):
        return None
    return {
        "authorization_id": str(record["authorization_id"]),
        "action": expected_action,
        "command_sha256": str(record["command_sha256"]),
        "principal": expected_principal,
        "source": expected_source,
        "identity_assurance": str(record["identity_assurance"]),
        "issued_at": float(record["issued_at"]),
        "consumed_at": time.time(),
    }


def consume_authorization(token: str, raw_text: str, action: str, *, source: str | None = None) -> bool:
    """Backward-compatible boolean capability consumption."""
    return consume_authorization_audit(token, raw_text, action, source=source) is not None
