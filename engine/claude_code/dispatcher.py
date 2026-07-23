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
import threading
import re
import uuid

from engine.claude_code.environment import sanitized_environment

CREATE_NO_WINDOW = 0x08000000

_GUARDRAILS = (
    "Stay strictly on the requested task. Do not invent files, functions, or APIs "
    "that do not exist — check first. After making changes, run the project's tests "
    "if there are any. If you cannot verify a change works, say so explicitly rather "
    "than claiming success."
)
_TARGET_MARKER = "AUTHORIZED TARGET PROJECT (ABSOLUTE):"
_TRUE_VALUES = {"1", "true", "yes", "on"}
_RESERVED_EXTRA_ARGS = {
    "-p", "--print", "--dangerously-skip-permissions", "--permission-mode",
    "--add-dir", "--settings", "--setting-sources", "--agents", "--agent",
    "--mcp-config", "--strict-mcp-config", "--resume", "--fork-session",
}
_ISOLATED_AGENT_SETTINGS = {
    "disableAllHooks": True,
    "disableBundledSkills": True,
    "disableWorkflows": True,
    "disableClaudeAiConnectors": True,
    "autoMemoryEnabled": False,
    "enabledPlugins": {},
    "includeGitInstructions": False,
    "env": {
        "CLAUDE_AGENT_SDK_DISABLE_BUILTIN_AGENTS": "1",
        "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "0",
        "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
        "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1",
        "CLAUDE_CODE_DISABLE_BUNDLED_SKILLS": "1",
        "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
        "CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL": "1",
        "CLAUDE_CODE_DISABLE_WORKFLOWS": "1",
    },
}


def is_enabled() -> bool:
    return os.getenv("NEXI_CLAUDE_CODE_ENABLED", "").strip().lower() in ("1", "true", "yes")


def claude_path() -> str:
    return os.getenv("CLAUDE_CLI_PATH") or shutil.which("claude") or "claude"


def _permission_args(permission_mode: str | None = None) -> list[str]:
    mode = _canonical_permission_mode(permission_mode)
    if mode == "bypassPermissions":
        return ["--dangerously-skip-permissions"]
    return ["--permission-mode", mode]


def _canonical_permission_mode(permission_mode: str | None) -> str:
    mode = str(permission_mode or os.getenv("NEXI_CLAUDE_CODE_PERMISSION_MODE", "acceptEdits")).strip()
    if mode in ("bypass", "dangerously-skip", "dangerously-skip-permissions"):
        mode = "bypassPermissions"
    if mode not in {"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"}:
        raise ValueError("Invalid Claude Code permission mode.")
    dangerous_allowed = (
        str(os.getenv("NEXI_CLAUDE_CODE_ALLOW_DANGEROUS_PERMISSIONS") or "").strip().lower() in _TRUE_VALUES
        or str(os.getenv("NEXI_STUDIO_UNATTENDED") or "").strip().lower() in _TRUE_VALUES
    )
    if mode == "bypassPermissions" and not dangerous_allowed:
        raise ValueError("Claude Code dangerous permission mode requires explicit operator opt-in.")
    return mode


def _validated_extra_args(extra_args) -> list[str]:
    if extra_args is None:
        return []
    if not isinstance(extra_args, (list, tuple)):
        raise ValueError("extra_args must be a list or tuple of strings.")
    validated = []
    for arg in extra_args:
        if not isinstance(arg, str) or not arg or "\x00" in arg:
            raise ValueError("extra_args must contain non-empty strings without NUL bytes.")
        if arg.split("=", 1)[0] in _RESERVED_EXTRA_ARGS:
            raise ValueError(f"extra_args cannot override reserved Claude option: {arg}")
        validated.append(arg)
    return validated


