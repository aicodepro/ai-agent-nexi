from src.orin.control.base import ControlResult, ControlFunction
from src.orin.control.registry import ControlRegistry
from src.orin.control.safety import EmergencyStop, SandboxPolicy, AuditLog
from src.orin.control.permission_manager import PermissionManager
from src.orin.control.action_gate import ActionGate, ActionGateResult, ActionGateStatus

registry = ControlRegistry()

from src.orin.control.desktop_controller import register_desktop_controls
from src.orin.control.window_controller import register_window_controls
from src.orin.control.file_controller import register_file_controls
from src.orin.control.chrome_controller import register_chrome_controls

register_desktop_controls(registry)
register_window_controls(registry)
register_file_controls(registry)
register_chrome_controls(registry)

gate = ActionGate(registry)

def dispatch_through_gate(action_name, entities=None, context=None):
    return gate.dispatch(action_name, entities or {}, context or {})

def execute_control_action(action_name, entities=None):
    result = gate.dispatch(action_name, entities or {})
    if result.status == ActionGateStatus.ALLOW:
        return result.control_result
    if result.status == ActionGateStatus.NEED_CONFIRMATION:
        return ControlResult.failure(
            message=result.message,
            code="NEED_CONFIRMATION",
            error_message=result.reason,
        )
    if result.status == ActionGateStatus.EMERGENCY_STOP_BLOCKED:
        return ControlResult.failure(
            message=result.message,
            code="EMERGENCY_STOP",
            error_message=result.reason,
        )
    if result.status == ActionGateStatus.UNKNOWN_ACTION:
        return ControlResult.failure(
            message=result.message,
            code="UNKNOWN_ACTION",
        )
    return ControlResult.failure(
        message=result.message,
        code="ACTION_BLOCKED",
        error_message=result.reason,
    )

def match_control_action(natural_language_text):
    return registry.match_by_text(natural_language_text)

def list_control_actions():
    return [{"name": f.name, "description": f.description, "risk_level": f.risk_level}
            for f in registry.list_functions()]
