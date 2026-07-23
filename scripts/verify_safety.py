"""Verify safety rules are working correctly."""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine.control.safety import EmergencyStop, SandboxPolicy
from engine.control import execute_control_action

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        print(f"  PASS: {name}")
        PASS += 1
    else:
        print(f"  FAIL: {name} - {detail}")
        FAIL += 1

def main():
    global PASS, FAIL
    print("=" * 60)
    print("SAFETY VERIFICATION")
    print("=" * 60)

    print("\n[1] Emergency Stop")
    EmergencyStop.clear()
    check("Emergency stop is not engaged by default", not EmergencyStop.is_engaged())

    EmergencyStop.engage(reason="Test")
    check("Emergency stop can be engaged", EmergencyStop.is_engaged())
    check("Emergency stop stores reason", EmergencyStop.reason() == "Test")

    result = execute_control_action("list_apps")
    check("Emergency stop blocks safe actions",
          not result.ok and result.error["code"] == "EMERGENCY_STOP")

    EmergencyStop.clear()
    check("Emergency stop can be cleared", not EmergencyStop.is_engaged())

    print("\n[2] Sandbox Policy")
    allowed, _ = SandboxPolicy.is_allowed("SAFE", "list_apps")
    check("SAFE actions are allowed", allowed)

    allowed, _ = SandboxPolicy.is_allowed("MEDIUM", "open_app")
    check("MEDIUM actions are allowed", allowed)

    allowed, _ = SandboxPolicy.is_allowed("HIGH", "close_app")
    check("HIGH actions are allowed", allowed)

    allowed, _ = SandboxPolicy.is_allowed("CRITICAL", "delete_files")
    check("CRITICAL actions are blocked", not allowed)

    for action in SandboxPolicy.BLOCKED_ACTIONS:
        allowed, _ = SandboxPolicy.is_allowed("HIGH", action)
        check(f"BLOCKED action '{action}' is blocked", not allowed)

    print("\n[3] Control Action Execution")
    result = execute_control_action("get_active_window")
    check("SAFE action 'get_active_window' returns ok", result.ok)

    result = execute_control_action("list_apps")
    check("SAFE action 'list_apps' returns ok", result.ok)

    result = execute_control_action("xyznonexistent12345")
    check("Unknown action returns failure", not result.ok)

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")

    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