def _validated_agents_json(agents_json: str | None, agent_name: str | None, permission_mode: str | None = None) -> str:
    if not agent_name:
        if agents_json:
            raise ValueError("agents_json requires agent_name.")
        return ""
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", str(agent_name)):
        raise ValueError("Invalid named agent.")
    try:
        payload = json.loads(str(agents_json or ""))
    except json.JSONDecodeError as exc:
        raise ValueError("agents_json is not valid JSON.") from exc
    if not isinstance(payload, dict) or agent_name not in payload:
        raise ValueError("agents_json does not define the selected agent.")
    parent_permission = _canonical_permission_mode(permission_mode)
    for name, definition in payload.items():
        if not re.fullmatch(r"[a-z][a-z0-9-]{1,63}", str(name)) or not isinstance(definition, dict):
            raise ValueError("agents_json contains an invalid agent definition.")
        if not str(definition.get("description") or "").strip() or not str(definition.get("prompt") or "").strip():
            raise ValueError("agents_json agent definitions require description and prompt.")
        tools = definition.get("tools")
        if tools is not None and (not isinstance(tools, list) or any(not isinstance(tool, str) for tool in tools)):
            raise ValueError("agents_json tools must be a list of strings.")
        maximum = definition.get("maxTurns")
        if maximum is not None and (not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 100):
            raise ValueError("agents_json maxTurns must be an integer from 1 to 100.")
        requested_permission = definition.get("permissionMode")
        if requested_permission is not None and str(requested_permission) not in {"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"}:
            raise ValueError("agents_json permissionMode is invalid.")
        # The parent stage is authoritative; a dynamic child definition cannot escalate it.
        definition["permissionMode"] = parent_permission
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def bind_target_to_task(task: str, project_dir: str) -> str:
    """Bind a named-agent prompt to the explicit target without changing cwd."""
    target = os.path.abspath(os.path.expanduser(str(project_dir or "")))
    text = str(task or "").strip()
    if _TARGET_MARKER in text:
        return text
    return f"{text}\n\n{_TARGET_MARKER} {target}\nUse this explicit target for all project reads, edits, and commands."


def isolated_agent_settings_json() -> str:
    return json.dumps(_ISOLATED_AGENT_SETTINGS, sort_keys=True, separators=(",", ":"))


def _validated_control_cwd(control_cwd: str | None, project_dir: str) -> str:
    target = os.path.abspath(os.path.expanduser(project_dir))
    control = os.path.abspath(os.path.expanduser(str(control_cwd or "")))
    if not control_cwd or not os.path.isdir(control):
        raise ValueError("Named Studio agents require an existing isolated control directory.")
    try:
        inside_target = os.path.commonpath([os.path.normcase(control), os.path.normcase(target)]) == os.path.normcase(target)
    except ValueError:
        inside_target = False
    if inside_target:
        raise ValueError("The Claude control directory must be outside the target project.")
    return control


def validate_session_id(session_id: str | None) -> str:
    """Return a canonical Claude session UUID or reject unsafe CLI input."""
    value = str(session_id or "").strip()
    if not value:
        raise ValueError("Claude resume session ID is required.")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError("Claude resume session ID must be a valid UUID.") from exc
    if value.lower() != str(parsed):
        raise ValueError("Claude resume session ID must use canonical UUID format.")
    return str(parsed)


def _session_id_from_event(event: object) -> str:
    if not isinstance(event, dict):
        return ""
    candidates = [event.get("session_id")]
    result = event.get("result")
    if isinstance(result, dict):
        candidates.append(result.get("session_id"))
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return validate_session_id(str(candidate))
        except ValueError:
            continue
    return ""


