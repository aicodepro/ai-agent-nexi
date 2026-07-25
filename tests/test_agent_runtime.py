import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from engine.agent_runtime import registry, session
from engine.agent_runtime.adapters import AntigravityAdapter, CustomCliAdapter, HermesAdapter, OpenClawAdapter, OpenCodeAdapter, SubprocessAdapter
from engine.agent_runtime.contracts import AgentRunRequest, RuntimeCapabilities


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    registry.reset_for_tests()
    monkeypatch.delenv("NEXI_AGENT_RUNTIME_PROVIDER", raising=False)
    monkeypatch.delenv("NEXI_AGENT_RUNTIME_ENABLED", raising=False)
    yield
    registry.reset_for_tests()


def _request(tmp_path, **overrides):
    project = tmp_path / "project"
    control = tmp_path / "control"
    project.mkdir(exist_ok=True)
    control.mkdir(exist_ok=True)
    values = {
        "task": "build it",
        "project_dir": str(project.resolve()),
        "owner_id": "wf_test",
        "permission_mode": "plan",
        "agent_name": "business-analyst",
        "agents_json": json.dumps({
            "business-analyst": {
                "description": "Analyze requirements",
                "prompt": "Stay within scope.",
                "tools": ["Read", "Grep", "Glob"],
            },
            "developer-team": {
                "description": "Implement",
                "prompt": "Implement only authorized work.",
                "tools": ["Read", "Edit", "Write", "Bash"],
            },
        }),
        "control_cwd": str(control.resolve()),
    }
    values.update(overrides)
    return AgentRunRequest(**values)


def test_provider_selection_preserves_claude_compatibility(monkeypatch):
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    assert registry.selected_provider_id() == "claude-code"
    assert registry.runtime_enabled("claude-code") is True
    assert registry.canonical_provider_id("open-code") == "opencode"


def test_non_claude_provider_requires_generic_opt_in(monkeypatch):
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    assert registry.runtime_enabled("opencode") is False
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_ENABLED", "1")
    assert registry.runtime_enabled("opencode") is True


def test_runtime_status_tool_reports_selected_provider(monkeypatch):
    from engine.tool_registry import execute_tool

    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_ENABLED", "1")
    result = execute_tool("nexi_agent_runtime_status", {})
    assert result["success"] is True
    assert result["selected_provider"] == "opencode"


