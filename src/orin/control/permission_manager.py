import threading
from datetime import datetime

from src.orin.control.safety import EmergencyStop, SandboxPolicy, AuditLog


_KNOWN_ACTIONS = {
    "run_diagnostics": {"risk_level": "SAFE", "description": "Run Jarvis diagnostics"},
    "check_project_status": {"risk_level": "SAFE", "description": "Check project status"},
    "retrieve_preferences": {"risk_level": "SAFE", "description": "Retrieve stored preferences"},
    "remember_preference": {"risk_level": "MEDIUM", "description": "Remember a preference"},
    "forget_preference": {"risk_level": "MEDIUM", "description": "Forget a preference"},
    "open_application": {"risk_level": "MEDIUM", "description": "Open an application"},
    "web_search": {"risk_level": "MEDIUM", "description": "Search the web"},
    "request_input": {"risk_level": "SAFE", "description": "Request user input"},
    "request_permission": {"risk_level": "SAFE", "description": "Request user permission"},
    "emergency_stop": {"risk_level": "SAFE", "description": "Engage emergency stop"},
    "screen_capture": {"risk_level": "HIGH", "description": "Capture screen"},
    "draft_email": {"risk_level": "HIGH", "description": "Draft an email"},
    "draft_whatsapp": {"risk_level": "HIGH", "description": "Draft a WhatsApp message"},
    "send_message": {"risk_level": "HIGH", "description": "Send a message"},
    "send_message_auto": {"risk_level": "CRITICAL", "description": "Send message automatically"},
    "delete_files": {"risk_level": "CRITICAL", "description": "Delete files"},
    "unknown": {"risk_level": "MEDIUM", "description": "Unknown action"},
}

_HIGH_CONFIRMATION_PROMPTS = {
    "screen_capture": "Jarvis wants to capture your screen. Allow?",
    "draft_email": "Jarvis wants to draft an email. Allow?",
    "draft_whatsapp": "Jarvis wants to draft a WhatsApp message. Allow?",
    "send_message": "Jarvis wants to send a message. Allow?",
}

_CRITICAL_CONFIRMATION_PROMPTS = {
    "delete_files": "Jarvis wants to delete files. Type CONFIRM to allow (not recommended).",
    "send_message_auto": "Jarvis wants to send a message automatically. Type CONFIRM to allow.",
}