def build_command(
    task: str,
    project_dir: str,
    extra_args=None,
    permission_mode: str | None = None,
    *,
    agent_name: str | None = None,
    agents_json: str | None = None,
    allowlisted_skills: list[str] | tuple[str, ...] | None = None,
    resume_session_id: str | None = None,
    fork_session: bool = False,
) -> list[str]:
    validated_extra_args = _validated_extra_args(extra_args)
    selected_agents = _validated_agents_json(agents_json, agent_name, permission_mode)
    if agent_name and allowlisted_skills:
        raise ValueError("Named Studio agents permit only SHA-verified injected agents; filesystem skills are disabled.")
    if not isinstance(fork_session, bool):
        raise ValueError("fork_session must be a boolean.")
    resume_args: list[str] = []
    if resume_session_id is not None:
        resume_args = ["--resume", validate_session_id(resume_session_id)]
        if fork_session:
            resume_args.append("--fork-session")
    elif fork_session:
        raise ValueError("fork_session requires resume_session_id.")
    agent_args: list[str] = []
    effective_task = str(task or "")
    if agent_name:
        effective_task = bind_target_to_task(effective_task, project_dir)
        agent_args = [
            "--setting-sources", "",
            "--settings", isolated_agent_settings_json(),
            "--agents", selected_agents,
            "--agent", str(agent_name),
            "--strict-mcp-config",
            "--disable-slash-commands",
            "--no-chrome",
        ]
    return [
        claude_path(), "-p", effective_task,
        *resume_args,
        *agent_args,
        "--output-format", "stream-json", "--verbose",
        "--add-dir", project_dir,
        "--append-system-prompt", _GUARDRAILS,
        *_permission_args(permission_mode),
        *validated_extra_args,
    ]


def _terminate_process(proc) -> bool:
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
        except TypeError:
            proc.wait()
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        return proc.poll() is not None
    except Exception:
        return False


