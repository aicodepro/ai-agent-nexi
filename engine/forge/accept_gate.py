"""Decide what happens after a forged tool passes its test.

SAFE (pure compute/read) -> auto-register. RISKY (touches fs/network/subprocess/
exec) -> require user approval before it can be installed/called.
"""


def decide(scan_result: dict) -> str:
    """Return "auto" or "approve" based on the safety scan."""
    return "auto" if scan_result.get("safe") else "approve"
