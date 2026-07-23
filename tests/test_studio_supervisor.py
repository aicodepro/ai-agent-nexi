import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from engine import agency
from engine import intent_taxonomy as tax
from engine.agency import workflow_engine as we
from engine.claude_code import verifier
from engine.groq_intent_router_v2 import _deterministic_router, route_intent_v2
from engine.studio import artifacts, governance, supervisor
from engine.studio.commands import is_explicit_studio_command, issue_authorization, parse_studio_command
from engine.tool_registry import execute_tool, get_tool, router_tool_manifest


STUDIO_TOOLS = {
    "nexi_start_studio_build",
    "nexi_studio_status",
    "nexi_cancel_studio_build",
    "nexi_continue_studio_build",
}


def _start_slots(command: str, **extra):
    return {"command": command, "_studio_auth": issue_authorization(command, "start"), **extra}


def _continue_slots(answer: str, **extra):
    raw_text = f"studio continue: {answer}"
    return {"answer": answer, "raw_text": raw_text, "_studio_auth": issue_authorization(raw_text, "continue"), **extra}


def _wait_for(run_id: str, statuses: set[str], timeout: float = 60.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = we.get_run(run_id)
        if run and run.status in statuses:
            return run
        time.sleep(0.01)
    return we.get_run(run_id)


CAPABILITIES = """## Assumptions
- Use the smallest reversible local default.
## Capabilities
- Skills considered: repository analysis
- Skills used: repository analysis
- MCP servers used: none
- Tools used: Read, Grep
- Reason for selection: stage evidence
BLOCKING_QUESTIONS:
- none"""

REQUIREMENTS = f"""# Requirements
## Goal
Build the exact authorized product.
## In scope
Core local flow.
## Constraints
No release mutation.
## Acceptance candidates
The core flow is observable.
{CAPABILITIES}"""

RESEARCH = f"""# Research
## Evidence
- Existing repository patterns were inspected.
## Risks
- Scope drift.
{CAPABILITIES}"""

ARCHITECTURE = f"""# Architecture
## Decision
Use the smallest compatible local design.
## Interfaces and failure modes
- Preserve existing boundaries and fail closed.
{CAPABILITIES}"""

PLAN = f"""# Sprint Plan
## Ordered phases
1. Implement.
2. Verify.
## Acceptance criteria
- AC-1: Core flow works locally.
## Test plan
- Run the focused automated suite.
{CAPABILITIES}"""

QA = f"""# QA Verification
## Acceptance results
- [PASS] AC-1: Core flow works with independent objective evidence {{QA_TOKEN}}.
## Final verdict
PASS
{CAPABILITIES}"""

STRATEGY = f"""# Project Strategy
## Charter
Build the smallest authorized local product.
## Objectives
- Deliver the observable core flow.
## Non-goals
- No external release or deployment.
## Risks
- Scope drift.
{CAPABILITIES}"""

SECURITY = f"""# Security Review
## Findings
- [NONE] No Critical or High finding.
## Final verdict
PASS workspace_sha256={{WORKSPACE_DIGEST}} agent_sha256={{AGENT_SHA256}}
{CAPABILITIES}"""


@pytest.fixture(autouse=True)
def _studio_environment(monkeypatch, tmp_path):
    we.clear()
    monkeypatch.setattr(we, "_STORE", tmp_path / "workflow_runs.jsonl")
    # The LLM safety gate calls the Groq safety model; offline (no GROQ_API_KEY) it fails
    # CLOSED and blocks the studio tools before any stage runs. Disable it here so these
    # tests exercise the studio authorization/gating logic they exist to cover.
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")
    monkeypatch.setenv("NEXI_STUDIO_ENABLED", "1")
    monkeypatch.setenv("NEXI_CLAUDE_CODE_ENABLED", "1")
    monkeypatch.setenv("CLAUDE_CLI_PATH", sys.executable)
    monkeypatch.setenv("OPENCODE_CLI_PATH", sys.executable)
    monkeypatch.delenv("NEXI_AGENT_RUNTIME_PROVIDER", raising=False)
    monkeypatch.delenv("NEXI_AGENT_RUNTIME_ENABLED", raising=False)
    monkeypatch.setenv("NEXI_STUDIO_ALLOW_HOST_EXECUTION", "1")
    monkeypatch.setenv("NEXI_STUDIO_PROJECTS_DIR", str(tmp_path / "projects"))
    monkeypatch.setenv("NEXI_STUDIO_DIR", str(tmp_path / "artifacts"))
    monkeypatch.setenv("NEXI_STUDIO_PROJECTS_DATA_DIR", str(tmp_path / "project-memory"))
    supervisor.set_dependencies(None)
    yield
    supervisor.set_dependencies(None)
    we.clear()


def _successful_dependencies(calls, *, outputs=None, requirements_sequence=None, test_results=None):
    outputs = dict(outputs or {})
    requirement_values = iter(requirements_sequence or [])
    test_values = iter(test_results or [])

    def run_task(prompt, project_dir=None, **kwargs):
        stage_match = __import__("re").search(r"NEXI STUDIO STAGE: ([a-z_]+)", prompt)
        internal_match = __import__("re").search(r"NEXI STUDIO INTERNAL SUBSTAGE: ([a-z_]+)", prompt)
        stage = stage_match.group(1) if stage_match else internal_match.group(1) if internal_match else "implementation"
        calls.append({"stage": stage, "prompt": prompt, "project_dir": project_dir, **kwargs})
        if stage == "implementation":
            Path(project_dir, "product.txt").write_text("built", encoding="utf-8")
            return {
                "ok": True,
                "on_track": True,
                "message": "implemented and verified",
                "dispatch": {
                    "ok": True,
                    "result": "Implemented the authorized product.",
                    "session_id": kwargs.get("resume_session_id") or str(uuid.uuid5(uuid.NAMESPACE_URL, "nexi-studio-test:implementation")),
                },
                "verify": {"checks": {
                    "made_changes": True,
                    "tests_ran": True,
                    "tests_passed": True,
                    "tests_output": "1 passed",
                    "diff_stat": "1 added",
                    "workspace_change": {"changed": True, "truncated": False},
                    "test_workspace_change": {"changed": False, "truncated": False},
                }},
            }
        defaults = {
            "project_strategy": STRATEGY,
            "requirements": REQUIREMENTS,
            "research": RESEARCH,
            "architecture": ARCHITECTURE,
            "sprint_plan": PLAN,
            "qa": QA,
            "security_review": SECURITY,
        }
        if stage == "requirements" and requirements_sequence:
            try:
                text = next(requirement_values)
            except StopIteration:
                text = REQUIREMENTS
        else:
            text = outputs.get(stage, defaults.get(stage, f"# {stage.title()}\nRead-only evidence."))
        token_match = __import__("re").search(r"G7-QA-EVIDENCE-[a-f0-9]{64}", prompt)
        workspace_match = __import__("re").search(r"PASS workspace_sha256=([a-f0-9]{64}) agent_sha256=([a-f0-9]{64})", prompt)
        text = text.replace("{QA_TOKEN}", token_match.group(0) if token_match else "MISSING_QA_TOKEN")
        if workspace_match:
            text = text.replace("{WORKSPACE_DIGEST}", workspace_match.group(1)).replace("{AGENT_SHA256}", workspace_match.group(2))
        session_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"nexi-studio-test:{stage}"))
        return {
            "ok": True,
            "on_track": True,
            "dispatch": {"ok": True, "result": text, "session_id": kwargs.get("resume_session_id") or session_id},
            "verify": None,
            "message": "done",
        }

    def run_tests(*_args, **_kwargs):
        try:
            return next(test_values)
        except StopIteration:
            return {"ran": True, "passed": True, "output": "2 passed"}

    return supervisor.StudioDependencies(
        run_task=run_task,
        stop_task=lambda **_kwargs: True,
        workspace_snapshot=verifier.workspace_snapshot,
        compare_workspace=verifier.compare_workspace,
        run_tests=run_tests,
    )


