"""Session orchestrator (dispatch -> verify), with both mocked."""
import time
import uuid

import engine.claude_code.session as s
from engine.claude_code.terminal_bridge import PtySession


def test_run_task_disabled_short_circuits(monkeypatch):
    monkeypatch.setattr(s.dispatcher, "dispatch", lambda *a, **k: {"ok": False, "reason": "disabled", "message": "off"})
    r = s.run_task("x")
    assert r["ok"] is False and r["message"] == "off" and r["verify"] is None


def test_run_task_ok_and_on_track(monkeypatch):
    monkeypatch.setattr(s.dispatcher, "dispatch", lambda *a, **k: {"ok": True, "result": "did it"})
    monkeypatch.setattr(s.verifier, "verify", lambda *a, **k: {
        "on_track": True,
        "checks": {"made_changes": True, "diff_stat": " x | 1 +", "tests_ran": True, "tests_passed": True},
    })
    r = s.run_task("do x", project_dir=".")
    assert r["ok"] and r["on_track"] and "on-track" in r["message"]


def test_run_task_off_track_explains(monkeypatch):
    monkeypatch.setattr(s.dispatcher, "dispatch", lambda *a, **k: {"ok": True, "result": "did it"})
    monkeypatch.setattr(s.verifier, "verify", lambda *a, **k: {"on_track": False, "checks": {"made_changes": False}})
    r = s.run_task("do x", project_dir=".")
    assert r["ok"] and not r["on_track"] and "off-track" in r["message"]


def test_failed_dispatch_does_not_execute_verification(monkeypatch):
    monkeypatch.setattr(s.dispatcher, "dispatch", lambda *a, **k: {"ok": False, "returncode": 1})
    monkeypatch.setattr(s.verifier, "verify", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not verify")))
    result = s.run_task("x", owner_id="test-owner")
    assert result["ok"] is False and result["verify"] is None


def test_run_task_forwards_named_agent_configuration(monkeypatch):
    captured = {}

    def fake_dispatch(*_args, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "result": "done"}

    monkeypatch.setattr(s.dispatcher, "dispatch", fake_dispatch)
    r = s.run_task(
        "x",
        verify=False,
        agent_name="business-analyst",
        agents_json='{"business-analyst":{"description":"d","prompt":"p"}}',
        allowlisted_skills=[],
    )
    assert r["ok"] is True
    assert captured["agent_name"] == "business-analyst"
    assert captured["agents_json"].startswith("{")
    assert captured["allowlisted_skills"] == []


def test_run_task_forwards_resume_and_fork_configuration(monkeypatch):
    captured = {}
    session_id = str(uuid.uuid4())

    def fake_dispatch(*_args, **kwargs):
        captured.update(kwargs)
        return {"ok": True, "result": "done", "session_id": session_id}

    monkeypatch.setattr(s.dispatcher, "dispatch", fake_dispatch)
    result = s.run_task("continue", verify=False, resume_session_id=session_id, fork_session=True)
    assert result["ok"] is True
    assert captured["resume_session_id"] == session_id
    assert captured["fork_session"] is True


def test_start_streaming_emits_events_and_done(monkeypatch):
    def fake_dispatch(task, project_dir=None, on_event=None, extra_args=None, **_kwargs):
        if on_event:
            on_event({"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}})
        return {"ok": True, "result": "done"}

    monkeypatch.setattr(s.dispatcher, "dispatch", fake_dispatch)
    monkeypatch.setattr(s.verifier, "verify", lambda *a, **k: {"on_track": True, "checks": {"made_changes": True, "diff_stat": ""}})
    got = []
    s.start_streaming("x", project_dir=".", emit=got.append)
    for _ in range(50):
        if any(p.get("kind") == "done" for p in got):
            break
        time.sleep(0.02)
    kinds = [p["kind"] for p in got]
    assert "event" in kinds and "done" in kinds


def test_pty_operation_failures_are_observable():
    class BrokenPty:
        def isalive(self):
            return True

        def read(self):
            raise OSError("read disconnected")

        def write(self, _data):
            raise OSError("write disconnected")

        def setwinsize(self, _rows, _cols):
            raise OSError("resize disconnected")

        def terminate(self, force=True):
            raise OSError("stop disconnected")

    pty = PtySession(lambda _data: None)
    pty._pty = BrokenPty()

    pty._read_loop()
    assert "read disconnected" in pty.last_error
    assert pty.write("x") is False
    assert "write disconnected" in pty.last_error
    assert pty.resize(80, 24) is False
    assert "resize disconnected" in pty.last_error
    assert pty.stop() is False
    assert "stop disconnected" in pty.last_error