def test_opencode_command_and_config_are_isolated(monkeypatch, tmp_path):
    adapter = OpenCodeAdapter()
    request = _request(tmp_path)
    command = adapter.build_command(request, "trusted prompt")
    environment = adapter.child_environment(request)

    assert command[:6] == [adapter.path(), "run", "--pure", "--auto", "--format", "json"]
    assert command[command.index("--dir") + 1] == request.project_dir
    assert command[command.index("--agent") + 1] == "business-analyst"
    assert environment["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"
    assert environment["OPENCODE_DISABLE_EXTERNAL_SKILLS"] == "1"
    assert environment["OPENCODE_DISABLE_CLAUDE_CODE"] == "1"
    assert Path(environment["XDG_CONFIG_HOME"]).is_dir()
    config = json.loads(environment["OPENCODE_CONFIG_CONTENT"])
    assert config["plugin"] == [] and config["mcp"] == {}
    assert config["agent"]["business-analyst"]["tools"]["write"] is False
    assert config["agent"]["developer-team"]["mode"] == "subagent"
    assert config["agent"]["business-analyst"]["steps"] == 12
    assert config["agent"]["business-analyst"]["tools"]["websearch"] is False
    assert config["agent"]["business-analyst"]["permission"]["task"] == {"*": "deny"}


def test_opencode_enforces_exact_delegation_roster(tmp_path):
    definitions = {
        "lead": {
            "description": "Lead",
            "prompt": "Delegate narrowly.",
            "tools": ["Read", "Agent(worker)"],
            "maxTurns": 4,
        },
        "worker": {
            "description": "Worker",
            "prompt": "Work narrowly.",
            "tools": ["Read"],
            "maxTurns": 3,
        },
    }
    adapter = OpenCodeAdapter()
    request = _request(tmp_path, agent_name="lead", agents_json=json.dumps(definitions))
    config = json.loads(adapter.child_environment(request)["OPENCODE_CONFIG_CONTENT"])
    assert config["agent"]["lead"]["permission"]["task"] == {"*": "deny", "worker": "allow"}
    assert config["agent"]["lead"]["tools"]["list"] is False

    definitions["lead"]["tools"] = ["Agent(untrusted)"]
    with pytest.raises(ValueError):
        adapter.child_environment(_request(tmp_path, agent_name="lead", agents_json=json.dumps(definitions)))


def test_opencode_rejects_missing_isolated_control_directory(tmp_path):
    adapter = OpenCodeAdapter()
    with pytest.raises(ValueError):
        adapter.child_environment(_request(tmp_path, control_cwd=None))


def test_hermes_cli_uses_project_cwd_and_refuses_fake_resume(tmp_path):
    adapter = HermesAdapter()
    request = _request(tmp_path)
    assert adapter.process_cwd(request) == request.project_dir
    assert adapter.build_command(request, "trusted prompt") == [adapter.path(), "-z", "trusted prompt"]
    with pytest.raises(ValueError):
        adapter.build_command(_request(tmp_path, resume_session_id="session-1"), "trusted prompt")


def test_openclaw_requires_explicit_embedded_fallback_opt_in(monkeypatch):
    adapter = OpenClawAdapter()
    allowed, reason = adapter.inspect_terminal_payload({"meta": {"transport": "embedded", "fallbackFrom": "gateway"}})
    assert allowed is False and "embedded" in reason.lower()
    monkeypatch.setenv("NEXI_OPENCLAW_ALLOW_EMBEDDED_FALLBACK", "1")
    assert adapter.inspect_terminal_payload({"meta": {"transport": "embedded"}}) == (True, "")


def test_openclaw_fresh_attempts_get_new_session_keys(tmp_path):
    adapter = OpenClawAdapter()
    first = adapter.build_command(_request(tmp_path), "one")
    second = adapter.build_command(_request(tmp_path), "two")
    assert first[first.index("--session-key") + 1] != second[second.index("--session-key") + 1]
    assert adapter.capabilities.native_cancel is False
    with pytest.raises(ValueError):
        adapter.build_command(_request(tmp_path, fork_session=True), "fork")


def test_antigravity_uses_sdk_worker_and_write_capability(tmp_path):
    adapter = AntigravityAdapter()
    command = adapter.build_command(_request(tmp_path, permission_mode="acceptEdits"), "trusted prompt")
    assert command[1].endswith("antigravity_worker.py")
    assert command[2:4] == ["--prompt", "trusted prompt"]
    assert "--write" in command
    assert registry.canonical_provider_id("anti-gravity") == "antigravity"


def test_custom_cli_uses_json_argv_without_shell(monkeypatch, tmp_path):
    executable = __import__("sys").executable
    monkeypatch.setenv(
        "NEXI_CUSTOM_AGENT_COMMAND_JSON",
        json.dumps([executable, "--project", "{project_dir}", "--prompt", "{prompt}", "--session", "{session_id}"]),
    )
    adapter = CustomCliAdapter()
    request = _request(tmp_path)
    command = adapter.build_command(request, "trusted prompt")
    assert command == [executable, "--project", request.project_dir, "--prompt", "trusted prompt", "--session", ""]
    assert adapter.available() is True
    assert adapter.capabilities.native_sessions is False
    assert adapter.capabilities.studio_eligible is False


def test_custom_cli_capabilities_require_explicit_complete_declaration(monkeypatch):
    monkeypatch.setenv("NEXI_CUSTOM_AGENT_STRUCTURED_EVENTS", "1")
    monkeypatch.setenv("NEXI_CUSTOM_AGENT_NATIVE_SESSIONS", "1")
    monkeypatch.setenv("NEXI_CUSTOM_AGENT_ENFORCED_READ_ONLY", "1")
    monkeypatch.setenv("NEXI_CUSTOM_AGENT_ENFORCED_TOOL_POLICY", "1")
    monkeypatch.setenv("NEXI_CUSTOM_AGENT_STUDIO_ELIGIBLE", "1")
    capabilities = CustomCliAdapter().capabilities
    assert capabilities.structured_events is True
    assert capabilities.native_sessions is True
    assert capabilities.studio_eligible is False


class _PythonOutputAdapter(SubprocessAdapter):
    provider_id = "python-output-test"
    executable = sys.executable
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="test",
        structured_events=True,
        native_sessions=False,
        native_cancel=False,
        project_scoping="test",
        agent_injection="test",
        isolation="test",
    )

    def available(self):
        return True

    def build_command(self, request, prompt):
        del request, prompt
        source = "import json; print(json.dumps({'type':'message','text':'first','api_key':'secret-value'})); print('second'); print('third')"
        return [sys.executable, "-c", source]


def test_subprocess_multiline_output_and_structured_secrets_are_safe(tmp_path):
    events = []
    result = _PythonOutputAdapter().execute(_request(tmp_path), on_event=events.append)
    assert result["ok"] is True
    assert result["result"] == "second\nthird"
    assert events[0]["payload"]["api_key"] == "[REDACTED]"
    assert "secret-value" not in json.dumps(result)


def test_subprocess_event_callback_failure_is_observable(tmp_path):
    def broken_callback(_event):
        raise RuntimeError("event sink offline")

    result = _PythonOutputAdapter().execute(_request(tmp_path), on_event=broken_callback)

    assert result["ok"] is True
    assert result["event_errors"][0]["type"] == "RuntimeError"
    assert "event sink offline" in result["event_errors"][0]["message"]