def _start_success(calls, command="let's build a local coffee app", **slots):
    supervisor.set_dependencies(_successful_dependencies(calls))
    started = execute_tool("nexi_start_studio_build", _start_slots(command, **slots))
    assert started["success"] is True
    return started, _wait_for(started["run_id"], {"completed", "failed", "waiting_for_input"})


def test_exact_command_grammar_and_route_protections(monkeypatch):
    assert parse_studio_command("let's build a coffee landing page")["trigger"] == "lets_build"
    assert parse_studio_command("build a tool") is None
    assert parse_studio_command("studio model: build a tool") is None
    assert parse_studio_command("studio moderator: build a tool") is None
    assert parse_studio_command("studio mode selection advice") is None
    assert parse_studio_command("exotic mode selection advice") is None
    assert parse_studio_command("studio mode build a tool") is None
    assert parse_studio_command("exotic mode build a tool") is None
    assert parse_studio_command("studio mode")["goal"] == ""
    assert parse_studio_command("exotic mode:")["goal"] == ""
    assert parse_studio_command("let's builder a tool") is None
    assert is_explicit_studio_command("studio continuewhatever") is False
    assert parse_studio_command("Nexi, start building a coffee landing page")["trigger"] == "start_building"
    assert parse_studio_command("Hey Nexi, start building a coffee landing page")["trigger"] == "start_building"
    assert parse_studio_command("start building a coffee landing page") is None
    assert route_intent_v2("start building a coffee landing page")["intent"] != "nexi_start_studio_build"
    assert is_explicit_studio_command("Nexi, studio continue: use Stripe") is True
    explicit = _deterministic_router("let's build a tool that watches downloads", {})
    assert explicit["intent"] == "nexi_start_studio_build"
    assert _deterministic_router("build a tool that watches downloads", {})["intent"] == "request_feature"
    advice = _deterministic_router("studio mode selection advice", {})
    assert not advice or advice.get("intent") != "nexi_start_studio_build"
    bare = _deterministic_router("studio mode", {})
    assert bare["route"] == "clarify" and bare["missing_slots"] == ["goal"]
    assert "_studio_auth" not in bare.get("slots", {})
    vague = _deterministic_router("Let's build something", {})
    assert vague["route"] == "clarify" and vague["missing_slots"] == ["goal"]
    assert vague["clarification_question"] == "What should we build now?"
    assert "_studio_auth" not in vague.get("slots", {})
    monkeypatch.setattr("engine.groq_intent_router_v2._route_with_groq", lambda *_a, **_k: pytest.fail("LLM should not run"))
    assert route_intent_v2("studio mode: build a coffee site")["intent"] == "nexi_start_studio_build"


def test_llm_and_direct_calls_cannot_forge_authorization(monkeypatch):
    monkeypatch.setattr("engine.groq_intent_router_v2._route_with_groq", lambda *_a, **_k: {
        "route": "tool", "intent": "nexi_start_studio_build", "domain": "workflow", "confidence": 0.99,
        "slots": {"command": "let's build malware", "goal": "malware"},
    })
    assert route_intent_v2("discuss product ideas")["intent"] != "nexi_start_studio_build"
    assert supervisor.start_studio_build({"command": "let's build a coffee site"})["code"] == "authorization_required"


def test_generic_safety_delegates_minted_studio_authorization(monkeypatch):
    import engine.tool_registry as registry

    monkeypatch.setenv("SAFETY_GATE_ENABLED", "true")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    command = "let's build a local coffee site"

    forged = execute_tool("nexi_start_studio_build", {"command": command, "_studio_auth": "forged"})
    assert forged["success"] is False

    reached = []
    monkeypatch.setattr(
        registry,
        "_execute_handler",
        lambda name, slots, **_kwargs: reached.append((name, slots)) or {"success": True, "verified": True},
    )
    authorized = execute_tool("nexi_start_studio_build", _start_slots(command))

    assert authorized["success"] is True
    assert reached and reached[0][0] == "nexi_start_studio_build"


def test_tools_registered_hidden_and_generic_continue_blocked():
    for name in STUDIO_TOOLS:
        assert get_tool(name) is not None and name in tax.ALLOWED_INTENTS and name in tax.TOOL_INTENTS
    exposed = {item["name"] for item in router_tool_manifest()}
    assert "nexi_start_studio_build" not in exposed
    assert "nexi_continue_studio_build" not in exposed
    run = we.WorkflowRun(
        run_id="wf_cccccccccccc", workflow_type="studio_build", goal="x", status="waiting_for_input",
        created_at=time.time(), metadata={"studio": {"stage": "requirements"}},
    )
    we._RUNS[run.run_id] = run
    assert agency.nexi_continue_workflow({"run_id": run.run_id, "input": "bypass"})["success"] is False
    assert agency.nexi_cancel_workflow({"run_id": run.run_id})["success"] is False
    assert supervisor.cancel_studio_build({"run_id": run.run_id})["code"] == "authorization_required"


