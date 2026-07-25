"""Built-in agent-runtime adapters.

Claude keeps its existing hardened dispatcher. Other providers use bounded,
no-shell subprocess adapters and return the same dispatch envelope.
"""

from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable

from engine.agent_runtime.contracts import AgentEvent, AgentRunRequest, RuntimeCapabilities
from engine.agent_runtime.environment import runtime_environment
from engine.claude_code import dispatcher as claude_dispatcher
from engine.memory_safety import redact_sensitive


CREATE_NO_WINDOW = 0x08000000
_SESSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,511}$")
_SENSITIVE_KEY_RE = re.compile(r"(?:api[_-]?key|token|password|secret|cookie|private[_-]?key|authorization)", re.I)


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        return max(minimum, min(maximum, int(os.getenv(name, str(default)))))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def sanitize_runtime_value(value: Any, *, depth: int = 0) -> Any:
    """Deep-redact provider output and keep every retained event bounded."""
    if depth >= 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in list(value.items())[:100]:
            label = str(key)[:120]
            safe[label] = "[REDACTED]" if _SENSITIVE_KEY_RE.search(label) else sanitize_runtime_value(item, depth=depth + 1)
        return safe
    if isinstance(value, (list, tuple)):
        return [sanitize_runtime_value(item, depth=depth + 1) for item in list(value)[:100]]
    if isinstance(value, str):
        return redact_sensitive(value)[:_bounded_int("NEXI_AGENT_RUNTIME_EVENT_CHARS", 16000, 1000, 64000)]
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redact_sensitive(str(value))[:2000]


def _runtime_path(env_name: str, executable: str) -> str:
    return str(os.getenv(env_name) or shutil.which(executable) or executable)


def _agent_delegates(tools: set[str], roster: set[str]) -> list[str]:
    delegates: set[str] = set()
    for tool in tools:
        match = re.fullmatch(r"Agent\(([^)]*)\)", str(tool).strip())
        if not match:
            continue
        delegates.update(name.strip() for name in match.group(1).split(",") if name.strip())
    unknown = delegates - roster
    if unknown:
        raise ValueError(f"Trusted agent delegation references unknown roles: {', '.join(sorted(unknown))}")
    return sorted(delegates)


def _validate_opaque_session(value: str | None) -> str:
    session_id = str(value or "").strip()
    if not session_id or not _SESSION_RE.fullmatch(session_id):
        raise ValueError("Agent session ID is missing or contains unsafe characters.")
    return session_id


def _trusted_prompt(request: AgentRunRequest) -> str:
    task = str(request.task or "").strip()
    if not request.agent_name or not request.agents_json:
        return task
    try:
        definitions = json.loads(request.agents_json)
    except json.JSONDecodeError as exc:
        raise ValueError("Trusted agent definitions are not valid JSON.") from exc
    selected = definitions.get(request.agent_name) if isinstance(definitions, dict) else None
    if not isinstance(selected, dict):
        raise ValueError("The selected trusted agent definition is missing.")
    roster = ", ".join(sorted(str(name) for name in definitions))
    role_prompt = str(selected.get("prompt") or "").strip()
    if not role_prompt:
        raise ValueError("The selected trusted agent has no prompt.")
    role_contracts = []
    for name, definition in sorted(definitions.items()):
        if not isinstance(definition, dict):
            continue
        tools = ", ".join(str(tool) for tool in definition.get("tools") or []) or "none"
        role_contracts.append(
            f"[{name}] {str(definition.get('description') or '').strip()}\n"
            f"Allowed tools: {tools}; max turns: {int(definition.get('maxTurns') or 12)}\n"
            f"Contract: {str(definition.get('prompt') or '').strip()}"
        )
    contracts_text = "\n\n".join(role_contracts)
    return (
        f"NEXI TRUSTED ENTRY ROLE: {request.agent_name}\n"
        f"AVAILABLE TRUSTED ROLE ROSTER: {roster}\n"
        "Nexi is the sole supervisor and gate authority. You may delegate only when your runtime "
        "supports it and only to roles in this roster. Never claim that a child agent ran unless "
        "your runtime provides evidence.\n\n"
        f"ROLE CONTRACT:\n{role_prompt}\n\n"
        f"TRUSTED SPECIALIST CONTRACTS:\n{contracts_text}\n\n"
        f"AUTHORIZED TARGET PROJECT: {request.project_dir}\n"
        f"AUTHORIZED TASK:\n{task}"
    )


