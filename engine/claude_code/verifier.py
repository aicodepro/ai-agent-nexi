"""Anti-hallucination verification after a Claude Code run.

Neither model is trusted blindly. After a dispatch, check reality:
- did the working tree actually change (git diff)?
- do the project's tests still pass?
- (optional) a second-model verdict: did this accomplish the task?
Returns {on_track: bool, checks: {...}}.
"""
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
from pathlib import Path

from engine.claude_code.environment import sanitized_environment

CREATE_NO_WINDOW = 0x08000000
_IGNORED_DIRS = {
    ".hg", ".svn", "__pycache__", ".pytest_cache", ".mypy_cache", "node_modules",
    "coverage", "htmlcov", ".nyc_output", "test-results", "playwright-report",
}
_IGNORED_FILES = {".coverage", "coverage.xml", "junit.xml"}
_TEST_PROCESSES: dict[str, subprocess.Popen] = {}
_TEST_CANCELLED: set[str] = set()
_TEST_LOCK = threading.RLock()


def _terminate_process(proc: subprocess.Popen) -> bool:
    try:
        if proc.poll() is not None:
            return True
        if sys.platform == "win32" and getattr(proc, "pid", None):
            killed = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            if killed.returncode != 0 and proc.poll() is None:
                return False
        else:
            proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        return proc.poll() is not None
    except Exception:
        return False


def cancel_tests(owner_id: str) -> bool:
    owner = str(owner_id or "")
    if not owner:
        return False
    with _TEST_LOCK:
        _TEST_CANCELLED.add(owner)
        proc = _TEST_PROCESSES.get(owner)
    return True if proc is None else _terminate_process(proc)


def clear_test_cancellation(owner_id: str | None) -> None:
    if not owner_id:
        return
    with _TEST_LOCK:
        _TEST_CANCELLED.discard(str(owner_id))


def _run(cmd, cwd=None, timeout=600, owner_id: str | None = None):
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = CREATE_NO_WINDOW
    owner = str(owner_id or "")
    with _TEST_LOCK:
        if owner and owner in _TEST_CANCELLED:
            return subprocess.CompletedProcess(cmd, -1, "", "cancelled before test start")
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=sanitized_environment(),
        **kwargs,
    )
    if owner:
        with _TEST_LOCK:
            _TEST_PROCESSES[owner] = proc
            cancelled = owner in _TEST_CANCELLED
        if cancelled:
            _terminate_process(proc)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _terminate_process(proc)
        stdout, stderr = proc.communicate()
        stderr = (stderr or "") + "\ntest process timed out"
    finally:
        if owner:
            with _TEST_LOCK:
                if _TEST_PROCESSES.get(owner) is proc:
                    _TEST_PROCESSES.pop(owner, None)
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)


def git_diff_stat(project_dir: str) -> str:
    """Summary of uncommitted changes ('' if the tree is unchanged)."""
    try:
        out = _run(["git", "-C", project_dir, "diff", "--stat"], timeout=20)
        return out.stdout.strip()
    except Exception:
        return ""


def workspace_snapshot(project_dir: str) -> dict:
    """Capture a bounded content fingerprint for baseline-aware verification."""
    root = Path(project_dir).expanduser().resolve()
    maximum = max(1, int(os.getenv("NEXI_VERIFY_MAX_FILES", "100000")))
    files: dict[str, str] = {}
    truncated = False
    errors: list[str] = []
    if not root.is_dir():
        return {"root": str(root), "files": files, "truncated": False, "errors": []}
    def _walk_error(exc: OSError) -> None:
        nonlocal truncated
        truncated = True
        errors.append(f"{getattr(exc, 'filename', root)}: {type(exc).__name__}")

    for current, dirs, names in os.walk(root, followlinks=False, onerror=_walk_error):
        relative_parts = Path(current).relative_to(root).parts
        if relative_parts and relative_parts[0] == ".git":
            if len(relative_parts) == 1:
                dirs[:] = [name for name in dirs if name == "hooks"]
                names = [name for name in names if name in {"config", "HEAD", "index"}]
            elif len(relative_parts) == 2 and relative_parts[1] == "hooks":
                dirs[:] = []
            else:
                dirs[:] = []
                names = []
        else:
            dirs[:] = sorted(name for name in dirs if name not in _IGNORED_DIRS)
        for name in sorted(names):
            if name in _IGNORED_FILES:
                continue
            path = Path(current) / name
            try:
                relative = path.relative_to(root).as_posix()
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                files[relative] = digest.hexdigest()
            except (OSError, ValueError) as exc:
                errors.append(f"{path}: {type(exc).__name__}")
                truncated = True
                continue
            if len(files) >= maximum:
                truncated = True
                break
        if truncated:
            break
    return {"root": str(root), "files": files, "truncated": truncated, "errors": errors[:20]}