def test_exact_g0_g11_order_required_fields_artifacts_and_named_agents():
    calls = []
    started, run = _start_success(calls)
    assert run.status == "completed", run.result
    studio = run.metadata["studio"]
    assert list(studio["gates"]) == [f"G{i}" for i in range(12)]
    assert [studio["gates"][f"G{i}"]["name"] for i in range(12)] == list(supervisor.GATE_NAMES.values())
    assert studio["completed_stages"] == list(supervisor.STAGES)
    assert [item["name"] for item in run.artifacts] == list(supervisor.STAGE_FILES.values())
    assert Path(artifacts.run_dir(run.run_id), "run.json").is_file()
    assert Path(studio["artifact_root"]) == artifacts.run_dir(run.run_id).resolve()
    required = {
        "run_id", "project_id", "authorization_id", "repository", "working_branch", "created_at",
        "current_stage", "stage", "status", "request_class", "gates", "stage_attempts", "assumptions",
        "pending_questions", "approvals", "failed_checks", "retry_count", "last_verified_commit_sha",
        "artifacts", "release_claims", "deployment_claims", "current_task", "runtime_provider", "runtime_capabilities",
        "agent_session_id", "agent_sessions", "claude_session_id", "claude_sessions", "strategy", "project_memory", "qa_objective_evidence", "manager_decisions",
    }
    assert required <= set(studio)
    assert studio["release_claims"]["highest_proven_state"] == "LOCAL_VERIFIED"
    assert studio["release_claims"]["commit_sha"] is None
    assert studio["gates"]["G10"]["status"] == "LOCAL_VERIFIED"
    assert studio["authorization"]["principal"]
    assert studio["authorization"]["source"] == "unknown"
    assert studio["authorization"]["identity_assurance"] == "local_os_principal_only_not_speaker_verification"
    assert studio["release_claims"]["pull_request"] == "NOT_CONFIGURED"
    assert studio["deployment_claims"]["state"] == "NOT_CONFIGURED"
    assert [call["agent_name"] for call in calls] == [
        "project-strategist", "business-analyst", "research-analyst", "solution-architect", "product-manager", "developer-team",
        "test-engineer", "qa-verifier", "security-reviewer", "integration-verifier", "release-manager", "knowledge-curator",
    ]
    assert all("agents_json" in call and "--safe-mode" not in call.get("extra_args", []) for call in calls)
    assert all("resume_session_id" not in call for call in calls)
    assert all("permissionMode" in definition and "maxTurns" in definition for call in calls for definition in json.loads(call["agents_json"]).values())
    capability_keys = {"skills_considered", "skills_used", "mcp_servers_used", "tools_used", "reason_for_selection"}
    provenance_keys = {"run_id", "authorization_id", "gate", "stage", "attempt", "repository", "branch", "head", "agent_definition_hashes", "input_artifact_hashes", "workspace_digest"}
    assert all(capability_keys <= set(item) for item in run.artifacts)
    assert all(item["capability_evidence"] == "agent_self_reported" for item in run.artifacts)
    assert all(provenance_keys <= set(item["provenance"]) for item in run.artifacts)
    assert "project-profile.md" in calls[1]["prompt"]
    assert "# Project Strategy" in calls[1]["prompt"]
    assert all("# Project Strategy" not in call["prompt"] for call in calls[2:])
    assert studio["claude_session_id"]
    assert studio["agent_session_id"] == studio["claude_session_id"]
    assert studio["agent_sessions"] == studio["claude_sessions"]
    assert studio["runtime_provider"] == "claude-code"
    assert studio["current_task"]["stage"] == "closeout"
    assert studio["current_task"]["status"] == "completed"
    assert all(record["agent"] and record["session_id"] and record["timestamp"] for record in studio["claude_sessions"].values())
    assert all(record["status"] == "completed" for record in studio["claude_sessions"].values())
    assert all(call["provider_id"] == "claude-code" for call in calls)
    assert studio["qa_objective_evidence"]["evidence_token"].startswith("G7-QA-EVIDENCE-")
    assert studio["qa_coverage"]["qa_evidence_token"] == studio["qa_objective_evidence"]["evidence_token"]
    state_before_status = json.dumps(run.to_dict(), sort_keys=True)
    status = supervisor.studio_status({"run_id": started["run_id"]})
    assert required - {"artifacts"} <= set(status)
    assert json.dumps(run.to_dict(), sort_keys=True) == state_before_status


def test_studio_persists_selected_non_claude_runtime(monkeypatch):
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "opencode")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_ENABLED", "1")
    calls = []
    _, run = _start_success(calls, "studio mode: build with opencode")
    assert run.status == "completed", run.result
    studio = run.metadata["studio"]
    assert studio["runtime_provider"] == "opencode"
    assert studio["runtime_capabilities"]["transport"] == "opencode-cli-json-events"
    assert all(call["provider_id"] == "opencode" for call in calls)
    assert all(record["provider_id"] == "opencode" for record in studio["agent_sessions"].values())


def test_studio_rejects_unavailable_or_policy_ineligible_provider(monkeypatch):
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "antigravity")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_ENABLED", "1")
    monkeypatch.setattr(
        supervisor.runtime_registry,
        "provider_status",
        lambda _provider: {"available": False, "capabilities": {"studio_eligible": False}},
    )
    unavailable = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: build with unavailable runtime"),
    )
    assert unavailable["success"] is False
    assert "not installed or configured" in unavailable["message"]

    monkeypatch.setattr(
        supervisor.runtime_registry,
        "provider_status",
        lambda _provider: {"available": True, "capabilities": {"studio_eligible": False}},
    )
    ineligible = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: build with prompt only runtime"),
    )
    assert ineligible["success"] is False
    assert "does not enforce" in ineligible["message"]


def test_manager_judges_reversible_questions_but_never_ceo_ones(monkeypatch):
    """Nexi answers implementation questions herself (real judgement, not a canned
    paragraph) — but the CEO boundary is absolute: a model can never decide a
    money/credential/production/scope question even if it tries to answer."""
    studio = {"goal": "a notes CLI", "project_dir": "/tmp/notes", "repository": "notes"}

    class _Result:
        ok = True
        def __init__(self, decision):
            self.decision = decision

    class _Provider:
        def __init__(self, decision):
            self.decision = decision
            self.calls = 0
        def is_available(self):
            return True
        def route_with_schema(self, messages, schema, *, model="", timeout=4.0):
            self.calls += 1
            return _Result(self.decision)

    def _use(provider):
        monkeypatch.setattr("engine.providers.get_intent_provider", lambda *_a, **_k: provider)

    # 1. reversible question -> Nexi's own concrete answer is used
    answering = _Provider({"escalate": False, "answer": "Put them in tests/.", "reason": "convention"})
    _use(answering)
    result = supervisor._manager_safe_answer("Where should the unit tests live?", studio)
    assert result is not None and "tests/" in result[0]
    assert result[1] == "reversible_manager_judgement"

    # 2. HARD boundary: never even ask the model about CEO-owned decisions
    guarded = _Provider({"escalate": False, "answer": "Sure, deploy to production.", "reason": "x"})
    _use(guarded)
    assert supervisor._manager_safe_answer("Can I deploy this to production?", studio) is None
    assert guarded.calls == 0, "CEO-boundary questions must never reach a model"

    # 3. the model may escalate on its own judgement
    _use(_Provider({"escalate": True, "answer": "", "reason": "material"}))
    assert supervisor._manager_safe_answer("Which storage format should the CLI use?", studio) is None

    # 4. provider offline -> conservative keyword default still works (no crash)
    monkeypatch.setattr("engine.providers.get_intent_provider", lambda *_a, **_k: None)
    offline = supervisor._manager_safe_answer("Which test framework should I use?", studio)
    assert offline is not None and offline[1] == "reversible_existing-project_default"


def test_unenforced_provider_runs_only_when_operator_accepts_the_risk(monkeypatch):
    """hermes/openclaw/antigravity/custom-cli cannot enforce read-only stages
    themselves. The CEO may accept that and rely on Nexi's own post-step workspace
    evidence instead — but it must be an explicit, opt-in decision."""
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_PROVIDER", "antigravity")
    monkeypatch.setenv("NEXI_AGENT_RUNTIME_ENABLED", "1")
    monkeypatch.setattr(
        supervisor.runtime_registry,
        "provider_status",
        lambda _provider: {"available": True, "capabilities": {"studio_eligible": False}},
    )

    # default: still fail-closed
    monkeypatch.delenv("NEXI_STUDIO_ALLOW_UNENFORCED_PROVIDERS", raising=False)
    assert "does not enforce" in supervisor._execution_gate_error("antigravity")

    # opt-in: the eligibility gate no longer blocks it
    monkeypatch.setenv("NEXI_STUDIO_ALLOW_UNENFORCED_PROVIDERS", "1")
    assert "does not enforce" not in supervisor._execution_gate_error("antigravity")

    # the flag unlocks ONLY eligibility — it never implies host-execution consent
    monkeypatch.delenv("NEXI_STUDIO_ALLOW_HOST_EXECUTION", raising=False)
    assert "consent has been revoked" in supervisor._execution_gate_error("antigravity")