def _terminate_process(proc: subprocess.Popen) -> bool:
    if proc.poll() is not None:
        return True
    try:
        if sys.platform == "win32" and proc.pid:
            result = subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                creationflags=CREATE_NO_WINDOW,
            )
            return result.returncode == 0 or proc.poll() is not None
        proc.terminate()
        proc.wait(timeout=5)
        return True
    except Exception:
        try:
            proc.kill()
            return True
        except Exception:
            return False


def _event_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload.strip()
    if not isinstance(payload, dict):
        return ""
    for key in ("result", "output", "text", "content", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, dict):
            nested = _event_text(value)
            if nested:
                return nested
    part = payload.get("part")
    if isinstance(part, dict):
        return _event_text(part)
    payloads = payload.get("payloads")
    if isinstance(payloads, list):
        text = "\n".join(_event_text(item) for item in payloads if _event_text(item))
        if text:
            return text
    return ""


def _event_session(payload: Any) -> str:
    if not isinstance(payload, dict):
        return ""
    for key in ("session_id", "sessionID", "sessionId", "session_key", "sessionKey"):
        value = payload.get(key)
        if value:
            try:
                return _validate_opaque_session(str(value))
            except ValueError:
                pass
    for key in ("meta", "result", "session"):
        nested = _event_session(payload.get(key))
        if nested:
            return nested
    return ""


class ClaudeCodeAdapter:
    provider_id = "claude-code"
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="claude-cli-stream-json",
        structured_events=True,
        native_sessions=True,
        native_cancel=True,
        project_scoping="explicit-add-dir-with-isolated-control-cwd",
        agent_injection="sha-verified-dynamic-agent-bundle",
        isolation="configuration-isolated-not-os-sandboxed",
        enforced_read_only=True,
        enforced_tool_policy=True,
        studio_eligible=True,
        limitations=("Native Windows has no OS sandbox.",),
    )

    def available(self) -> bool:
        return bool(shutil.which(str(os.getenv("CLAUDE_CLI_PATH") or "claude")) or os.getenv("CLAUDE_CLI_PATH"))

    def validate_session_id(self, value: str | None) -> str:
        return claude_dispatcher.validate_session_id(value)

    def execute(self, request: AgentRunRequest, on_event=None) -> dict[str, Any]:
        result = claude_dispatcher.dispatch(
            request.task,
            project_dir=request.project_dir,
            on_event=on_event,
            extra_args=list(request.extra_args),
            owner_id=request.owner_id,
            permission_mode=request.permission_mode,
            agent_name=request.agent_name,
            agents_json=request.agents_json,
            allowlisted_skills=[],
            resume_session_id=request.resume_session_id,
            fork_session=request.fork_session,
            control_cwd=request.control_cwd,
        )
        return {**result, "provider_id": self.provider_id, "capabilities": self.capabilities.as_dict()}

    def stop(self, owner_id: str | None = None) -> bool:
        return claude_dispatcher.stop(owner_id=owner_id)