def test_opencode_timeout_or_output_limit_benches_model(monkeypatch, tmp_path):
    from engine.agent_runtime import model_health

    adapter = OpenCodeAdapter()
    monkeypatch.setattr(adapter, "_choose_model", lambda _request: "provider/slow-model")
    monkeypatch.setattr(
        SubprocessAdapter,
        "execute",
        lambda *_a, **_k: {"ok": False, "reason": "timeout_or_output_limit"},
    )
    monkeypatch.setenv("NEXI_MODEL_FAIL_THRESHOLD", "1")
    model_health.reset("opencode")

    adapter.execute(_request(tmp_path))

    assert "provider/slow-model" not in model_health.healthy("opencode", ["provider/slow-model"])
    model_health.reset("opencode")


class _BlockingLaunchAdapter(_PythonOutputAdapter):
    def __init__(self):
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def build_command(self, request, prompt):
        self.started.set()
        self.release.wait(timeout=5)
        return super().build_command(request, prompt)


def test_cancellation_before_spawn_is_latched(tmp_path):
    adapter = _BlockingLaunchAdapter()
    request = _request(tmp_path, owner_id="cancel-owner")
    results = []
    worker = threading.Thread(target=lambda: results.append(adapter.execute(request)))
    worker.start()
    assert adapter.started.wait(timeout=2)
    assert adapter.stop(owner_id="cancel-owner") is True
    adapter.release.set()
    worker.join(timeout=5)
    assert results and results[0]["reason"] == "cancelled"


def test_cancellation_waits_for_process_handoff(monkeypatch, tmp_path):
    adapter = _PythonOutputAdapter()
    request = _request(tmp_path, owner_id="handoff-owner")
    real_popen = subprocess.Popen
    entered = threading.Event()
    release = threading.Event()

    def delayed_popen(*args, **kwargs):
        entered.set()
        release.wait(timeout=5)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr("engine.agent_runtime.adapters.subprocess.Popen", delayed_popen)
    results = []
    worker = threading.Thread(target=lambda: results.append(adapter.execute(request)))
    worker.start()
    assert entered.wait(timeout=2)
    stopped = []
    stopper = threading.Thread(target=lambda: stopped.append(adapter.stop(owner_id="handoff-owner")))
    stopper.start()
    time.sleep(0.05)
    assert stopper.is_alive()
    release.set()
    stopper.join(timeout=5)
    worker.join(timeout=5)
    assert stopped == [True]
    assert results and results[0]["reason"] == "cancelled"


def test_eel_start_endpoint_is_fail_closed():
    exposed = {}
    class FakeEel:
        def expose(self, fn):
            exposed[fn.__name__] = fn
            return fn
    session.register_eel(FakeEel())
    result = exposed["agent_runtime_start"]("write files", "C:\\")
    assert result["ok"] is False
    assert result["reason"] == "studio_authorization_required"


def test_ui_loader_does_not_register_legacy_claude_execution_bridge(monkeypatch):
    from engine import ui_loader

    exposed = {}
    class FakeEel:
        def init(self, _directory):
            return None
        def expose(self, fn):
            exposed[fn.__name__] = fn
            return fn

    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    monkeypatch.delenv("NEXI_AGENT_RUNTIME_ENABLED", raising=False)
    ui_loader.init_eel_ui(FakeEel())
    assert "agent_runtime_start" in exposed
    assert "claude_code_start" not in exposed


class _FakeAdapter:
    provider_id = "fake-runtime"
    capabilities = RuntimeCapabilities(
        provider_id=provider_id,
        transport="test",
        structured_events=True,
        native_sessions=True,
        native_cancel=True,
        project_scoping="test",
        agent_injection="test",
        isolation="test",
    )

    def __init__(self):
        self.requests = []
        self.stopped = []

    def available(self):
        return True

    def validate_session_id(self, value):
        return str(value)

    def execute(self, request, on_event=None):
        self.requests.append(request)
        if on_event:
            on_event({"provider_id": self.provider_id, "kind": "started"})
        return {
            "ok": True,
            "reason": "",
            "result": "implemented",
            "session_id": "session-1",
            "provider_id": self.provider_id,
            "events": [],
        }

    def stop(self, owner_id=None):
        self.stopped.append(owner_id)
        return True


def test_supervised_session_uses_registered_provider(monkeypatch, tmp_path):
    adapter = _FakeAdapter()
    registry.register_adapter(adapter)
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_ENABLED", "1")
    result = session.run_task(
        "implement",
        project_dir=str(tmp_path),
        provider_id=adapter.provider_id,
        owner_id="owner-1",
        verify=False,
    )
    assert result["ok"] is True
    assert result["provider_id"] == adapter.provider_id
    assert result["dispatch"]["session_id"] == "session-1"
    assert adapter.requests[0].project_dir == str(Path(tmp_path).resolve())