def test_nexi_manager_answers_safe_reversible_question_before_escalating():
    safe_question = REQUIREMENTS.replace(
        "BLOCKING_QUESTIONS:\n- none",
        "BLOCKING_QUESTIONS:\n- Which test framework should we use?",
    )
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, requirements_sequence=[safe_question, REQUIREMENTS]))
    started = execute_tool("nexi_start_studio_build", _start_slots("studio mode: build a manager supervised app"))
    run = _wait_for(started["run_id"], {"completed", "failed", "waiting_for_input"})
    assert run.status == "completed", run.result
    studio = run.metadata["studio"]
    assert studio["manager_decisions"]
    decision = studio["manager_decisions"][0]
    assert decision["source"] == "nexi_manager"
    assert decision["reason"] == "reversible_existing-project_default"
    requirement_calls = [call for call in calls if call["stage"] == "requirements"]
    assert len(requirement_calls) == 2
    assert "smallest reversible local choice" in requirement_calls[1]["prompt"]


def test_request_classification_and_not_applicable_stage_selection(tmp_path):
    project = tmp_path / "projects" / "existing"
    project.mkdir(parents=True)
    (project / "existing.py").write_text("x = 1", encoding="utf-8")
    calls = []
    started, run = _start_success(calls, "studio mode: fix bug in parser", project_dir=str(project))
    assert started["request_class"] == "BUG_FIX"
    assert run.status == "completed"
    assert run.metadata["studio"]["gates"]["G2"]["status"] == "NOT_APPLICABLE"
    assert run.metadata["studio"]["gates"]["G3"]["status"] == "NOT_APPLICABLE"
    assert {call["stage"] for call in calls}.isdisjoint({"research", "architecture"})
    assert len(run.artifacts) == 11


@pytest.mark.parametrize(("goal", "facts", "expected"), [
    ("create a new app", {"has_project_files": False}, "NEW_PROJECT"),
    ("build a bug tracker", {"has_project_files": False}, "NEW_PROJECT"),
    ("revise the product idea", {"has_project_files": True}, "IDEA_REVISION"),
    ("add a feature for exports", {"has_project_files": True}, "FEATURE_CHANGE"),
    ("change the report title", {"has_project_files": True}, "CHANGE_REQUEST"),
    ("fix the parser bug", {"has_project_files": True}, "BUG_FIX"),
    ("refactor for performance", {"has_project_files": True}, "TECHNICAL_IMPROVEMENT"),
    ("prototype an experiment", {"has_project_files": True}, "EXPERIMENT"),
    ("release the current app", {"has_project_files": True}, "RELEASE"),
    ("emergency hotfix", {"has_project_files": True}, "HOTFIX"),
    ("continue the existing work", {"has_project_files": True}, "CONTINUATION"),
])
def test_all_request_classes_are_deterministic_and_plans_only_narrow_scope(goal, facts, expected):
    policy = governance.load_policy()
    assert governance.classify_request(goal, facts) == expected
    plan = governance.selected_stages(expected, policy)
    assert set(plan) <= set(supervisor.STAGES)
    if expected == "NEW_PROJECT":
        assert plan == supervisor.STAGES


def test_trusted_agent_json_is_sha_validated_and_target_agents_are_ignored(tmp_path):
    policy = governance.load_policy()
    agents_json, records = governance.load_trusted_agents(["qa-verifier"], policy)
    assert json.loads(agents_json)["qa-verifier"]["prompt"]
    assert len(records[0]["sha256"]) == 64
    target = tmp_path / ".claude" / "agents"
    target.mkdir(parents=True)
    (target / "qa-verifier.md").write_text("MALICIOUS TARGET AGENT", encoding="utf-8")
    agents_json_again, _ = governance.load_trusted_agents(["qa-verifier"], policy)
    assert "MALICIOUS" not in agents_json_again


def test_grouped_questions_assumptions_and_same_stage_resume():
    grouped = REQUIREMENTS.replace(
        "BLOCKING_QUESTIONS:\n- none",
        "BLOCKING_QUESTIONS:\n- Which payment provider?\n- Which billing currency?",
    )
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, requirements_sequence=[grouped, REQUIREMENTS]))
    started = execute_tool("nexi_start_studio_build", _start_slots("studio mode: build a paid newsletter"))
    run = _wait_for(started["run_id"], {"waiting_for_input", "failed"})
    studio = run.metadata["studio"]
    assert run.status == "waiting_for_input"
    assert len([item for item in studio["pending_questions"] if item["status"] == "PENDING"]) == 2
    assert studio["gates"]["G1"]["status"] == "BLOCKED"
    assert studio["assumptions"]
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("Stripe; INR", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"completed", "failed"})
    assert run.status == "completed", run.result
    assert [call["stage"] for call in calls].count("requirements") == 2
    assert [call["stage"] for call in calls].count("research") == 1
    assert all(item["status"] == "ANSWERED" for item in run.metadata["studio"]["pending_questions"])
    assert len(run.metadata["studio"]["authorization_history"]) == 2
    requirement_calls = [call for call in calls if call["stage"] == "requirements"]
    first_session = str(uuid.uuid5(uuid.NAMESPACE_URL, "nexi-studio-test:requirements"))
    assert "resume_session_id" not in requirement_calls[0]
    assert requirement_calls[1]["resume_session_id"] == first_session


def test_explicit_release_blocks_at_g10_when_governance_is_incomplete(tmp_path):
    project = tmp_path / "projects" / "release-app"
    project.mkdir(parents=True)
    (project / "app.py").write_text("print('ok')", encoding="utf-8")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls))
    started = execute_tool("nexi_start_studio_build", _start_slots("studio mode: release the current app", project_dir=str(project)))
    run = _wait_for(started["run_id"], {"waiting_for_input", "completed"})
    studio = run.metadata["studio"]
    assert studio["request_class"] == "RELEASE"
    assert run.status == "waiting_for_input"
    assert studio["gates"]["G10"]["status"] == "BLOCKED"
    assert studio["release_claims"]["highest_proven_state"] == "RELEASE_BLOCKED"


def test_qa_requires_exact_ac_coverage():
    calls = []
    bad_qa = QA.replace("- [PASS] AC-1: Core flow works with independent objective evidence {QA_TOKEN}.\n", "")
    supervisor.set_dependencies(_successful_dependencies(calls, outputs={"qa": bad_qa}))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a local app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "qa_acceptance_failed"
    assert run.metadata["studio"]["gates"]["G7"]["status"] == "FAILED"


def test_security_high_finding_blocks_g8():
    calls = []
    high = SECURITY.replace("- [NONE] No Critical or High finding.", "- [HIGH] SEC-1: RESOLVED authorization bypass.").replace("PASS workspace_sha256={WORKSPACE_DIGEST} agent_sha256={AGENT_SHA256}", "BLOCK")
    supervisor.set_dependencies(_successful_dependencies(calls, outputs={"security_review": high}))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a local app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "security_blocked"
    assert run.metadata["studio"]["gates"]["G8"]["status"] == "FAILED"


def test_closeout_detects_artifact_hash_inconsistency():
    calls = []
    _, run = _start_success(calls)
    Path(run.artifacts[0]["path"]).write_text("tampered", encoding="utf-8")
    issues = supervisor._closeout_consistency(run, run.metadata["studio"], governance.load_policy())
    assert any("Artifact hash failed" in issue for issue in issues)


def test_full_jsonl_restore_retains_runs_older_than_fifty_checkpoints(tmp_path, monkeypatch):
    store = tmp_path / "long.jsonl"
    monkeypatch.setattr(we, "_STORE", store)
    for index in range(60):
        run = we.WorkflowRun(
            run_id=f"wf_{index:012x}", workflow_type="router_audit", goal=str(index),
            status="completed", created_at=float(index), updated_at=float(index),
        )
        assert we._persist(run)
    we.clear()
    we._load()
    assert we.get_run("wf_000000000000") is not None
    assert we.get_run("wf_00000000003b") is not None
    assert len(we.list_runs()) == 60