class SubprocessAdapter:
    provider_id = "subprocess"
    path_env = ""
    executable = ""
    capabilities = RuntimeCapabilities(
        provider_id="subprocess",
        transport="subprocess",
        structured_events=False,
        native_sessions=False,
        native_cancel=False,
        project_scoping="adapter-defined",
        agent_injection="trusted-prompt-envelope",
        isolation="not-os-sandboxed",
    )

    def __init__(self) -> None:
        self._run_lock = threading.Lock()
        self._state_lock = threading.RLock()
        self._proc: subprocess.Popen | None = None
        self._owner_id: str | None = None
        self._cancel_requested: set[str] = set()

    def path(self) -> str:
        return _runtime_path(self.path_env, self.executable)

    def available(self) -> bool:
        configured = str(os.getenv(self.path_env) or "").strip()
        return bool((configured and Path(configured).exists()) or shutil.which(self.executable))

    def validate_session_id(self, value: str | None) -> str:
        if not self.capabilities.native_sessions:
            raise ValueError(f"{self.provider_id} does not support resumable sessions through this adapter.")
        return _validate_opaque_session(value)

    def build_command(self, request: AgentRunRequest, prompt: str) -> list[str]:
        raise NotImplementedError

    def build_prompt(self, request: AgentRunRequest) -> str:
        return _trusted_prompt(request)

    def process_cwd(self, request: AgentRunRequest) -> str:
        return str(Path(request.control_cwd or request.project_dir).resolve())

    def child_environment(self, request: AgentRunRequest) -> dict[str, str]:
        return runtime_environment(self.provider_id, request.control_cwd)

    def inspect_terminal_payload(self, payload: dict[str, Any]) -> tuple[bool, str]:
        return True, ""

    def execute(self, request: AgentRunRequest, on_event=None) -> dict[str, Any]:
        if not self.available():
            return {
                "ok": False,
                "reason": "provider_unavailable",
                "message": f"{self.provider_id} is not installed or configured.",
                "provider_id": self.provider_id,
                "capabilities": self.capabilities.as_dict(),
            }
        if not self._run_lock.acquire(blocking=False):
            return {"ok": False, "reason": "busy", "message": f"{self.provider_id} is already running.", "provider_id": self.provider_id}
        proc = None
        completed = False
        owner = str(request.owner_id or "nexi-agent-runtime")
        events: list[dict[str, Any]] = []
        event_errors: list[dict[str, str]] = []
        raw_lines: list[str] = []
        plain_lines: list[str] = []
        raw_chars = 0
        result_text = ""
        session_id = ""
        timed_out = threading.Event()
        timer: threading.Timer | None = None
        try:
            with self._state_lock:
                self._owner_id = owner
                if owner in self._cancel_requested:
                    return {"ok": False, "reason": "cancelled", "message": f"{self.provider_id} run was cancelled before launch.", "provider_id": self.provider_id}
            prompt = self.build_prompt(request)
            command = self.build_command(request, prompt)
            cwd = self.process_cwd(request)
            if not Path(cwd).is_dir():
                return {"ok": False, "reason": "invalid_control_cwd", "message": "Agent control directory does not exist.", "provider_id": self.provider_id}
            popen_kwargs: dict[str, Any] = {}
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = CREATE_NO_WINDOW
            with self._state_lock:
                if owner in self._cancel_requested:
                    return {"ok": False, "reason": "cancelled", "message": f"{self.provider_id} run was cancelled before launch.", "provider_id": self.provider_id}
                proc = subprocess.Popen(
                    command,
                    cwd=cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    env=self.child_environment(request),
                    **popen_kwargs,
                )
                self._proc = proc
            timeout_seconds = _bounded_int("NEXI_AGENT_RUNTIME_TIMEOUT_SECONDS", 600, 1, 86400)
            def expire() -> None:
                timed_out.set()
                _terminate_process(proc)
            timer = threading.Timer(timeout_seconds, expire)
            timer.daemon = True
            timer.start()
            assert proc.stdout is not None
            for sequence, raw_line in enumerate(proc.stdout, start=1):
                line = raw_line.rstrip("\r\n")[:_bounded_int("NEXI_AGENT_RUNTIME_LINE_CHARS", 65536, 1000, 262144)]
                if not line:
                    continue
                raw_chars += len(line)
                if raw_chars > _bounded_int("NEXI_AGENT_RUNTIME_OUTPUT_CHARS", 2000000, 10000, 10000000):
                    _terminate_process(proc)
                    timed_out.set()
                    break
                raw_lines.append(line)
                try:
                    native = json.loads(line)
                except json.JSONDecodeError:
                    plain_lines.append(redact_sensitive(line))
                    native = {"type": "raw", "text": redact_sensitive(line)}
                native = sanitize_runtime_value(native)
                if not isinstance(native, dict):
                    native = {"type": "raw", "text": str(native)}
                text = _event_text(native)
                if text:
                    result_text = text
                candidate = _event_session(native)
                if candidate:
                    session_id = candidate
                event = AgentEvent(
                    provider_id=self.provider_id,
                    owner_id=owner,
                    sequence=sequence,
                    kind="message" if text else "progress",
                    native_type=str(native.get("type") or native.get("event") or "raw") if isinstance(native, dict) else "raw",
                    payload=native if isinstance(native, dict) else {"value": str(native)},
                ).as_dict()
                events.append(event)
                if len(events) > 500:
                    del events[: len(events) - 500]
                if on_event:
                    try:
                        on_event(event)
                    except Exception as exc:
                        event_errors.append({
                            "type": type(exc).__name__,
                            "message": str(sanitize_runtime_value(str(exc))),
                        })
                        if len(event_errors) > 20:
                            del event_errors[:-20]
            proc.wait()
            completed = True
            if timer:
                timer.cancel()
            parsed_terminal: dict[str, Any] = {}
            joined = "\n".join(raw_lines).strip()
            if joined:
                try:
                    parsed = json.loads(joined)
                    if isinstance(parsed, dict):
                        parsed_terminal = sanitize_runtime_value(parsed)
                        result_text = _event_text(parsed_terminal) or result_text
                        session_id = _event_session(parsed_terminal) or session_id
                except json.JSONDecodeError:
                    if plain_lines:
                        result_text = "\n".join(plain_lines)
            payload_ok, payload_reason = self.inspect_terminal_payload(sanitize_runtime_value(parsed_terminal))
            cancelled = owner in self._cancel_requested
            ok = proc.returncode == 0 and payload_ok and not timed_out.is_set() and not cancelled
            reason = "" if ok else "cancelled" if cancelled else "timeout_or_output_limit" if timed_out.is_set() else payload_reason or "provider_failed"
            return {
                "ok": ok,
                "reason": reason,
                "returncode": proc.returncode,
                "result": redact_sensitive(result_text),
                "message": "" if ok else redact_sensitive(payload_reason or result_text or f"{self.provider_id} failed: {reason}."),
                "events": events,
                "event_errors": event_errors,
                "session_id": session_id,
                "owner_id": owner,
                "project_dir": request.project_dir,
                "control_cwd": cwd,
                "provider_id": self.provider_id,
                "capabilities": self.capabilities.as_dict(),
            }
        except FileNotFoundError:
            return {"ok": False, "reason": "provider_unavailable", "message": f"{self.provider_id} executable was not found.", "provider_id": self.provider_id}
        except (OSError, ValueError) as exc:
            return {"ok": False, "reason": "provider_configuration_invalid", "message": redact_sensitive(str(exc)), "provider_id": self.provider_id}
        finally:
            if timer:
                timer.cancel()
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
            active_owner = self._owner_id
            if owner_id and active_owner not in {None, str(owner_id)}:
                return False
            requested_owner = str(owner_id or active_owner or "")
            if requested_owner:
                self._cancel_requested.add(requested_owner)
        if proc is None:
            return True
        return _terminate_process(proc)


