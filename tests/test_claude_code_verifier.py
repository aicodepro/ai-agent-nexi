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


def test_model_verifier_exception_is_observable_and_fails_closed(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")

    def broken_verifier(*_args):
        raise RuntimeError("verifier provider unavailable")

    result = v.verify("task", "/p", {"ok": True}, run_tests_after=False, verifier_fn=broken_verifier)

    assert result["on_track"] is False
    assert result["checks"]["model_verdict_error"]["type"] == "RuntimeError"
    assert "provider unavailable" in result["checks"]["model_verdict_error"]["message"]


def test_skip_tests_still_on_track(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")
    assert v.verify("task", "/p", {"ok": True}, run_tests_after=False)["on_track"] is True


def test_failed_dispatch_never_on_track(monkeypatch):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: " x | 1 +")
    assert v.verify("task", "/p", {"ok": False}, run_tests_after=False)["on_track"] is False


def test_workspace_baseline_detects_new_untracked_file(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: "")
    before = v.workspace_snapshot(str(tmp_path))
    (tmp_path / "new.py").write_text("print('new')", encoding="utf-8")
    result = v.verify("task", str(tmp_path), {"ok": True}, run_tests_after=False, baseline=before)
    assert result["on_track"] is True
    assert result["checks"]["workspace_change"]["added"] == ["new.py"]


def test_required_tests_fail_when_no_test_command(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: "")
    before = v.workspace_snapshot(str(tmp_path))
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")
    result = v.verify("task", str(tmp_path), {"ok": True}, baseline=before, require_tests=True)
    assert result["on_track"] is False
    assert result["checks"]["tests_ran"] is False


def test_test_process_workspace_mutation_fails_verification(monkeypatch, tmp_path):
    monkeypatch.setattr(v, "git_diff_stat", lambda p: "")
    before = v.workspace_snapshot(str(tmp_path))
    source = tmp_path / "app.py"
    source.write_text("safe = True", encoding="utf-8")

    def mutating_tests(_project, test_cmd=None):
        source.write_text("safe = False", encoding="utf-8")
        return {"ran": True, "passed": True, "output": "passed"}

    monkeypatch.setattr(v, "run_tests", mutating_tests)
    result = v.verify("task", str(tmp_path), {"ok": True}, baseline=before)
    assert result["on_track"] is False
    assert result["checks"]["test_workspace_change"]["modified"] == ["app.py"]


def test_workspace_snapshot_ignores_dependencies_and_test_artifacts(tmp_path):
    before = v.workspace_snapshot(str(tmp_path))
    (tmp_path / "node_modules" / "package").mkdir(parents=True)
    (tmp_path / "node_modules" / "package" / "index.js").write_text("generated", encoding="utf-8")
    (tmp_path / ".coverage").write_text("generated", encoding="utf-8")
    (tmp_path / "coverage.xml").write_text("generated", encoding="utf-8")
    (tmp_path / "htmlcov").mkdir()
    (tmp_path / "htmlcov" / "index.html").write_text("generated", encoding="utf-8")

    change = v.compare_workspace(before, v.workspace_snapshot(str(tmp_path)))

    assert change["changed"] is False