def test_restart_policy_pauses_and_fresh_authorization_resumes_same_stage():
    grouped = REQUIREMENTS.replace("BLOCKING_QUESTIONS:\n- none", "BLOCKING_QUESTIONS:\n- Confirm local scope?")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, requirements_sequence=[grouped, REQUIREMENTS]))
    started = execute_tool("nexi_start_studio_build", _start_slots("studio mode: build a restart-safe app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    run.status = "running"
    we.register_workflow_type(
        supervisor.WORKFLOW_TYPE,
        supervisor.run_studio_build,
        continuer=supervisor._continue_studio,
        canceller=supervisor._cancel_studio,
        restart_policy="pause_for_resume",
    )
    assert run.status == "waiting_for_input"
    assert run.metadata["restart_reconciliation"]["required"] is True
    resumed = supervisor.continue_studio_build(_continue_slots("Confirmed", run_id=run.run_id))
    assert resumed["success"] is True and resumed["authorization_id"] != started["authorization_id"]
    run = _wait_for(run.run_id, {"completed", "failed"})
    assert run.status == "completed", run.result
    assert run.metadata["restart_reconciliation"]["required"] is False
    assert run.metadata["restart_reconciliation"]["external_side_effects_replayed"] is False


def test_read_only_stage_mutation_fails_current_gate():
    def run_task(_prompt, project_dir=None, **_kwargs):
        Path(project_dir, "unexpected.txt").write_text("changed", encoding="utf-8")
        return {"ok": True, "dispatch": {"ok": True, "result": REQUIREMENTS}}

    supervisor.set_dependencies(supervisor.StudioDependencies(
        run_task=run_task,
        stop_task=lambda **_kwargs: True,
        workspace_snapshot=verifier.workspace_snapshot,
        compare_workspace=verifier.compare_workspace,
        run_tests=lambda *_a, **_k: {"ran": True, "passed": True, "output": "ok"},
    ))
    project = Path(os.environ["NEXI_STUDIO_PROJECTS_DIR"], "existing-read-only")
    project.mkdir(parents=True)
    (project / "existing.py").write_text("x = 1", encoding="utf-8")
    started = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: change the safe app", project_dir=str(project)),
    )
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "read_only_stage_modified_workspace"
    assert run.metadata["studio"]["gates"]["G1"]["status"] == "FAILED"
    assert run.status == "waiting_for_input"
    assert run.metadata["studio"]["failure"]["repair_owner"] == "business-analyst"
    assert run.metadata["studio"]["failure"]["loop_count"] == 1
    assert run.metadata["studio"]["pause_integrity"]["workspace_digest"]
    assert "requirements" not in run.metadata["studio"]["claude_sessions"]


def test_read_only_mutation_cleanup_allows_fresh_rerun():
    calls = []
    base = _successful_dependencies(calls)
    state = {"mutated": False}

    def mutate_once(prompt, project_dir=None, **kwargs):
        if "NEXI STUDIO STAGE: requirements" in prompt and not state["mutated"]:
            state["mutated"] = True
            Path(project_dir, "unexpected.txt").write_text("changed", encoding="utf-8")
            return {"ok": True, "dispatch": {"ok": True, "result": REQUIREMENTS, "session_id": str(uuid.uuid4())}}
        return base.run_task(prompt, project_dir=project_dir, **kwargs)

    supervisor.set_dependencies(supervisor.StudioDependencies(
        run_task=mutate_once,
        stop_task=base.stop_task,
        workspace_snapshot=base.workspace_snapshot,
        compare_workspace=base.compare_workspace,
        run_tests=base.run_tests,
    ))
    project = Path(os.environ["NEXI_STUDIO_PROJECTS_DIR"], "recover-read-only")
    project.mkdir(parents=True)
    (project / "existing.py").write_text("x = 1", encoding="utf-8")
    started = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: change the recoverable app", project_dir=str(project)),
    )
    run = _wait_for(started["run_id"], {"waiting_for_input"})

    blocked = execute_tool("nexi_continue_studio_build", _continue_slots("retry", run_id=run.run_id))
    assert blocked["success"] is False
    assert blocked["code"] == "reconciliation_failed"

    (project / "unexpected.txt").unlink()
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("retry after cleanup", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"completed", "failed"})
    assert run.status == "completed", run.result
    requirement_calls = [call for call in calls if call["stage"] == "requirements"]
    assert requirement_calls and not requirement_calls[0].get("resume_session_id")


