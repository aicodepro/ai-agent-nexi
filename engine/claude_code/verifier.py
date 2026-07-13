"""Anti-hallucination verification after a Claude Code run.

Neither model is trusted blindly. After a dispatch, check reality:
- did the working tree actually change (git diff)?
- do the project's tests still pass?
- (optional) a second-model verdict: did this accomplish the task?
Returns {on_track: bool, checks: {...}}.
"""
import os
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000


def _run(cmd, cwd=None, timeout=600):
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout, **kwargs)


def git_diff_stat(project_dir: str) -> str:
    """Summary of uncommitted changes ('' if the tree is unchanged)."""
    try:
        out = _run(["git", "-C", project_dir, "diff", "--stat"], timeout=20)
        return out.stdout.strip()
    except Exception:
        return ""


def run_tests(project_dir: str, test_cmd=None) -> dict:
    """Run the project's tests. Returns {ran, passed, output}."""
    cmd = test_cmd or [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    try:
        out = _run(cmd, cwd=project_dir)
        return {"ran": True, "passed": out.returncode == 0, "output": (out.stdout + out.stderr)[-2000:]}
    except Exception as exc:
        return {"ran": False, "passed": False, "output": f"could not run tests: {exc}"}


def verify(task: str, project_dir: str, dispatch_result: dict, *, run_tests_after=True, verifier_fn=None) -> dict:
    """Combine reality checks into an on-track verdict."""
    diff = git_diff_stat(project_dir)
    checks = {"made_changes": bool(diff), "diff_stat": diff}

    if run_tests_after:
        t = run_tests(project_dir)
        checks["tests_ran"] = t["ran"]
        checks["tests_passed"] = t["passed"]
        checks["tests_output"] = t["output"]

    model_verdict = None
    if verifier_fn:
        try:
            model_verdict = bool(verifier_fn(task, (dispatch_result or {}).get("result", ""), diff))
        except Exception:
            model_verdict = None
    checks["model_verdict"] = model_verdict

    # On-track = the dispatch succeeded, something actually changed, tests didn't
    # regress, and (if we asked a verifier model) it agreed.
    on_track = bool((dispatch_result or {}).get("ok")) and checks["made_changes"]
    if checks.get("tests_ran"):
        on_track = on_track and checks["tests_passed"]
    if model_verdict is not None:
        on_track = on_track and model_verdict

    return {"on_track": on_track, "checks": checks}
