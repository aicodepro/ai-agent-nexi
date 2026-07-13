"""Anti-hallucination verifier (mocked git/pytest — no real subprocesses)."""
import engine.claude_code.verifier as v


def test_on_track_when_changed_and_tests_pass(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " engine/x.py | 3 +++")
    monkeypatch.setattr(v, "run_tests", lambda p, test_cmd=None: {"ran": True, "passed": True, "output": "ok"})
    assert v.verify("task", "/p", {"ok": True})["on_track"] is True


def test_off_track_when_nothing_changed(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: "")
    monkeypatch.setattr(v, "run_tests", lambda p, test_cmd=None: {"ran": True, "passed": True, "output": ""})
    assert v.verify("task", "/p", {"ok": True})["on_track"] is False


def test_off_track_when_tests_fail(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")
    monkeypatch.setattr(v, "run_tests", lambda p, test_cmd=None: {"ran": True, "passed": False, "output": "boom"})
    assert v.verify("task", "/p", {"ok": True})["on_track"] is False


def test_model_verdict_false_makes_off_track(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")
    r = v.verify("task", "/p", {"ok": True}, run_tests_after=False, verifier_fn=lambda t, res, diff: False)
    assert r["on_track"] is False


def test_skip_tests_still_on_track(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")
    assert v.verify("task", "/p", {"ok": True}, run_tests_after=False)["on_track"] is True


def test_failed_dispatch_never_on_track(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")
    assert v.verify("task", "/p", {"ok": False}, run_tests_after=False)["on_track"] is False