def test_artifacts_are_atomic_run_scoped_and_capped(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXI_STUDIO_DIR", str(tmp_path))
    monkeypatch.setattr(artifacts, "_SOFT_CHAR_CAP", 120)
    first = artifacts.write_doc("wf_aaaaaaaaaaaa", "01-requirements.md", "x" * 500)
    second = artifacts.write_doc("wf_bbbbbbbbbbbb", "01-requirements.md", "short")
    artifacts.write_run_json("wf_aaaaaaaaaaaa", {"run_id": "wf_aaaaaaaaaaaa"})
    assert first["over_cap"] is True and first["chars"] <= 120
    assert Path(first["path"]).parent != Path(second["path"]).parent
    assert not list(tmp_path.rglob("*.tmp"))


def test_exact_cancel_authorization_is_fresh_one_use_and_source_bound():
    first = route_intent_v2("cancel studio", source="voice")
    second = route_intent_v2("cancel studio", source="voice")
    assert first["intent"] == "nexi_cancel_studio_build"
    assert first["slots"]["_studio_auth"] != second["slots"]["_studio_auth"]
    assert first["slots"]["command_source"] == "voice"
    wrong_source = dict(first["slots"], command_source="ui")
    assert supervisor.cancel_studio_build(wrong_source)["code"] == "authorization_required"
    assert supervisor.cancel_studio_build(first["slots"])["code"] == "authorization_required"  # consumed by mismatch
    no_run = supervisor.cancel_studio_build(second["slots"])
    assert no_run["success"] is True
    assert no_run["authorization_id"]
    assert supervisor.cancel_studio_build(second["slots"])["code"] == "authorization_required"


def test_governance_enforces_exact_order_profiles_and_dynamic_limits():
    policy = governance.load_policy()
    assert tuple(policy["stages"]) == governance.CANONICAL_STAGES
    assert [policy["stages"][stage]["gate"] for stage in governance.CANONICAL_STAGES] == [f"G{i}" for i in range(1, 12)]
    assert [policy["stages"][stage]["ready_state"] for stage in governance.CANONICAL_STAGES] == list(governance.CANONICAL_READY_STATES.values())
    assert [policy["stages"][stage]["agent"] for stage in governance.CANONICAL_STAGES] == list(governance.CANONICAL_STAGE_AGENTS.values())
    assert [policy["stages"][stage]["permission_mode"] for stage in governance.CANONICAL_STAGES] == list(governance.CANONICAL_PERMISSION_MODES.values())
    assert [policy["stages"][stage]["read_only"] for stage in governance.CANONICAL_STAGES] == list(governance.CANONICAL_READ_ONLY.values())
    assert policy["request_class_stage_plans"] == {
        name: list(governance.CANONICAL_REQUEST_CLASS_STAGE_PLANS[name])
        for name in governance.REQUEST_CLASSES
    }
    assert policy["schema_version"] == 3
    assert "development" in policy["branch_policy"]["protected_branches"]
    assert governance.TECHNICAL_LEAD_AGENT == "developer-team"
    assert "lead-developer" not in policy["trusted_agents"]
    for name, definition in policy["trusted_agents"].items():
        profile = definition["tool_profile"]
        if profile == "read_only":
            assert definition["allowed_tools"] == list(governance.READ_ONLY_TOOLS)
        elif profile == "research":
            assert definition["allowed_tools"] == list(governance.RESEARCH_TOOLS)
        assert "ReportFindings" not in definition["allowed_tools"]
        agents_json, _ = governance.load_trusted_agents([name], policy, authoritative_permission_mode="plan")
        dynamic = json.loads(agents_json)[name]
        assert dynamic["permissionMode"] == "plan"
        assert isinstance(dynamic["maxTurns"], int)

    malformed = json.loads(json.dumps(policy))
    malformed["request_class_stage_plans"]["BUG_FIX"] = ["requirements", "qa", "sprint_plan"]
    with pytest.raises(governance.GovernanceError):
        governance.load_policy(_write_policy_for_test(malformed))

    wrong_schema = json.loads(json.dumps(policy))
    wrong_schema["schema_version"] = 2
    with pytest.raises(governance.GovernanceError):
        governance.load_policy(_write_policy_for_test(wrong_schema))

    no_development = json.loads(json.dumps(policy))
    no_development["branch_policy"]["protected_branches"].remove("development")
    with pytest.raises(governance.GovernanceError):
        governance.load_policy(_write_policy_for_test(no_development))

    governance_text = (Path(__file__).resolve().parents[1] / ".github" / "ai-team-governance.yml").read_text(encoding="utf-8")
    assert "protected: [main, master, development]" in governance_text
    assert "state: RELEASE_APPROVED" in governance_text
    assert "implies_human_or_external_approval: false" in governance_text
    assert "- LOCAL_VERIFIED" in governance_text
    assert "- COMMITTED_LOCAL" in governance_text


def _write_policy_for_test(policy: dict) -> str:
    path = Path(os.environ["NEXI_STUDIO_DIR"]).parent / f"policy-{time.time_ns()}.json"
    path.write_text(json.dumps(policy), encoding="utf-8")
    return str(path)


def test_provenance_canonical_fields_cannot_be_overwritten(tmp_path):
    policy = governance.load_policy()
    project = tmp_path / "projects" / "provenance"
    project.mkdir(parents=True)
    run = we.WorkflowRun(run_id="wf_a1b2c3d4e5f6", workflow_type="studio_build", goal="x", status="running", created_at=time.time())
    studio = {
        "run_id": run.run_id,
        "authorization_id": "auth_real",
        "project_dir": str(project),
        "repository": str(project),
        "working_branch": "NOT_A_GIT_REPOSITORY",
        "stage_attempts": {"requirements": 2},
        "trusted_agent_definitions": {"requirements": [{"name": "business-analyst", "sha256": "a" * 64}]},
    }
    entry = supervisor._record_artifact(
        run,
        studio,
        "requirements",
        REQUIREMENTS,
        policy,
        provenance={"run_id": "evil", "gate": "G99", "workspace_digest": "evil", "custom": "kept"},
    )
    assert entry["provenance"]["run_id"] == run.run_id
    assert entry["provenance"]["gate"] == "G1"
    assert entry["provenance"]["workspace_digest"] != "evil"
    assert entry["provenance"]["custom"] == "kept"


def test_question_overflow_is_resumable_at_same_gate():
    overflow = REQUIREMENTS.replace(
        "BLOCKING_QUESTIONS:\n- none",
        "BLOCKING_QUESTIONS:\n- One?\n- Two?\n- Three?\n- Four?",
    )
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, requirements_sequence=[overflow]))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build an overflow app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    studio = run.metadata["studio"]
    assert studio["failure"]["code"] == "question_limit"
    assert studio["failure"]["resume_stage"] == "requirements"
    assert studio["gates"]["G1"]["status"] == "BLOCKED"


def test_remediation_limit_requires_and_audits_fresh_explicit_override():
    invalid = REQUIREMENTS.replace("## Acceptance candidates", "## Missing acceptance")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, outputs={"requirements": invalid}))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a bounded app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    for index in range(2):
        resumed = execute_tool("nexi_continue_studio_build", _continue_slots(f"retry {index}", run_id=run.run_id))
        assert resumed["success"] is True
        run = _wait_for(run.run_id, {"waiting_for_input"})
    assert run.metadata["studio"]["remediation"]["loops_by_gate"]["G1"] == 3
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("CEO override", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"waiting_for_input"})
    audit = run.metadata["studio"]["remediation_override_audit"][-1]
    assert audit["prior_loop_count"] == 3
    assert audit["authorization_id"] == resumed["authorization_id"]
    assert run.metadata["studio"]["remediation"]["loops_by_gate"]["G1"] == 1


def test_non_git_workspace_mutation_blocks_resume():
    grouped = REQUIREMENTS.replace("BLOCKING_QUESTIONS:\n- none", "BLOCKING_QUESTIONS:\n- Confirm?")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, requirements_sequence=[grouped]))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a digest app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    Path(run.metadata["studio"]["project_dir"], "mutated.txt").write_text("changed", encoding="utf-8")
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("yes", run_id=run.run_id))
    assert resumed["success"] is False
    assert resumed["code"] == "reconciliation_failed"
    assert "workspace changed" in resumed["message"].lower()


def _git(project: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, check=True)
    return result.stdout.strip()


def test_git_head_drift_and_parent_repository_scope_escape_are_rejected(tmp_path):
    projects = tmp_path / "projects"
    repo = projects / "repo"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "studio@example.invalid")
    _git(repo, "config", "user.name", "Studio Test")
    _git(repo, "checkout", "-b", "feature/studio")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    grouped = REQUIREMENTS.replace("BLOCKING_QUESTIONS:\n- none", "BLOCKING_QUESTIONS:\n- Confirm?")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, requirements_sequence=[grouped]))
    started = execute_tool("nexi_start_studio_build", _start_slots("studio mode: change the app", project_dir=str(repo)))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    (repo / "app.py").write_text("x = 2", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "drift")
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("yes", run_id=run.run_id))
    assert resumed["success"] is False
    assert "head_sha changed" in resumed["message"].lower()

    we.clear()
    parent = projects / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    _git(parent, "init")
    (child / "file.py").write_text("x = 1", encoding="utf-8")
    denied = supervisor.start_studio_build(_start_slots("studio mode: change child", project_dir=str(child)))
    assert denied["success"] is False
    assert "git top-level" in denied["message"].lower()


def test_implementation_rejects_git_control_mutation_and_keeps_remote_separate(tmp_path):
    repo = tmp_path / "projects" / "git-controls"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "studio@example.invalid")
    _git(repo, "config", "user.name", "Studio Test")
    _git(repo, "checkout", "-b", "feature/studio")
    _git(repo, "remote", "add", "origin", "https://example.invalid/nexi.git")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")

    calls = []
    base = _successful_dependencies(calls)
    def tampering_run_task(prompt, project_dir=None, **kwargs):
        result = base.run_task(prompt, project_dir=project_dir, **kwargs)
        if "NEXI STUDIO STAGE: implementation" in prompt:
            config = Path(project_dir, ".git", "config")
            config.write_text(config.read_text(encoding="utf-8") + "\n# unauthorized mutation\n", encoding="utf-8")
        return result
    supervisor.set_dependencies(supervisor.StudioDependencies(
        run_task=tampering_run_task,
        stop_task=base.stop_task,
        workspace_snapshot=base.workspace_snapshot,
        compare_workspace=base.compare_workspace,
        run_tests=base.run_tests,
    ))
    started = execute_tool("nexi_start_studio_build", _start_slots("studio mode: change the app", project_dir=str(repo)))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    studio = run.metadata["studio"]
    assert studio["repository"] == "https://example.invalid/nexi.git"
    assert studio["remote_url"] == studio["repository"]
    assert Path(studio["repository_root"]) == repo.resolve()
    assert studio["failure"]["code"] == "implementation_verification_failed"
    assert ".git/config" in studio["verification"]["git_control_changes"]


