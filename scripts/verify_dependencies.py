"""Verify all required dependencies for the control layer are available."""
import sys
import os

REQUIRED = {
    "playwright": "playwright.sync_api",
    "psutil": "psutil",
    "pywin32": "win32gui",
    "pygetwindow": "pygetwindow",
    "pyautogui": "pyautogui",
    "eel": "eel",
}

OPTIONAL = {
}

PASS = 0
FAIL = 0

def main():
    global PASS, FAIL
    print("=" * 60)
    print("DEPENDENCY VERIFICATION")
    print("=" * 60)

    print("\n[Required Dependencies]")
    for name, import_path in REQUIRED.items():
        try:
            exec(f"import {import_path.split('.')[0]}")
            print(f"  PASS: {name} ({import_path})")
            PASS += 1
        except ImportError as e:
            print(f"  FAIL: {name} ({import_path}) - {e}")
            FAIL += 1

    print("\n[Control Layer Imports]")
    try:
        sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
        from src.orin.control import (  # noqa: F401
            execute_control_action, match_control_action, list_control_actions,
            EmergencyStop, ControlResult, registry
        )
        print("  PASS: src.orin.control package imported successfully")
        PASS += 1
    except ImportError as e:
        print(f"  FAIL: src.orin.control import failed - {e}")
        FAIL += 1

    print("\n[Framework Compatibility]")
    test_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "www", "controller.js"))
    if os.path.exists(test_path):
        print(f"  PASS: controller.js exists at {test_path}")
        PASS += 1
    else:
        print(f"  FAIL: controller.js not found at {test_path}")
        FAIL += 1

    print(f"\n{'=' * 60}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
