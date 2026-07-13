"""Session orchestrator (dispatch -> verify), with both mocked."""
import time

import engine.claude_code.session as s


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


def test_start_streaming_emits_events_and_done(monkeypatch):
    def fake_dispatch(task, project_dir=None, on_event=None, extra_args=None):
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
