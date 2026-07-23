from __future__ import annotations

import threading
from datetime import datetime
from enum import Enum
from typing import Optional

from engine.control.base import ControlResult
from engine.control.permission_manager import PermissionManager
from engine.control.registry import ControlRegistry
from engine.control.safety import EmergencyStop, AuditLog


class ActionGateStatus(Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    NEED_CONFIRMATION = "NEED_CONFIRMATION"
    UNKNOWN_ACTION = "UNKNOWN_ACTION"
    EMERGENCY_STOP_BLOCKED = "EMERGENCY_STOP_BLOCKED"


class ActionGateResult:
    def __init__(
        self,
        status: ActionGateStatus,
        action_name: str = "",
        message: str = "",
        reason: str = "",
        permission_result: Optional[dict] = None,
        control_result: Optional[ControlResult] = None,
        handler_called: bool = False,
    ):
        self.status = status
        self.action_name = action_name
        self.message = message
        self.reason = reason
        self.permission_result = permission_result or {}
        self.control_result = control_result
        self.handler_called = handler_called
        self.timestamp = datetime.now().isoformat()

    def to_dict(self):
        return {
            "status": self.status.value,
            "action_name": self.action_name,
            "message": self.message,
            "reason": self.reason,
            "permission_result": self.permission_result,
            "control_result": self.control_result.to_dict() if self.control_result else None,
            "handler_called": self.handler_called,
            "timestamp": self.timestamp,
        }

    @classmethod
    def allow(cls, action_name: str, control_result: ControlResult, perm_result: Optional[dict] = None):
        return cls(
            status=ActionGateStatus.ALLOW,
            action_name=action_name,
            message=control_result.message or "Action executed successfully",
            permission_result=perm_result or {},
            control_result=control_result,
            handler_called=True,
        )

    @classmethod
    def block(cls, action_name: str, reason: str = "", perm_result: Optional[dict] = None):
        return cls(
            status=ActionGateStatus.BLOCK,
            action_name=action_name,
            message=f"Action blocked: {reason}" if reason else "Action blocked",
            reason=reason,
            permission_result=perm_result or {},
            handler_called=False,
        )

    @classmethod
    def need_confirmation(cls, action_name: str, prompt: str = "", perm_result: Optional[dict] = None):
        return cls(
            status=ActionGateStatus.NEED_CONFIRMATION,
            action_name=action_name,
            message=prompt or "Confirmation required",
            reason="Action requires user confirmation",
            permission_result=perm_result or {},
            handler_called=False,
        )

    @classmethod
    def unknown_action(cls, action_name: str):
        return cls(
            status=ActionGateStatus.UNKNOWN_ACTION,
            action_name=action_name,
            message=f"Unknown action: {action_name}",
            reason="No matching action found in registry",
            handler_called=False,
        )

    @classmethod
    def emergency_stop(cls, action_name: str = ""):
        return cls(
            status=ActionGateStatus.EMERGENCY_STOP_BLOCKED,
            action_name=action_name,
            message="All actions blocked: emergency stop is engaged.",
            reason=EmergencyStop.reason(),
            handler_called=False,
        )


class ActionGate:
    def __init__(
        self,
        registry: ControlRegistry,
        permission_manager: Optional[PermissionManager] = None,
    ):
        self._registry = registry
        self._permission_manager = permission_manager or PermissionManager()
        self._lock = threading.Lock()

    def dispatch(
        self,
        action_name: str,
        entities: Optional[dict] = None,
        context: Optional[dict] = None,
    ) -> ActionGateResult:
        entities = entities or {}
        context = context or {}

        if EmergencyStop.is_engaged():
            AuditLog.log(
                action_name,
                {**entities, "context": context, "gate_status": "EMERGENCY_STOP_BLOCKED"},
            )
            return ActionGateResult.emergency_stop(action_name)

        func = self._resolve_action(action_name)
        if func is None:
            AuditLog.log(
                action_name,
                {**entities, "context": context, "gate_status": "UNKNOWN_ACTION"},
            )
            return ActionGateResult.unknown_action(action_name)

        perm_result = self._permission_manager.evaluate(func.name, func.risk_level, context)
        decision = perm_result["decision"]

        if decision == "pending":
            AuditLog.log(
                func.name,
                {**entities, "context": context, "gate_status": "NEED_CONFIRMATION"},
            )
            return ActionGateResult.need_confirmation(
                action_name=func.name,
                prompt=perm_result.get("confirmation_prompt", "Confirmation required"),
                perm_result=perm_result,
            )

        if decision == "blocked":
            block_reason = perm_result.get("block_reason", "Action blocked by policy")
            AuditLog.log(
                func.name,
                {**entities, "context": context, "gate_status": "BLOCK", "reason": block_reason},
            )
            return ActionGateResult.block(
                action_name=func.name,
                reason=block_reason,
                perm_result=perm_result,
            )

        AuditLog.log(
            func.name,
            {**entities, "context": context, "gate_status": "ALLOW"},
        )
        control_result = func(**entities)
        return ActionGateResult.allow(func.name, control_result, perm_result)

    def confirm(
        self,
        action_name: str,
        user_response: str,
        entities: Optional[dict] = None,
    ) -> ActionGateResult:
        entities = entities or {}

        if EmergencyStop.is_engaged():
            return ActionGateResult.emergency_stop(action_name)

        func = self._resolve_action(action_name)
        if func is None:
            return ActionGateResult.unknown_action(action_name)

        if func.risk_level == "CRITICAL":
            return ActionGateResult.block(
                action_name=func.name,
                reason="CRITICAL risk actions are blocked by policy regardless of confirmation",
            )

        if func.risk_level == "HIGH":
            if self._is_affirmative(user_response):
                control_result = func(**entities)
                return ActionGateResult.allow(func.name, control_result)
            return ActionGateResult.block(
                action_name=func.name,
                reason="User denied the action",
            )

        perm_result = self._permission_manager.confirm(func.name, user_response)
        control_result = func(**entities)
        return ActionGateResult.allow(func.name, control_result, perm_result)

    def _resolve_action(self, action_name: str):
        func = self._registry.get(action_name)
        if func is None:
            func = self._registry.match_by_text(action_name)
        return func

    @staticmethod
    def _is_affirmative(response):
        if not response or not isinstance(response, str):
            return False
        r = response.strip().lower()
        return r in ("yes", "y", "approve", "allow", "confirm", "ok", "proceed", "1")
