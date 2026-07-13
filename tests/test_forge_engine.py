"""Forge loop end-to-end (engine/forge/forge_engine.py) with a fake generator."""
import json

from engine.forge import forge_engine, tool_installer


def _fake(payload):
    def gen(_prompt):
        return json.dumps(payload)
    return gen


GOOD = {
    "name": "add_numbers",
    "function_code": "def add_numbers(a, b):\n    return a + b\n",
    "test_code": "from forged_tool import add_numbers\n\ndef test_add():\n    assert add_numbers(2, 3) == 5\n",
}
BAD = {
    "name": "add_numbers",
    "function_code": "def add_numbers(a, b):\n    return a + b\n",
    "test_code": "from forged_tool import add_numbers\n\ndef test_add():\n    assert add_numbers(2, 3) == 999\n",
}
RISKY = {
    "name": "list_dir",
    "function_code": "import os\n\ndef list_dir(path='.'):\n    return os.listdir(path)\n",
    "test_code": "from forged_tool import list_dir\n\ndef test_list():\n    assert isinstance(list_dir('.'), list)\n",
}


def test_good_safe_tool_forges_installs_and_runs(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    r = forge_engine.forge_tool("add two numbers", generate_fn=_fake(GOOD))
    assert r["ok"] is True and r["status"] == "installed" and r["name"] == "add_numbers"
    assert "add_numbers" in tool_installer.list_forged()
    assert tool_installer.call_forged("add_numbers", 4, 5) == 9   # the forged tool actually works
    assert tool_installer.remove("add_numbers") is True


def test_failing_tool_is_rejected_after_retries(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    r = forge_engine.forge_tool("broken", generate_fn=_fake(BAD), max_retries=1)
    assert r["ok"] is False and r["status"] == "failed"
    assert tool_installer.list_forged() == []


def test_risky_tool_needs_approval_not_installed(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_FORGE_DIR", str(tmp_path))
    r = forge_engine.forge_tool("list a directory", generate_fn=_fake(RISKY))
    assert r["ok"] is False and r["status"] == "needs_approval"
    assert "list_dir" not in tool_installer.list_forged()


def test_empty_spec_fails():
    assert forge_engine.forge_tool("  ")["status"] == "failed"
