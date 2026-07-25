"""Guard: NEXI must never force-kill a browser (a past incident closed the
user's Chrome and lost every tab). See engine/control/process_controller.py."""
import subprocess

import engine.control.process_controller as pc


def _recorder(monkeypatch):
    """Record taskkill invocations without running them.

    Must return a real CompletedProcess: kill_process now inspects
    `completed.returncode` so it reports an actual failure instead of claiming success
    unconditionally. A recorder returning None makes every non-blocked kill look failed.
    """
    calls = []

    def fake_run(*a, **k):
        calls.append(a[0] if a else k)
        return subprocess.CompletedProcess(a[0] if a else [], 0, "", "")

    monkeypatch.setattr(pc.subprocess, "run", fake_run)
    return calls


def test_chrome_force_kill_is_blocked(monkeypatch):
    monkeypatch.delenv("NEXI_ALLOW_BROWSER_KILL", raising=False)
    calls = _recorder(monkeypatch)
    result = pc.kill_process("chrome")
    assert result.ok is False
    assert result.error["code"] == "BROWSER_KILL_BLOCKED"
    assert calls == []  # taskkill never reached


def test_edge_and_firefox_also_blocked(monkeypatch):
    monkeypatch.delenv("NEXI_ALLOW_BROWSER_KILL", raising=False)
    calls = _recorder(monkeypatch)
    assert pc.kill_process("msedge").ok is False
    assert pc.kill_process("firefox").ok is False
    assert calls == []


def test_non_browser_kill_is_allowed(monkeypatch):
    calls = _recorder(monkeypatch)
    result = pc.kill_process("notepad")
    assert result.ok is True
    assert len(calls) == 1  # taskkill reached (swallowed by conftest)


def test_override_env_allows_browser_kill(monkeypatch):
    monkeypatch.setenv("NEXI_ALLOW_BROWSER_KILL", "1")
    calls = _recorder(monkeypatch)
    result = pc.kill_process("chrome")
    assert result.ok is True
    assert len(calls) == 1


# --- command-injection hardening ---------------------------------------------

def test_start_process_rejects_shell_metacharacters(monkeypatch):
    calls = []
    monkeypatch.setattr(pc.os, "system", lambda cmd: calls.append(cmd))
    result = pc.start_process("calc & del /q x")
    assert result.ok is False
    assert result.error["code"] == "UNSAFE_APP_NAME"
    assert calls == []  # shell never reached


def test_start_process_allows_safe_name(monkeypatch):
    """start_process no longer shells out via os.system — it launches an argv list with
    shell=False, which is what makes a voice-supplied app name un-injectable. Assert the
    mechanism that provides the guarantee, not the one it replaced."""
    calls = []

    def fake_popen(*a, **k):
        calls.append((a[0] if a else None, k))
        return None  # start_process does not use the handle

    monkeypatch.setattr(pc.subprocess, "Popen", fake_popen)
    result = pc.start_process("spotify")
    assert result.ok is True
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ["spotify"], "app name must be one argv element, never a shell string"
    assert kwargs.get("shell") is False


def test_kill_process_uses_argv_not_shell(monkeypatch):
    monkeypatch.delenv("NEXI_ALLOW_BROWSER_KILL", raising=False)
    captured = {}
    monkeypatch.setattr(pc.subprocess, "run", lambda *a, **k: captured.update(args=a, kwargs=k))
    pc.kill_process("notepad")
    assert isinstance(captured["args"][0], list)      # argv list, not a shell string
    assert captured["kwargs"].get("shell") is False
