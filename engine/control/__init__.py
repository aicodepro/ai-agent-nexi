from engine.control.base import ControlResult, ControlFunction
from engine.control.registry import ControlRegistry
from engine.control.safety import EmergencyStop, SandboxPolicy, AuditLog
from engine.control.permission_manager import PermissionManager
from engine.control.action_gate import ActionGate, ActionGateResult, ActionGateStatus

registry = ControlRegistry()

from engine.control.desktop_controller import register_desktop_controls
from engine.control.window_controller import register_window_controls
from engine.control.file_controller import register_file_controls
from engine.control.chrome_controller import register_chrome_controls

# Registration must not be able to break `import engine.control`. A desktop
# driver that needs a display (pyautogui/win32) fails on a headless CI box, and
# an unguarded call here took the whole package down with it - so pure policy
# code like ActionGate became unimportable. Degrade per-controller instead.
for _name, _register in (
    ("desktop", register_desktop_controls),
    ("window", register_window_controls),
    ("file", register_file_controls),
    ("chrome", register_chrome_controls),
):
    try:
        _register(registry)
    except Exception as _exc:  # pragma: no cover - environment dependent
        print(f"[CONTROL] {_name} controls unavailable: {type(_exc).__name__}", flush=True)

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
