"""Nexi -> Claude Code dispatcher.

Hands a coding task to the installed `claude` CLI running headless in auto mode,
scoped to a project directory, and streams its events back. Human-triggered only.

Opt-in: NEXI_CLAUDE_CODE_ENABLED=1.
Permission mode: NEXI_CLAUDE_CODE_PERMISSION_MODE (default "acceptEdits"; set to
"bypass"/"dangerously-skip" for full auto including shell commands).
CLI path override: CLAUDE_CLI_PATH.
"""
import json
import os
import shutil
import subprocess
import sys

CREATE_NO_WINDOW = 0x08000000

_GUARDRAILS = (
    "Stay strictly on the requested task. Do not invent files, functions, or APIs "
    "that do not exist — check first. After making changes, run the project's tests "
    "if there are any. If you cannot verify a change works, say so explicitly rather "
    "than claiming success."
)


def is_enabled() -> bool:
    return os.getenv("NEXI_CLAUDE_CODE_ENABLED", "").strip().lower() in ("1", "true", "yes")


def claude_path() -> str:
    return os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude") or "claude"


def _permission_args() -> list[str]:
    mode = os.getenv("NEXI_CLAUDE_CODE_PERMISSION_MODE", "acceptEdits").strip()
    if mode in ("bypass", "dangerously-skip", "dangerously-skip-permissions"):
        return ["--dangerously-skip-permissions"]
    return ["--permission-mode", mode]


def build_command(task: str, project_dir: str, extra_args=None) -> list[str]:
    return [
        claude_path(), "-p", task,
        "--output-format", "stream-json", "--verbose",
        "--add-dir", project_dir,
        "--append-system-prompt", _GUARDRAILS,
        *_permission_args(),
        *(extra_args or []),
    ]


class Dispatch:
    """One live Claude Code run. Not thread-safe across concurrent runs; one at a time."""

    def __init__(self):
        self._proc = None

    def run(self, task: str, project_dir: str | None = None, on_event=None, extra_args=None) -> dict:
        if not is_enabled():
            return {"ok": False, "reason": "disabled",
                    "message": "Claude Code control is off. Set NEXI_CLAUDE_CODE_ENABLED=1 to enable."}
        if not str(task or "").strip():
            return {"ok": False, "reason": "empty_task", "message": "No task given."}

        cwd = project_dir or os.getcwd()
        cmd = build_command(task, cwd, extra_args)
        popen_kwargs = {}
        if sys.platform == "win32":
            popen_kwargs["creationflags"] = CREATE_NO_WINDOW
        try:
            self._proc = subprocess.Popen(
                cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1, **popen_kwargs,
            )
        except FileNotFoundError:
            self._proc = None
            return {"ok": False, "reason": "claude_not_found",
                    "message": "Claude Code CLI not found. Install it or set CLAUDE_CLI_PATH."}

        events = []
        result_text = ""
        is_error = False
        for line in self._proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "raw", "text": line}
            events.append(event)
            if event.get("type") == "result":
                result_text = event.get("result") or event.get("text") or result_text
                is_error = bool(event.get("is_error"))
            if on_event:
                try:
                    on_event(event)
                except Exception:
                    pass

        self._proc.wait()
        returncode = self._proc.returncode
        self._proc = None
        return {
            "ok": returncode == 0 and not is_error,
            "returncode": returncode,
            "result": result_text,
            "is_error": is_error,
            "events": events,
        }

    def stop(self) -> bool:
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:
                return False
            return True
        return False


_dispatch = Dispatch()


def dispatch(task: str, project_dir: str | None = None, on_event=None, extra_args=None) -> dict:
    return _dispatch.run(task, project_dir=project_dir, on_event=on_event, extra_args=extra_args)


def stop() -> bool:
    return _dispatch.stop()