class OpenCodeAdapter(SubprocessAdapter):
    provider_id = "opencode"
    path_env = "OPENCODE_CLI_PATH"
    executable = "opencode"
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="opencode-cli-json-events",
        structured_events=True,
        native_sessions=True,
        native_cancel=False,
        project_scoping="explicit-dir",
        agent_injection="isolated-inline-agent-config",
        isolation="project-and-user-config-disabled-not-os-sandboxed",
        enforced_read_only=True,
        enforced_tool_policy=True,
        studio_eligible=True,
        limitations=("CLI cancellation is forced process-tree termination.",),
    )

    def build_prompt(self, request: AgentRunRequest) -> str:
        # The selected SHA-verified role is already injected as an OpenCode agent.
        # Keep the user turn direct so the model executes instead of acknowledging
        # a second, duplicate role declaration.
        return (
            f"{str(request.task or '').strip()}\n\n"
            f"AUTHORIZED TARGET PROJECT: {request.project_dir}\n"
            "Nexi is the supervisor and independently verifies your work. Complete the task now; "
            "do not merely acknowledge the role or restate the request."
        )

    def _choose_model(self, request: AgentRunRequest) -> str:
        """The model this run will use. Explicit override wins; else the first HEALTHY
        model in the free-first per-task chain. Deterministic, so child_environment and
        execute() agree within a run."""
        override = str(os.getenv("NEXI_OPENCODE_MODEL") or "").strip()
        if override:
            return override
        from engine.agent_runtime.model_policy import select_model
        task = str(getattr(request, "task_kind", "") or "").strip() or None
        return select_model("opencode", task) or ""

    def execute(self, request: AgentRunRequest, on_event=None) -> dict[str, Any]:
        model = self._choose_model(request)
        try:
            result = super().execute(request, on_event=on_event)
            # Self-healing: a failed run benches the model so the NEXT run's chain skips
            # it and picks the next best; a success clears its failure count. Only count
            # model/provider failures, not user cancels or invalid-cwd config errors.
            if model:
                from engine.agent_runtime import model_health
                reason = str((result or {}).get("reason") or "")
                if result and result.get("ok"):
                    model_health.mark_ok("opencode", model)
                elif reason in {"provider_unavailable", "provider_configuration_invalid",
                                "error", "timeout", "timeout_or_output_limit", "model_error", "not_success"}:
                    model_health.mark_failed("opencode", model, reason)
            return result
        finally:
            if request.control_cwd:
                auth = Path(request.control_cwd) / "opencode-home" / ".local" / "share" / "opencode" / "auth.json"
                try:
                    auth.unlink(missing_ok=True)
                except OSError:
                    pass

    def child_environment(self, request: AgentRunRequest) -> dict[str, str]:
        if not request.control_cwd:
            raise ValueError("OpenCode requires an isolated control_cwd.")
        environment = super().child_environment(request)
        writable = request.permission_mode != "plan"
        agents: dict[str, Any] = {}
        if request.agents_json:
            definitions = json.loads(request.agents_json)
            roster = {str(name) for name in definitions}
            for name, definition in definitions.items():
                tools = set(definition.get("tools") or [])
                delegates = _agent_delegates(tools, roster)
                can_write = writable and "Write" in tools
                can_edit = writable and "Edit" in tools
                can_bash = writable and "Bash" in tools
                agents[name] = {
                    "description": str(definition.get("description") or name),
                    "prompt": str(definition.get("prompt") or ""),
                    "mode": "primary" if name == request.agent_name else "subagent",
                    "steps": max(1, min(100, int(definition.get("maxTurns") or 12))),
                    "tools": {
                        "read": True,
                        "grep": True,
                        "glob": True,
                        "list": "List" in tools,
                        "write": can_write,
                        "edit": can_edit,
                        "bash": can_bash,
                        "webfetch": "WebFetch" in tools,
                        "websearch": "WebSearch" in tools,
                        "skill": "Skill" in tools,
                        "task": bool(delegates),
                    },
                    "permission": {
                        "edit": "allow" if can_write or can_edit else "deny",
                        "bash": "allow" if can_bash else "deny",
                        "task": {"*": "deny", **{delegate: "allow" for delegate in delegates}},
                        "external_directory": "deny",
                    },
                }
        config = {
            "share": "disabled",
            "autoupdate": False,
            "plugin": [],
            "mcp": {},
            "instructions": [],
            "tools": {"*": False},
            "agent": agents,
            "default_agent": request.agent_name or ("build" if writable else "plan"),
            "permission": {"external_directory": "deny"},
        }
        # By default this config REPLACES the user's opencode setup, so their own agents,
        # MCP servers and plugins are invisible to a Studio run — Darsh saw only
        # "build" and "plan" despite having 240 agents installed. That isolation is
        # deliberate (an injected agent roster is what makes a stage's permissions
        # provable), but it can be opted out of when you want the full local toolbox.
        #
        # With NEXI_OPENCODE_USE_USER_CONFIG=1 we stop blanket-denying tools/plugins/MCP
        # and let opencode merge its own config. The NEXI-injected agents still win for
        # the keys they define, and external_directory stays denied so a run cannot
        # wander outside the authorized project.
        if str(os.getenv("NEXI_OPENCODE_USE_USER_CONFIG") or "").strip().lower() in {"1", "true", "yes", "on"}:
            config.pop("tools", None)      # let the user's tool config apply
            config.pop("plugin", None)     # keep installed plugins
            config.pop("mcp", None)        # keep configured MCP servers
            config.pop("instructions", None)
            print("[OPENCODE] using user config (agents/MCP/plugins enabled); "
                  "stage agent roster still injected", flush=True)
        # Model: explicit override wins; else the first HEALTHY model of the free-first
        # per-task chain (engine/agent_runtime/model_policy). opencode then switches
        # within its own pool. No hardcoded global default; a benched model is skipped.
        model = self._choose_model(request)
        if model:
            config["model"] = model
        environment["OPENCODE_CONFIG_CONTENT"] = json.dumps(config, separators=(",", ":"))
        return environment

    def build_command(self, request: AgentRunRequest, prompt: str) -> list[str]:
        command = [self.path(), "run", "--pure", "--auto", "--format", "json", "--dir", request.project_dir]
        if request.resume_session_id:
            command.extend(["--session", self.validate_session_id(request.resume_session_id)])
        if request.fork_session:
            command.append("--fork")
        if request.agent_name:
            command.extend(["--agent", request.agent_name])
        command.extend(request.extra_args)
        command.append(prompt)
        return command


