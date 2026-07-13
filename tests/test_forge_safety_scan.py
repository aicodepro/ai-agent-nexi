"""Forge static safety scan (engine/forge/safety_scan.py)."""
from engine.forge import safety_scan


def test_pure_compute_is_safe():
    r = safety_scan.scan("import math\ndef f(x):\n    return math.sqrt(x)\n")
    assert r["safe"] is True
    assert r["flags"] == []


def test_import_os_is_risky():
    r = safety_scan.scan("import os\ndef f():\n    return os.getcwd()\n")
    assert r["safe"] is False
    assert any("os" in flag for flag in r["flags"])


def test_open_call_is_risky():
    r = safety_scan.scan("def f(p):\n    return open(p).read()\n")
    assert r["safe"] is False
    assert "call:open" in r["flags"]


def test_subprocess_import_is_risky():
    r = safety_scan.scan("import subprocess\ndef f():\n    subprocess.run(['ls'])\n")
    assert r["safe"] is False


def test_eval_call_is_risky():
    r = safety_scan.scan("def f(s):\n    return eval(s)\n")
    assert r["safe"] is False
    assert "call:eval" in r["flags"]


def test_syntax_error_not_safe():
    r = safety_scan.scan("def f(:\n  pass")
    assert r["safe"] is False
    assert "syntax_error" in r["flags"]
