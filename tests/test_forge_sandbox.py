"""Forge sandbox runner (engine/forge/sandbox_runner.py). Runs real pytest subprocesses."""
from engine.forge import sandbox_runner


def test_passing_test_passes():
    fc = "def add(a, b):\n    return a + b\n"
    tc = "from forged_tool import add\n\ndef test_add():\n    assert add(2, 3) == 5\n"
    r = sandbox_runner.run_test(fc, tc, timeout=60)
    assert r["passed"] is True


def test_failing_test_fails():
    fc = "def add(a, b):\n    return a + b\n"
    tc = "from forged_tool import add\n\ndef test_add():\n    assert add(2, 3) == 6\n"
    r = sandbox_runner.run_test(fc, tc, timeout=60)
    assert r["passed"] is False