class HermesAdapter(SubprocessAdapter):
    provider_id = "hermes"
    path_env = "HERMES_CLI_PATH"
    executable = "hermes"
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="hermes-cli-plain",
        structured_events=False,
        native_sessions=False,
        native_cancel=False,
        project_scoping="process-cwd",
        agent_injection="trusted-prompt-envelope-with-native-delegation-available",
        isolation="workspace-snapshot-guard-not-os-sandboxed",
        limitations=("Not eligible for governed Studio stages because CLI permissions are prompt-only.", "Use the Hermes Runs API adapter in a future release for native SSE, approvals, and stop."),
    )

    def process_cwd(self, request: AgentRunRequest) -> str:
        return str(Path(request.project_dir).resolve())

    def build_command(self, request: AgentRunRequest, prompt: str) -> list[str]:
        if request.resume_session_id or request.fork_session:
            raise ValueError("The Hermes CLI adapter cannot prove resumable-session semantics; start a fresh supervised attempt.")
        return [self.path(), "-z", prompt, *request.extra_args]


class OpenClawAdapter(SubprocessAdapter):
    provider_id = "openclaw"
    path_env = "OPENCLAW_CLI_PATH"
    executable = "openclaw"
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="openclaw-agent-cli-json",
        structured_events=False,
        native_sessions=True,
        native_cancel=False,
        project_scoping="absolute-target-in-trusted-prompt",
        agent_injection="trusted-prompt-envelope",
        isolation="agent-workspace-is-not-a-hard-sandbox",
        limitations=("Not eligible for governed Studio stages because CLI permissions are prompt-only.", "Cancellation is forced process-tree termination.", "The CLI may fall back to embedded execution unless explicitly accepted."),
    )

    def build_command(self, request: AgentRunRequest, prompt: str) -> list[str]:
        if request.fork_session:
            raise ValueError("The OpenClaw CLI adapter does not expose a verified fork-session operation.")
        agent_id = str(os.getenv("NEXI_OPENCLAW_AGENT_ID") or "main").strip()
        session_key = request.resume_session_id or f"nexi-{uuid.uuid4().hex}"
        command = [
            self.path(), "agent", "--agent", agent_id,
            "--session-key", self.validate_session_id(session_key),
            "--message", prompt,
            "--timeout", str(max(1, int(os.getenv("NEXI_AGENT_RUNTIME_TIMEOUT_SECONDS", "600")))),
            "--json",
        ]
        command.extend(request.extra_args)
        return command

    def inspect_terminal_payload(self, payload: dict[str, Any]) -> tuple[bool, str]:
        meta = payload.get("meta") if isinstance(payload, dict) else None
        if isinstance(meta, dict) and meta.get("transport") == "embedded" and str(os.getenv("NEXI_OPENCLAW_ALLOW_EMBEDDED_FALLBACK") or "").lower() not in {"1", "true", "yes"}:
            return False, "OpenClaw fell back to embedded execution; set NEXI_OPENCLAW_ALLOW_EMBEDDED_FALLBACK=1 to accept that degraded transport."
        return True, ""


