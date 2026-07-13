"""Nexi -> Claude Code dispatcher, with a mocked `claude` process (no real runs)."""
import json

import engine.claude_code.dispatcher as d


class FakeProc:
    def __init__(self, lines, returncode=0):
        self.stdout = iter(lines)
        self.returncode = returncode
        self._waited = False

    def wait(self):
        self._waited = True

    def poll(self):
        return self.returncode if self._waited else None

    def terminate(self):
        pass


STREAM = [
    json.dumps({"type": "system", "subtype": "init"}) + "\n",
    json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "Working"}]}}) + "\n",
    json.dumps({"type": "result", "subtype": "success", "result": "Done: added the function.", "is_error": False}) + "\n",
]


def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NEXI_CLAUDE_CODE_ENABLED", raising=False)
    r = d.dispatch("do something")
    assert r["ok"] is False and r["reason"] == "disabled"


def test_empty_task(monkeypatch):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    assert d.dispatch("   ")["reason"] == "empty_task"


def test_successful_run_parses_events(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    monkeypatch.setattr(d.subprocess, "Popen", lambda *a, **k: FakeProc(list(STREAM), 0))
    seen = []
    r = d.dispatch("add a function", project_dir=str(tmp_path), on_event=seen.append)
    assert r["ok"] is True
    assert r["result"] == "Done: added the function."
    assert any(e.get("type") == "assistant" for e in seen)


def test_error_result_marks_not_ok(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    lines = [json.dumps({"type": "result", "result": "failed", "is_error": True}) + "\n"]
    monkeypatch.setattr(d.subprocess, "Popen", lambda *a, **k: FakeProc(lines, 0))
    r = d.dispatch("x", project_dir=str(tmp_path))
    assert r["ok"] is False and r["is_error"] is True


def test_claude_not_found(monkeypatch):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")

    def boom(*a, **k):
        raise FileNotFoundError()

    monkeypatch.setattr(d.subprocess, "Popen", boom)
    assert d.dispatch("x")["reason"] == "claude_not_found"


def test_build_command_default_permission(monkeypatch):
    monkeypatch.delenv("NEXI_CLAUDE_CODE_PERMISSION_MODE", raising=False)
    cmd = d.build_command("do X", "C:/proj")
    assert "-p" in cmd and "do X" in cmd
    assert "stream-json" in cmd and "--add-dir" in cmd
    assert "--permission-mode" in cmd and "acceptEdits" in cmd


def test_build_command_bypass_mode(monkeypatch):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_PERMISSION_MODE", "bypass")
    assert "--dangerously-skip-permissions" in d.build_command("x", "/p")
