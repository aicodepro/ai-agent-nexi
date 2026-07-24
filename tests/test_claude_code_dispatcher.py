"""Nexi -> Claude Code dispatcher, with a mocked `claude` process (no real runs)."""
import json
import uuid

import pytest

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


SESSION_ID = str(uuid.uuid4())

STREAM = [
    json.dumps({"type": "system", "subtype": "init", "session_id": SESSION_ID}) + "\n",
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
    assert r["session_id"] == SESSION_ID
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
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ALLOW_DANGEROUS_PERMISSIONS", "1")
    assert "--dangerously-skip-permissions" in d.build_command("x", "/p")


def test_dangerous_permission_mode_requires_explicit_opt_in(monkeypatch):
    import pytest

    monkeypatch.setenv("NEXI_CLAUDE_CODE_PERMISSION_MODE", "bypassPermissions")
    monkeypatch.delenv("NEXI_CLAUDE_CODE_ALLOW_DANGEROUS_PERMISSIONS", raising=False)
    monkeypatch.delenv("NEXI_STUDIO_UNATTENDED", raising=False)

    with pytest.raises(ValueError, match="dangerous permission"):
        d.build_command("x", "/p")


@pytest.mark.parametrize("extra_args", [
    ["--dangerously-skip-permissions"],
    ["--permission-mode", "bypassPermissions"],
    "--model safe",
    ["--model", 42],
])
def test_build_command_rejects_unsafe_or_malformed_extra_args(extra_args):
    with pytest.raises(ValueError, match="extra_args"):
        d.build_command("x", "/p", extra_args=extra_args)


def test_build_command_supports_per_run_plan_mode(monkeypatch):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_PERMISSION_MODE", "acceptEdits")
    cmd = d.build_command("research", "C:/proj", permission_mode="plan")
    assert cmd[cmd.index("--permission-mode") + 1] == "plan"


def test_build_command_supports_validated_resume_and_optional_fork():
    session_id = str(uuid.uuid4())
    resumed = d.build_command("continue", "C:/proj", resume_session_id=session_id)
    assert resumed[resumed.index("--resume") + 1] == session_id
    assert "--fork-session" not in resumed
    forked = d.build_command("branch", "C:/proj", resume_session_id=session_id, fork_session=True)
    assert forked[forked.index("--resume") + 1] == session_id
    assert "--fork-session" in forked


def test_build_command_rejects_malformed_resume_and_orphan_fork():
    import pytest

    with pytest.raises(ValueError):
        d.build_command("x", "C:/proj", resume_session_id="not-a-uuid")
    with pytest.raises(ValueError):
        d.build_command("x", "C:/proj", fork_session=True)
    with pytest.raises(ValueError):
        d.build_command("x", "C:/proj", resume_session_id=str(uuid.uuid4()), fork_session="yes")


def test_result_event_session_uuid_is_extracted_when_init_omits_it(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    session_id = str(uuid.uuid4())
    lines = [json.dumps({"type": "result", "result": {"result": "done", "session_id": session_id}, "is_error": False}) + "\n"]
    monkeypatch.setattr(d.subprocess, "Popen", lambda *a, **k: FakeProc(lines, 0))
    result = d.dispatch("x", project_dir=str(tmp_path))
    assert result["session_id"] == session_id


def test_event_callback_failure_is_returned_to_the_caller(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    monkeypatch.setattr(d.subprocess, "Popen", lambda *a, **k: FakeProc(list(STREAM), 0))

    def broken_callback(_event):
        raise RuntimeError("UI stream disconnected")

    result = d.dispatch("x", project_dir=str(tmp_path), on_event=broken_callback)

    assert result["ok"] is True
    assert result["event_errors"]
    assert result["event_errors"][0]["type"] == "RuntimeError"
    assert "UI stream disconnected" in result["event_errors"][0]["message"]


def test_build_command_routes_validated_named_agent_without_safe_mode():
    agents = json.dumps({
        "qa-verifier": {
            "description": "Read-only QA",
            "prompt": "Verify only.",
            "tools": ["Read", "Grep"],
            "model": "inherit",
            "permissionMode": "acceptEdits",
            "maxTurns": 12,
        }
    })
    cmd = d.build_command(
        "verify",
        "C:/proj",
        agent_name="qa-verifier",
        agents_json=agents,
        allowlisted_skills=[],
        permission_mode="plan",
    )
    assert cmd[cmd.index("--agent") + 1] == "qa-verifier"
    dynamic = json.loads(cmd[cmd.index("--agents") + 1])["qa-verifier"]
    assert dynamic["prompt"] == "Verify only."
    assert dynamic["permissionMode"] == "plan"  # parent stage remains authoritative
    assert dynamic["maxTurns"] == 12
    assert "--strict-mcp-config" in cmd
    assert "--disable-slash-commands" in cmd
    assert "--safe-mode" not in cmd
    assert cmd[cmd.index("--setting-sources") + 1] == ""
    isolated = json.loads(cmd[cmd.index("--settings") + 1])
    assert isolated["disableAllHooks"] is True
    assert isolated["disableBundledSkills"] is True
    assert isolated["enabledPlugins"] == {}
    task = cmd[cmd.index("-p") + 1]
    assert "AUTHORIZED TARGET PROJECT (ABSOLUTE):" in task
    assert "C:\\proj" in task or "C:/proj" in task


def test_named_agent_runs_from_isolated_control_cwd(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    target = tmp_path / "target"
    control = tmp_path / "control"
    target.mkdir()
    control.mkdir()
    agents = json.dumps({
        "qa-verifier": {
            "description": "Read-only QA",
            "prompt": "Verify only.",
            "tools": ["Read", "Grep"],
        }
    })
    captured = {}

    def popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["cwd"] = kwargs["cwd"]
        return FakeProc(list(STREAM), 0)

    monkeypatch.setattr(d.subprocess, "Popen", popen)
    result = d.dispatch(
        "verify",
        project_dir=str(target),
        agent_name="qa-verifier",
        agents_json=agents,
        permission_mode="plan",
        control_cwd=str(control),
    )

    assert result["ok"] is True
    assert captured["cwd"] == str(control.resolve())
    assert captured["cwd"] != str(target.resolve())
    assert captured["cmd"][captured["cmd"].index("--add-dir") + 1] == str(target.resolve())


def test_named_agent_rejects_missing_or_unselected_agent_json():
    import pytest

    with pytest.raises(ValueError):
        d.build_command("x", "C:/proj", agent_name="qa-verifier", agents_json="{}")


def test_owner_scoped_stop_refuses_another_owner():
    dispatch = d.Dispatch()
    proc = FakeProc([], 0)
    dispatch._proc = proc
    dispatch._owner_id = "studio-1"
    assert dispatch.stop(owner_id="studio-2") is False
    assert dispatch.stop(owner_id="studio-1") is True