class AntigravityAdapter(SubprocessAdapter):
    provider_id = "antigravity"
    path_env = "ANTIGRAVITY_PYTHON_PATH"
    executable = sys.executable
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="google-antigravity-python-sdk-worker",
        structured_events=True,
        native_sessions=False,
        native_cancel=False,
        project_scoping="worker-process-cwd",
        agent_injection="trusted-system-instructions",
        isolation="sdk-policy-plus-workspace-verification-not-os-sandboxed",
        enforced_read_only=True,
        limitations=("Not eligible for governed Studio stages until exact role tool policies are enforced.", "The adapter controls SDK-created agents, not an already-running Antigravity desktop IDE session."),
    )

    def available(self) -> bool:
        configured = str(os.getenv(self.path_env) or "").strip()
        return importlib.util.find_spec("google.antigravity") is not None or bool(configured and (Path(configured).exists() or shutil.which(configured)))

    def process_cwd(self, request: AgentRunRequest) -> str:
        return str(Path(request.project_dir).resolve())

    def build_command(self, request: AgentRunRequest, prompt: str) -> list[str]:
        if request.resume_session_id or request.fork_session:
            raise ValueError("The Antigravity worker adapter does not persist SDK conversations between processes.")
        python = str(os.getenv(self.path_env) or sys.executable)
        worker = str(Path(__file__).with_name("antigravity_worker.py").resolve())
        command = [python, worker, "--prompt", prompt]
        if request.permission_mode != "plan":
            command.append("--write")
        command.extend(request.extra_args)
        return command


