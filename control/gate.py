"""Action gate — permission checking and execution."""

from control.registry import get_registry, ControlAction

RISK_POLICY = {
    "safe": {"allowed": True, "confirm": False},
    "medium": {"allowed": True, "confirm": False},
    "high": {"allowed": True, "confirm": True},
    "critical": {"allowed": False, "confirm": True},
}

_emergency_stop = False


def engage_emergency_stop():
    global _emergency_stop
    _emergency_stop = True


def clear_emergency_stop():
    global _emergency_stop
    _emergency_stop = False


def is_emergency_stopped() -> bool:
    return _emergency_stop


class ActionGate:
    def execute(self, action_name: str, entity: str = "") -> dict:
        if _emergency_stop:
            return {"ok": False, "message": "Emergency stop is active."}

        registry = get_registry()
        action = registry.get(action_name) or registry.match(action_name)
        if not action:
            return {"ok": False, "message": f"Unknown action: {action_name}"}

        policy = RISK_POLICY.get(action.risk, RISK_POLICY["safe"])
        if not policy["allowed"]:
            return {"ok": False, "message": f"Action '{action_name}' is blocked (critical risk)."}

        if policy["confirm"]:
            return {"ok": True, "requires_confirmation": True,
                    "message": f"Action '{action_name}' requires confirmation."}

        try:
            result = action.handler(entity)
            if isinstance(result, dict):
                return result
            return {"ok": True, "message": str(result) if result else "Done."}
        except Exception as e:
            return {"ok": False, "message": f"Action failed: {e}"}


_gate = ActionGate()


def dispatch_action(action_name: str, entity: str = "") -> dict:
    return _gate.execute(action_name, entity)