def test_vague_qa_and_malformed_high_security_findings_block():
    calls = []
    vague = QA.replace(" {QA_TOKEN}", "")
    supervisor.set_dependencies(_successful_dependencies(calls, outputs={"qa": vague}))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a qa evidence app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "qa_acceptance_failed"

    we.clear()
    calls = []
    malformed = SECURITY.replace("- [NONE] No Critical or High finding.", "- HIGH SEC-9: authorization bypass")
    supervisor.set_dependencies(_successful_dependencies(calls, outputs={"security_review": malformed}))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a security evidence app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "security_blocked"
    assert run.metadata["studio"]["security"]["blocking_findings"]


def test_jsonl_checkpoint_precedes_run_json(monkeypatch, tmp_path):
    run = we.WorkflowRun(run_id="wf_123456abcdef", workflow_type="studio_build", goal="x", status="running", created_at=time.time(), metadata={"studio": {}})
    studio = {"run_id": run.run_id, "status": "running"}
    called = []
    monkeypatch.setattr(we, "_persist", lambda _run: False)
    monkeypatch.setattr(artifacts, "write_run_json", lambda *_a, **_k: called.append("run_json"))
    assert supervisor._checkpoint(run, studio, event_type="test", expected_statuses={"running"}) is False
    assert called == []
    assert run.status == "running"


def test_project_memory_is_atomic_hashed_idempotent_and_has_no_unearned_idea_history():
    calls = []
    _, run = _start_success(calls)
    assert run.status == "completed", run.result
    studio = run.metadata["studio"]
    memory = studio["project_memory"]
    for key in ("project_profile", "decisions", "architecture_index", "product_defaults"):
        entry = memory[key]
        content = Path(entry["path"]).read_text(encoding="utf-8")
        assert __import__("hashlib").sha256(content.encode("utf-8")).hexdigest() == entry["sha256"]
    assert not Path(artifacts.project_dir(studio["project_id"]), "idea-history.md").exists()
    decisions_path = Path(memory["decisions"]["path"])
    supervisor._write_project_memory(run, studio)
    supervisor._write_project_memory(run, studio)
    assert decisions_path.read_text(encoding="utf-8").count(f"## Run {run.run_id}") == 1


def test_project_document_helpers_reject_invalid_project_ids_and_names():
    with pytest.raises(ValueError):
        artifacts.write_project_doc("../escape", "project-profile.md", "x")
    with pytest.raises(ValueError):
        artifacts.write_project_doc("PROJ_" + "A" * 20, "project-profile.md", "x")
    with pytest.raises(ValueError):
        artifacts.write_project_doc("proj_" + "a" * 20, "../escape.md", "x")


def test_project_memory_failure_is_recoverable_and_blocks_g11(monkeypatch, tmp_path):
    project = tmp_path / "projects" / "memory-failure-existing"
    project.mkdir(parents=True)
    (project / "existing.py").write_text("x = 1", encoding="utf-8")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls))
    monkeypatch.setattr(artifacts, "write_project_doc", lambda *_a, **_k: (_ for _ in ()).throw(OSError("disk full")))
    started = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: fix bug in memory", project_dir=str(project)),
    )
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    studio = run.metadata["studio"]
    assert studio["failure"]["code"] == "project_memory_failed"
    assert studio["failure"]["terminal"] is False
    assert studio["gates"]["G11"]["status"] == "FAILED"


def test_same_run_project_memory_resume_does_not_duplicate_decisions(monkeypatch, tmp_path):
    project = tmp_path / "projects" / "memory-resume-existing"
    project.mkdir(parents=True)
    (project / "existing.py").write_text("x = 1", encoding="utf-8")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls))
    real_write = artifacts.write_project_doc
    state = {"writes": 0, "failed": False}

    def fail_after_decisions(*args, **kwargs):
        state["writes"] += 1
        if state["writes"] == 3 and not state["failed"]:
            state["failed"] = True
            raise OSError("transient disk error")
        return real_write(*args, **kwargs)

    monkeypatch.setattr(artifacts, "write_project_doc", fail_after_decisions)
    started = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: fix bug in memory", project_dir=str(project)),
    )
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "project_memory_failed"
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("retry project memory", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"completed", "failed"})
    assert run.status == "completed", run.result
    decisions = artifacts.read_project_doc(run.metadata["studio"]["project_id"], "decisions.md")
    assert decisions.count(f"## Run {run.run_id}") == 1
    closeout_calls = [call for call in calls if call["stage"] == "closeout"]
    assert len(closeout_calls) == 2
    assert closeout_calls[1]["resume_session_id"] == str(uuid.uuid5(uuid.NAMESPACE_URL, "nexi-studio-test:closeout"))


def test_partial_project_memory_tampering_blocks_same_run_resume(monkeypatch, tmp_path):
    project = tmp_path / "projects" / "memory-journal-tamper"
    project.mkdir(parents=True)
    (project / "existing.py").write_text("x = 1", encoding="utf-8")
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls))
    real_write = artifacts.write_project_doc
    state = {"writes": 0, "failed": False}

    def fail_after_decisions(*args, **kwargs):
        state["writes"] += 1
        if state["writes"] == 3 and not state["failed"]:
            state["failed"] = True
            raise OSError("transient disk error")
        return real_write(*args, **kwargs)

    monkeypatch.setattr(artifacts, "write_project_doc", fail_after_decisions)
    started = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: fix bug in memory journal", project_dir=str(project)),
    )
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    decisions = Path(artifacts.project_dir(run.metadata["studio"]["project_id"]), "decisions.md")
    decisions.write_text(decisions.read_text(encoding="utf-8") + "\n- unauthorized tamper\n", encoding="utf-8")

    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("retry project memory", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"waiting_for_input", "failed", "completed"})
    assert run.status == "waiting_for_input"
    assert run.metadata["studio"]["failure"]["code"] == "project_memory_failed"
    assert "outside the journal" in run.metadata["studio"]["failure"]["message"]


def test_strategist_runs_only_for_new_project_and_idea_revision(tmp_path):
    new_calls = []
    _, new_run = _start_success(new_calls, "studio mode: build a strategy app")
    assert [call["stage"] for call in new_calls].count("project_strategy") == 1
    assert new_run.metadata["studio"]["strategy"]["agent"] == "project-strategist"

    bug_project = tmp_path / "projects" / "bug-existing"
    bug_project.mkdir(parents=True)
    (bug_project / "existing.py").write_text("x = 1", encoding="utf-8")
    bug_calls = []
    _, bug_run = _start_success(bug_calls, "studio mode: fix bug in parser", project_dir=str(bug_project))
    assert bug_run.metadata["studio"]["request_class"] == "BUG_FIX"
    assert all(call["stage"] != "project_strategy" for call in bug_calls)

    revision_project = tmp_path / "projects" / "revision-existing"
    revision_project.mkdir(parents=True)
    (revision_project / "existing.py").write_text("x = 1", encoding="utf-8")
    old_project_id = governance.stable_project_id(str(revision_project.resolve()))
    previous = artifacts.write_project_doc(old_project_id, "project-profile.md", "# Project Profile\n- Prior direction")
    artifacts.publish_project_manifest(old_project_id, expected_documents={previous["name"]: previous})
    revision_calls = []
    _, revision_run = _start_success(revision_calls, "studio mode: revise the product idea", project_dir=str(revision_project))
    revision_studio = revision_run.metadata["studio"]
    assert revision_studio["request_class"] == "IDEA_REVISION"
    assert [call["stage"] for call in revision_calls].count("project_strategy") == 1
    assert revision_studio["strategy"]["previous_project_profile_sha256"] == previous["sha256"]
    history = artifacts.read_project_doc(revision_studio["project_id"], "idea-history.md")
    assert "## IC-" in history
    assert f"run={revision_run.run_id}" in history