class CustomCliAdapter(SubprocessAdapter):
    provider_id = "custom-cli"
    path_env = "NEXI_CUSTOM_AGENT_EXECUTABLE"
    executable = "custom-agent"
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="configured-no-shell-subprocess",
        structured_events=False,
        native_sessions=False,
        native_cancel=False,
        project_scoping="configured-command-template",
        agent_injection="trusted-prompt-envelope",
        isolation="adapter-owner-must-verify",
        limitations=("Not eligible for governed Studio stages unless operator-declared capabilities are conformance-tested.",),
    )

    def __init__(self) -> None:
        super().__init__()
        read_only = _env_bool("NEXI_CUSTOM_AGENT_ENFORCED_READ_ONLY")
        tool_policy = _env_bool("NEXI_CUSTOM_AGENT_ENFORCED_TOOL_POLICY")
        self.capabilities = replace(
            self.capabilities,
            structured_events=_env_bool("NEXI_CUSTOM_AGENT_STRUCTURED_EVENTS"),
            native_sessions=_env_bool("NEXI_CUSTOM_AGENT_NATIVE_SESSIONS"),
            native_cancel=_env_bool("NEXI_CUSTOM_AGENT_NATIVE_CANCEL"),
            enforced_read_only=read_only,
            enforced_tool_policy=tool_policy,
            studio_eligible=False,
        )

    def available(self) -> bool:
        try:
            template = json.loads(str(os.getenv("NEXI_CUSTOM_AGENT_COMMAND_JSON") or ""))
        except json.JSONDecodeError:
            return False
        if not isinstance(template, list) or not template or not isinstance(template[0], str):
            return False
        executable = template[0]
        return bool(Path(executable).exists() or shutil.which(executable))

    def build_command(self, request: AgentRunRequest, prompt: str) -> list[str]:
        try:
            template = json.loads(str(os.getenv("NEXI_CUSTOM_AGENT_COMMAND_JSON") or ""))
        except json.JSONDecodeError as exc:
            raise ValueError("NEXI_CUSTOM_AGENT_COMMAND_JSON must be a JSON string array.") from exc
        if not isinstance(template, list) or not template or any(not isinstance(item, str) for item in template):
            raise ValueError("NEXI_CUSTOM_AGENT_COMMAND_JSON must be a non-empty JSON string array.")
        replacements = {
            "{prompt}": prompt,
            "{project_dir}": request.project_dir,
            "{control_cwd}": str(request.control_cwd or ""),
            "{session_id}": str(request.resume_session_id or ""),
            "{agent}": str(request.agent_name or ""),
            "{owner_id}": request.owner_id,
        }
        command: list[str] = []
        for item in template:
            value = item
            for marker, replacement in replacements.items():
                value = value.replace(marker, replacement)
            command.append(value)
        command.extend(request.extra_args)
        return command

    def process_cwd(self, request: AgentRunRequest) -> str:
        mode = str(os.getenv("NEXI_CUSTOM_AGENT_CWD_MODE") or "control").strip().lower()
        if mode == "project":
            return str(Path(request.project_dir).resolve())
        return super().process_cwd(request)


BUILTIN_ADAPTERS = {
    "claude-code": ClaudeCodeAdapter,
    "opencode": OpenCodeAdapter,
    "hermes": HermesAdapter,
    "openclaw": OpenClawAdapter,
    "antigravity": AntigravityAdapter,
    "custom-cli": CustomCliAdapter,
}