class Dispatch:
    """One live Claude Code run with owner-scoped cancellation."""

    def __init__(self):
        self._proc = None
        self._owner_id = None
        self._run_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._cancel_requested: set[str] = set()

    def run(
        self,
        task: str,
        project_dir: str | None = None,
        on_event=None,
        extra_args=None,
        *,
        owner_id: str | None = None,
        permission_mode: str | None = None,
        agent_name: str | None = None,
        agents_json: str | None = None,
        allowlisted_skills: list[str] | tuple[str, ...] | None = None,
        resume_session_id: str | None = None,
        fork_session: bool = False,
        control_cwd: str | None = None,
    ) -> dict:
        if not is_enabled():
            return {"ok": False, "reason": "disabled",
                    "message": "Claude Code control is off. Set NEXI_CLAUDE_CODE_ENABLED=1 to enable."}
        if not str(task or "").strip():
            return {"ok": False, "reason": "empty_task", "message": "No task given."}

        target_cwd = os.path.abspath(os.path.expanduser(project_dir or os.getcwd()))
        if not os.path.isdir(target_cwd):
            return {"ok": False, "reason": "invalid_project_dir", "message": "The project directory does not exist."}
        try:
            process_cwd = _validated_control_cwd(control_cwd, target_cwd) if agent_name else target_cwd
        except ValueError as exc:
            return {"ok": False, "reason": "invalid_control_cwd", "message": str(exc)}
        try:
            maximum_events = max(10, int(os.getenv("NEXI_CLAUDE_CODE_MAX_EVENTS", "500")))
        except ValueError:
            return {"ok": False, "reason": "invalid_configuration", "message": "NEXI_CLAUDE_CODE_MAX_EVENTS must be an integer."}
        if not self._run_lock.acquire(blocking=False):
            with self._state_lock:
                active_owner = self._owner_id
            return {"ok": False, "reason": "busy", "owner_id": active_owner,
                    "message": "Claude Code is already running another task."}

        owner = str(owner_id or f"dispatch-{threading.get_ident()}")
        proc = None
        completed = False
        try:
            with self._state_lock:
                self._owner_id = owner
                self._proc = None
            try:
                cmd = build_command(
                    task,
                    target_cwd,
                    extra_args,
                    permission_mode=permission_mode,
                    agent_name=agent_name,
                    agents_json=agents_json,
                    allowlisted_skills=allowlisted_skills,
                    resume_session_id=resume_session_id,
                    fork_session=fork_session,
                )
                popen_kwargs = {}
                if sys.platform == "win32":
                    popen_kwargs["creationflags"] = CREATE_NO_WINDOW
                proc = subprocess.Popen(
                    cmd, cwd=process_cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, env=sanitized_environment(for_claude=True), **popen_kwargs,
                )
                with self._state_lock:
                    self._proc = proc
                    cancelled_before_spawn = owner in self._cancel_requested
                if cancelled_before_spawn:
                    _terminate_process(proc)
            except FileNotFoundError:
                return {"ok": False, "reason": "claude_not_found",
                        "message": "Claude Code CLI not found. Install it or set CLAUDE_CLI_PATH."}
            except ValueError as exc:
                return {"ok": False, "reason": "invalid_agent_configuration", "message": str(exc)}

            events = []
            event_errors = []
            result_text = ""
            is_error = False
            session_id = ""
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    event = {"type": "raw", "text": line}
                events.append(event)
                if len(events) > maximum_events:
                    del events[:len(events) - maximum_events]
                if event.get("type") == "result":
                    result_payload = event.get("result")
                    if isinstance(result_payload, dict):
                        result_text = result_payload.get("result") or result_payload.get("text") or result_text
                    else:
                        result_text = result_payload or event.get("text") or result_text
                    is_error = bool(event.get("is_error"))
                event_session_id = _session_id_from_event(event)
                if event_session_id:
                    session_id = event_session_id
                if on_event:
                    try:
                        on_event(event)
                    except Exception as exc:
                        event_errors.append({"type": type(exc).__name__, "message": str(exc)})
                        if len(event_errors) > 20:
                            del event_errors[:-20]

            proc.wait()
            completed = True
            returncode = proc.returncode
            with self._state_lock:
                cancelled = owner in self._cancel_requested
            return {
                "ok": returncode == 0 and not is_error,
                "reason": "cancelled" if cancelled else "",
                "returncode": returncode,
                "result": result_text,
                "is_error": is_error,
                "events": events,
                "event_errors": event_errors,
                "owner_id": owner,
                "session_id": session_id,
                "project_dir": target_cwd,
                "control_cwd": process_cwd,
            }
        finally:
            if proc is not None and not completed and proc.poll() is None:
                _terminate_process(proc)
            with self._state_lock:
                self._proc = None
                self._owner_id = None
                self._cancel_requested.discard(owner)
            self._run_lock.release()

    def stop(self, owner_id: str | None = None) -> bool:
        with self._state_lock:
            proc = self._proc
            owner = self._owner_id
        requested_owner = str(owner_id) if owner_id else owner
        if owner_id and owner not in {None, requested_owner}:
            return False
        if requested_owner:
            with self._state_lock:
                self._cancel_requested.add(requested_owner)
        if requested_owner and proc is None:
            return True
        if proc and proc.poll() is None:
            return _terminate_process(proc)
        return False


_dispatch = Dispatch()


def dispatch(
    task: str,
    project_dir: str | None = None,
    on_event=None,
    extra_args=None,
    *,
    owner_id: str | None = None,
    permission_mode: str | None = None,
    agent_name: str | None = None,
    agents_json: str | None = None,
    allowlisted_skills: list[str] | tuple[str, ...] | None = None,
    resume_session_id: str | None = None,
    fork_session: bool = False,
    control_cwd: str | None = None,
) -> dict:
    return _dispatch.run(
        task,
        project_dir=project_dir,
        on_event=on_event,
        extra_args=extra_args,
        owner_id=owner_id,
        permission_mode=permission_mode,
        agent_name=agent_name,
        agents_json=agents_json,
        allowlisted_skills=allowlisted_skills,
        resume_session_id=resume_session_id,
        fork_session=fork_session,
        control_cwd=control_cwd,
    )


def stop(owner_id: str | None = None) -> bool:
    return _dispatch.stop(owner_id=owner_id)