def test_project_strategist_mutation_requires_cleanup_and_fresh_session():
    session_id = str(uuid.uuid4())
    calls = []
    base = _successful_dependencies(calls)
    state = {"mutated": False}

    def mutating_strategy(prompt, project_dir=None, **kwargs):
        if "NEXI STUDIO INTERNAL SUBSTAGE: project_strategy" in prompt and not state["mutated"]:
            state["mutated"] = True
            Path(project_dir, "unauthorized.txt").write_text("changed", encoding="utf-8")
            return {"ok": True, "dispatch": {"ok": True, "result": STRATEGY, "session_id": session_id}}
        return base.run_task(prompt, project_dir=project_dir, **kwargs)

    supervisor.set_dependencies(supervisor.StudioDependencies(
        run_task=mutating_strategy,
        stop_task=lambda **_kwargs: True,
        workspace_snapshot=verifier.workspace_snapshot,
        compare_workspace=verifier.compare_workspace,
        run_tests=lambda *_a, **_k: {"ran": True, "passed": True, "output": "ok"},
    ))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a strategy mutation app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.status == "waiting_for_input"
    assert run.metadata["studio"]["failure"]["code"] == "project_strategy_modified_workspace"
    assert run.metadata["studio"]["failure"]["terminal"] is False
    assert "project_strategy" not in run.metadata["studio"]["claude_sessions"]

    blocked = execute_tool("nexi_continue_studio_build", _continue_slots("retry", run_id=run.run_id))
    assert blocked["success"] is False
    assert blocked["code"] == "reconciliation_failed"

    Path(run.metadata["studio"]["project_dir"], "unauthorized.txt").unlink()
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("retry after cleanup", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"completed", "failed"})
    assert run.status == "completed", run.result
    strategy_calls = [call for call in calls if call["stage"] == "project_strategy"]
    assert strategy_calls and not strategy_calls[0].get("resume_session_id")


def test_project_memory_tampering_blocks_later_run():
    calls = []
    _, run = _start_success(calls, "studio mode: build a memory integrity app")
    studio = run.metadata["studio"]
    decisions = Path(studio["project_memory"]["decisions"]["path"])
    decisions.write_text(decisions.read_text(encoding="utf-8") + "\n- tampered\n", encoding="utf-8")

    started = execute_tool(
        "nexi_start_studio_build",
        _start_slots("studio mode: fix bug in memory integrity app", project_dir=studio["project_dir"]),
    )
    assert started["success"] is False
    assert started["code"] == "project_memory_integrity_failed"


@pytest.mark.parametrize("test_result", [
    {"ran": False, "passed": False, "output": "not detected"},
    {"ran": True, "passed": False, "output": "1 failed"},
])
def test_qa_objective_rerun_rejects_no_run_and_failure(test_result):
    calls = []
    supervisor.set_dependencies(_successful_dependencies(calls, test_results=[
        {"ran": True, "passed": True, "output": "g6 passed"},
        test_result,
    ]))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build an objective qa app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["failure"]["code"] == "qa_objective_tests_failed"
    assert all(call["stage"] != "qa" for call in calls)


def test_qa_objective_rerun_rejects_post_test_mutation():
    calls = []
    base = _successful_dependencies(calls)
    count = {"tests": 0}

    def mutating_tests(project_dir, **_kwargs):
        count["tests"] += 1
        if count["tests"] == 2:
            Path(project_dir, "qa-mutated.txt").write_text("mutation", encoding="utf-8")
        return {"ran": True, "passed": True, "output": "passed"}

    supervisor.set_dependencies(supervisor.StudioDependencies(
        run_task=base.run_task,
        stop_task=base.stop_task,
        workspace_snapshot=base.workspace_snapshot,
        compare_workspace=base.compare_workspace,
        run_tests=mutating_tests,
    ))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a mutation guarded app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    evidence = run.metadata["studio"]["qa_objective_evidence"]
    assert evidence["post_test_mutation"] is True
    assert run.metadata["studio"]["failure"]["code"] == "qa_objective_tests_failed"

    blocked = execute_tool("nexi_continue_studio_build", _continue_slots("retry", run_id=run.run_id))
    assert blocked["success"] is False
    assert blocked["code"] == "reconciliation_failed"

    Path(run.metadata["studio"]["project_dir"], "qa-mutated.txt").unlink()
    resumed = execute_tool("nexi_continue_studio_build", _continue_slots("retry after cleanup", run_id=run.run_id))
    assert resumed["success"] is True
    run = _wait_for(run.run_id, {"completed", "failed"})
    assert run.status == "completed", run.result


def test_qa_objective_rerun_rejects_truncated_post_test_snapshot():
    calls = []
    base = _successful_dependencies(calls)
    state = {"tests": 0, "truncate_next": False}

    def tests(project_dir, **_kwargs):
        state["tests"] += 1
        if state["tests"] == 2:
            state["truncate_next"] = True
        return {"ran": True, "passed": True, "output": "passed"}

    def snapshots(project_dir):
        snapshot = verifier.workspace_snapshot(project_dir)
        if state["truncate_next"]:
            state["truncate_next"] = False
            snapshot["truncated"] = True
        return snapshot

    supervisor.set_dependencies(supervisor.StudioDependencies(
        run_task=base.run_task,
        stop_task=base.stop_task,
        workspace_snapshot=snapshots,
        compare_workspace=base.compare_workspace,
        run_tests=tests,
    ))
    started = execute_tool("nexi_start_studio_build", _start_slots("let's build a truncated snapshot app"))
    run = _wait_for(started["run_id"], {"waiting_for_input"})
    assert run.metadata["studio"]["qa_objective_evidence"]["snapshot_truncated"] is True
    assert run.metadata["studio"]["failure"]["code"] == "qa_objective_tests_failed"


def test_development_branch_is_protected_from_implementation(tmp_path):
    repo = tmp_path / "projects" / "development-protected"
    repo.mkdir(parents=True)
    _git(repo, "init")
    _git(repo, "config", "user.email", "studio@example.invalid")
    _git(repo, "config", "user.name", "Studio Test")
    _git(repo, "checkout", "-b", "development")
    (repo / "app.py").write_text("x = 1", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-m", "initial")
    denied = supervisor.start_studio_build(_start_slots("studio mode: change the app", project_dir=str(repo)))
    assert denied["code"] == "protected_branch"


def test_clean_process_can_import_studio_supervisor_without_circular_import():
    result = subprocess.run(
        [sys.executable, "-c", "import engine.studio.supervisor; print('IMPORT_OK')"],
        cwd=str(Path(__file__).resolve().parents[1]),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "IMPORT_OK" in result.stdout