class PermissionManager:
    def __init__(self):
        self._lock = threading.Lock()
        self._pending_decisions = {}

    def evaluate(self, action_name, risk_level=None, context=None):
        if EmergencyStop.is_engaged():
            return self._decision(
                action_name, "blocked",
                requires_confirmation=False,
                block_reason="Emergency stop is engaged. All actions blocked.",
            )
        if risk_level is None:
            risk_level = _KNOWN_ACTIONS.get(action_name, {}).get("risk_level", "MEDIUM")
        allowed, reason = SandboxPolicy.is_allowed(risk_level, action_name)
        if not allowed:
            return self._decision(
                action_name, "blocked",
                requires_confirmation=False,
                block_reason=reason,
            )
        if risk_level == "CRITICAL":
            return self._decision(
                action_name, "blocked",
                requires_confirmation=True,
                confirmation_prompt=self._prompt_for(action_name, risk_level),
                block_reason="CRITICAL risk actions are blocked by policy",
            )
        if risk_level == "HIGH":
            from src.orin.vision.screen_trust import ScreenTrust
            if ScreenTrust.is_owner_trusted():
                AuditLog.log(action_name, {"owner_trusted_auto_approved": True, "context": context or {}})
                return self._decision(
                    action_name, "approved",
                    requires_confirmation=False,
                    confirmation_prompt="Using trusted owner access.",
                    owner_trusted=True,
                )
            prompt = self._prompt_for(action_name, risk_level)
            decision_id = self._create_pending(action_name, prompt)
            AuditLog.log(action_name, {"decision_id": decision_id, "context": context or {}})
            return self._decision(
                action_name, "pending",
                requires_confirmation=True,
                confirmation_prompt=prompt,
                decision_id=decision_id,
            )
        AuditLog.log(action_name, {"context": context or {}})
        return self._decision(
            action_name, "approved",
            requires_confirmation=False,
        )

    def require_confirmation(self, action_name):
        risk_level = _KNOWN_ACTIONS.get(action_name, {}).get("risk_level", "MEDIUM")
        return self._prompt_for(action_name, risk_level)

    def confirm(self, action_name, user_response):
        if EmergencyStop.is_engaged():
            return self._decision(
                action_name, "blocked",
                requires_confirmation=False,
                block_reason="Emergency stop is engaged.",
            )
        risk_level = _KNOWN_ACTIONS.get(action_name, {}).get("risk_level", "MEDIUM")
        allowed, reason = SandboxPolicy.is_allowed(risk_level, action_name)
        if not allowed:
            return self._decision(
                action_name, "blocked",
                requires_confirmation=False,
                block_reason=reason,
            )
        if risk_level == "CRITICAL":
            # CRITICAL actions remain blocked even if user types confirmation.
            # This is a safety invariant: CRITICAL = policy-blocked, not user-choice.
            return self._decision(
                action_name, "blocked",
                requires_confirmation=True,
                user_confirmed=True,
                block_reason="CRITICAL risk actions are blocked by policy regardless of confirmation",
            )
        if risk_level == "HIGH":
            if self._is_affirmative(user_response):
                AuditLog.log(action_name, {"confirmed": True})
                return self._decision(
                    action_name, "approved",
                    requires_confirmation=False,
                    user_confirmed=True,
                    confirmed_at=datetime.now().isoformat(),
                )
            AuditLog.log(action_name, {"confirmed": False})
            return self._decision(
                action_name, "denied",
                requires_confirmation=True,
                user_confirmed=False,
                block_reason="User denied the action",
            )
        AuditLog.log(action_name, {"auto_approved": True})
        return self._decision(
            action_name, "approved",
            requires_confirmation=False,
            user_confirmed=True,
        )

    def _decision(self, action_name, decision, requires_confirmation=False,
                  confirmation_prompt="", block_reason="", decision_id="",
                  user_confirmed=False, confirmed_at=None, owner_trusted=False):
        return {
            "action_name": action_name,
            "risk_level": _KNOWN_ACTIONS.get(action_name, {}).get("risk_level", "MEDIUM"),
            "decision": decision,
            "requires_confirmation": requires_confirmation,
            "confirmation_prompt": confirmation_prompt,
            "block_reason": block_reason,
            "user_confirmed": user_confirmed,
            "decision_id": decision_id,
            "decision_timestamp": datetime.now().isoformat(),
            "confirmed_at": confirmed_at,
            "owner_trusted": owner_trusted,
        }

    def _prompt_for(self, action_name, risk_level):
        if risk_level == "HIGH":
            return _HIGH_CONFIRMATION_PROMPTS.get(
                action_name,
                f"This is a HIGH risk action ({action_name}). Proceed?"
            )
        if risk_level == "CRITICAL":
            return _CRITICAL_CONFIRMATION_PROMPTS.get(
                action_name,
                f"This is a CRITICAL risk action ({action_name}) and is blocked by policy."
            )
        return ""

    def _create_pending(self, action_name, prompt):
        with self._lock:
            decision_id = f"dec_{len(self._pending_decisions)}_{action_name}"
            self._pending_decisions[decision_id] = {
                "action_name": action_name,
                "prompt": prompt,
                "created_at": datetime.now().isoformat(),
            }
            return decision_id

    def _is_affirmative(self, response):
        if not response or not isinstance(response, str):
            return False
        r = response.strip().lower()
        return r in ("yes", "y", "approve", "allow", "confirm", "ok", "proceed", "1")