def compare_workspace(before: dict | None, after: dict | None) -> dict:
    before_files = dict((before or {}).get("files") or {})
    after_files = dict((after or {}).get("files") or {})
    added = sorted(set(after_files) - set(before_files))
    deleted = sorted(set(before_files) - set(after_files))
    modified = sorted(path for path in set(before_files) & set(after_files) if before_files[path] != after_files[path])
    changed = bool(added or deleted or modified)
    parts = []
    if added:
        parts.append(f"{len(added)} added")
    if modified:
        parts.append(f"{len(modified)} modified")
    if deleted:
        parts.append(f"{len(deleted)} deleted")
    return {
        "changed": changed,
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "summary": ", ".join(parts) if parts else "no workspace changes",
        "truncated": bool((before or {}).get("truncated") or (after or {}).get("truncated")),
    }


def detect_test_command(project_dir: str) -> list[str] | None:
    root = Path(project_dir)
    package_json = root / "package.json"
    if package_json.is_file():
        try:
            package = json.loads(package_json.read_text(encoding="utf-8"))
            script = str((package.get("scripts") or {}).get("test") or "").strip()
            if script and "no test specified" not in script.lower():
                if (root / "pnpm-lock.yaml").exists():
                    return ["pnpm", "test"]
                if (root / "yarn.lock").exists():
                    return ["yarn", "test"]
                return ["npm", "test"]
        except (OSError, ValueError, TypeError):
            pass
    python_markers = ("pyproject.toml", "pytest.ini", "setup.cfg", "tox.ini")
    if (root / "tests").is_dir() or any((root / marker).is_file() for marker in python_markers):
        return [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider"]
    return None


def run_tests(project_dir: str, test_cmd=None, *, owner_id: str | None = None) -> dict:
    """Run the project's tests. Returns {ran, passed, output}."""
    cmd = test_cmd or detect_test_command(project_dir)
    if not cmd:
        return {"ran": False, "passed": False, "output": "no test command detected"}
    if isinstance(cmd, str):
        cmd = shlex.split(cmd, posix=sys.platform != "win32")
    try:
        out = _run(cmd, cwd=project_dir, owner_id=owner_id)
        return {"ran": True, "passed": out.returncode == 0, "output": (out.stdout + out.stderr)[-2000:]}
    except Exception as exc:
        return {"ran": False, "passed": False, "output": f"could not run tests: {exc}"}


def verify(
    task: str,
    project_dir: str,
    dispatch_result: dict,
    *,
    run_tests_after=True,
    verifier_fn=None,
    baseline: dict | None = None,
    test_cmd=None,
    require_tests: bool = False,
    owner_id: str | None = None,
) -> dict:
    """Combine reality checks into an on-track verdict."""
    diff = git_diff_stat(project_dir)
    workspace_change = None
    made_changes = bool(diff)
    if baseline is not None:
        workspace_change = compare_workspace(baseline, workspace_snapshot(project_dir))
        made_changes = bool(workspace_change["changed"])
        if not diff:
            diff = workspace_change["summary"]
    checks = {"made_changes": made_changes, "diff_stat": diff}
    if workspace_change is not None:
        checks["workspace_change"] = workspace_change

    if run_tests_after:
        before_tests = workspace_snapshot(project_dir)
        test_kwargs = {"test_cmd": test_cmd}
        if owner_id is not None:
            test_kwargs["owner_id"] = owner_id
        t = run_tests(project_dir, **test_kwargs)
        checks["tests_ran"] = t["ran"]
        checks["tests_passed"] = t["passed"]
        checks["tests_output"] = t["output"]
        checks["test_workspace_change"] = compare_workspace(before_tests, workspace_snapshot(project_dir))

    model_verdict = None
    model_verdict_error = None
    if verifier_fn:
        try:
            model_verdict = bool(verifier_fn(task, (dispatch_result or {}).get("result", ""), diff))
        except Exception as exc:
            model_verdict_error = {"type": type(exc).__name__, "message": str(exc)}
    checks["model_verdict"] = model_verdict
    checks["model_verdict_error"] = model_verdict_error

    # On-track = the dispatch succeeded, something actually changed, tests didn't
    # regress, and (if we asked a verifier model) it agreed.
    on_track = bool((dispatch_result or {}).get("ok")) and checks["made_changes"]
    if workspace_change is not None and workspace_change.get("truncated"):
        on_track = False
    if checks.get("tests_ran"):
        on_track = on_track and checks["tests_passed"]
    elif require_tests:
        on_track = False
    if model_verdict is not None:
        on_track = on_track and model_verdict
    if model_verdict_error is not None:
        on_track = False
    test_workspace_change = checks.get("test_workspace_change") or {}
    if test_workspace_change.get("changed") or test_workspace_change.get("truncated"):
        on_track = False

    return {"on_track": on_track, "checks": checks}
