"""Deterministic, stdlib-only runtime policy for Nexi Studio."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable


REQUEST_CLASSES = (
    "NEW_PROJECT",
    "IDEA_REVISION",
    "FEATURE_CHANGE",
    "CHANGE_REQUEST",
    "BUG_FIX",
    "TECHNICAL_IMPROVEMENT",
    "EXPERIMENT",
    "RELEASE",
    "HOTFIX",
    "CONTINUATION",
)
CANONICAL_STAGES = (
    "requirements",
    "research",
    "architecture",
    "sprint_plan",
    "implementation",
    "developer_tests",
    "qa",
    "security_review",
    "integration",
    "release",
    "closeout",
)
CANONICAL_GATES = {stage: f"G{index}" for index, stage in enumerate(CANONICAL_STAGES, start=1)}
CANONICAL_READY_STATES = {
    "requirements": "REQUIREMENTS_READY",
    "research": "RESEARCH_READY",
    "architecture": "ARCHITECTURE_READY",
    "sprint_plan": "SPRINT_READY",
    "implementation": "IMPLEMENTATION_COMPLETE",
    "developer_tests": "DEVELOPER_TESTS_PASS",
    "qa": "QA_PASS",
    "security_review": "SECURITY_PASS",
    "integration": "INTEGRATION_PASS",
    "release": "LOCAL_VERIFIED",
    "closeout": "CLOSED",
}
CANONICAL_STAGE_AGENTS = {
    "requirements": "business-analyst",
    "research": "research-analyst",
    "architecture": "solution-architect",
    "sprint_plan": "product-manager",
    "implementation": "developer-team",
    "developer_tests": "test-engineer",
    "qa": "qa-verifier",
    "security_review": "security-reviewer",
    "integration": "integration-verifier",
    "release": "release-manager",
    "closeout": "knowledge-curator",
}
def _unattended_enabled() -> bool:
    """Operator opt-in for prompt-free writes. Env only — never model-settable."""
    import os as _os
    return str(_os.getenv("NEXI_STUDIO_UNATTENDED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _write_mode() -> str:
    """The mode a writing stage uses.

    acceptEdits auto-approves FILE EDITS but still prompts for Bash, so an unattended
    run stalls on the first command waiting for someone to click yes. With the operator
    opt-in, writing stages use bypassPermissions so the build actually completes alone.
    Read-only stages are unaffected — they stay on 'plan' either way.
    """
    return "bypassPermissions" if _unattended_enabled() else "acceptEdits"


def permission_mode_for(stage: str) -> str:
    """Permission mode for a stage, evaluated NOW (not frozen at import).

    Reading the env at import time meant a later NEXI_STUDIO_UNATTENDED change — or a
    test setting it — was silently ignored. Always resolve at call time.
    """
    return _write_mode() if stage == "implementation" else "plan"


class _PermissionModes(dict):
    """Back-compat mapping that re-evaluates on lookup instead of being a frozen dict."""

    def __getitem__(self, stage):
        return permission_mode_for(stage)

    def get(self, stage, default=None):
        return permission_mode_for(stage) if stage in CANONICAL_STAGES else default


CANONICAL_PERMISSION_MODES = _PermissionModes(
    {stage: ("acceptEdits" if stage == "implementation" else "plan") for stage in CANONICAL_STAGES}
)
CANONICAL_READ_ONLY = {
    stage: stage != "implementation"
    for stage in CANONICAL_STAGES
}
CANONICAL_REQUEST_CLASS_STAGE_PLANS = {
    "NEW_PROJECT": CANONICAL_STAGES,
    "IDEA_REVISION": CANONICAL_STAGES,
    "FEATURE_CHANGE": ("requirements", "architecture", "sprint_plan", "implementation", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
    "CHANGE_REQUEST": ("requirements", "sprint_plan", "implementation", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
    "BUG_FIX": ("requirements", "sprint_plan", "implementation", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
    "TECHNICAL_IMPROVEMENT": ("requirements", "architecture", "sprint_plan", "implementation", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
    "EXPERIMENT": CANONICAL_STAGES,
    "RELEASE": ("requirements", "sprint_plan", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
    "HOTFIX": ("requirements", "sprint_plan", "implementation", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
    "CONTINUATION": ("requirements", "sprint_plan", "implementation", "developer_tests", "qa", "security_review", "integration", "release", "closeout"),
}
READ_ONLY_TOOLS = ("Read", "Grep", "Glob")
RESEARCH_TOOLS = ("Read", "Grep", "Glob", "WebSearch", "WebFetch")
_IMPLEMENTATION_TOOLS = frozenset({"Read", "Grep", "Glob", "Edit", "Write", "Bash", "Skill"})
_TEST_TOOLS = frozenset({"Read", "Grep", "Glob", "Edit", "Write", "Bash", "Skill"})
_PERMISSION_MODES = frozenset({"default", "acceptEdits", "plan", "dontAsk", "bypassPermissions"})
_DEVELOPER_AGENT_ALLOWLIST = "Agent(frontend-engineer, backend-engineer, design-engineer, test-engineer, devops-engineer)"
# The existing developer-team coordinator is the G5 technical lead. Keep leadership
# inside implementation delegation rather than adding a duplicate approval role.
TECHNICAL_LEAD_AGENT = "developer-team"
_AGENT_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{1,63}$")
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_POLICY_PATH = _ROOT / "config" / "studio" / "governance.json"
_TRUSTED_AGENT_ROOT = (_ROOT / ".claude" / "agents").resolve()


class GovernanceError(ValueError):
    """Raised when checked-in Studio governance is invalid or untrusted."""


def load_policy(path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    policy_path = Path(path or _DEFAULT_POLICY_PATH).resolve()
    try:
        policy = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GovernanceError(f"Studio governance could not be loaded: {exc}") from exc
    required = {
        "schema_version",
        "artifact_root",
        "stages",
        "request_class_stage_plans",
        "max_questions_per_gate",
        "max_fix_loops_per_gate",
        "handoff_target_tokens",
        "extension_allowlists",
        "branch_policy",
        "release",
        "deployment",
        "external_actions_implemented",
        "trusted_agents",
    }
    missing = sorted(required - set(policy))
    if missing:
        raise GovernanceError(f"Studio governance is missing: {', '.join(missing)}")
    if policy.get("schema_version") != 3:
        raise GovernanceError("Studio governance schema_version must be exactly 3.")
    if int(policy["max_questions_per_gate"]) != 3 or int(policy["max_fix_loops_per_gate"]) != 3:
        raise GovernanceError("Studio question and remediation limits must both be three.")
    stages = policy.get("stages") or {}
    if tuple(stages) != CANONICAL_STAGES:
        raise GovernanceError("Studio stages must use the exact canonical G1-G11 order.")
    gates: list[str] = []
    ready_states: list[str] = []
    for stage in CANONICAL_STAGES:
        cfg = stages.get(stage)
        if not isinstance(cfg, dict):
            raise GovernanceError(f"Invalid stage policy for {stage}.")
        canonical_fields = {
            "gate": CANONICAL_GATES[stage],
            "ready_state": CANONICAL_READY_STATES[stage],
            "agent": CANONICAL_STAGE_AGENTS[stage],
            "permission_mode": CANONICAL_PERMISSION_MODES[stage],
            "read_only": CANONICAL_READ_ONLY[stage],
        }
        if any(cfg.get(key) != value for key, value in canonical_fields.items()):
            raise GovernanceError(f"Canonical gate, ready-state, agent, permission, or read-only mapping mismatch for {stage}.")
        gates.append(str(cfg["gate"]))
        ready_states.append(str(cfg["ready_state"]))
    if len(set(gates)) != 11 or len(set(ready_states)) != 11:
        raise GovernanceError("Studio gate and ready-state mappings must be unique.")
    plans = policy.get("request_class_stage_plans") or {}
    if tuple(plans) != REQUEST_CLASSES:
        raise GovernanceError("Studio request-class plans must define the exact canonical class order.")
    for request_class in REQUEST_CLASSES:
        plan = plans.get(request_class)
        expected = list(CANONICAL_REQUEST_CLASS_STAGE_PLANS[request_class])
        if not isinstance(plan, list) or plan != expected:
            raise GovernanceError(f"Stage plan for {request_class} must exactly match canonical policy.")
    if policy.get("extension_allowlists") != {"skills": [], "mcp_servers": [], "plugins": []}:
        raise GovernanceError("Studio extensions must remain empty; only SHA-verified injected agents are allowed.")
    if policy.get("external_actions_implemented") is not False:
        raise GovernanceError("External release/deployment actions must remain explicitly unimplemented.")
    protected = set((policy.get("branch_policy") or {}).get("protected_branches") or [])
    if "development" not in protected:
        raise GovernanceError("Studio protected branches must include development.")
    implementation = stages.get("implementation") or {}
    if implementation.get("agent") != TECHNICAL_LEAD_AGENT:
        raise GovernanceError("developer-team must remain the sole G5 technical-lead coordinator.")
    return policy


def stable_project_id(repository: str) -> str:
    canonical = os.path.normcase(os.path.realpath(str(repository or ""))).replace("\\", "/")
    return "proj_" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:20]


def classify_request(goal: str, project_facts: dict[str, Any]) -> str:
    """Classify scope without adding any authority or widening the original goal."""
    text = " ".join(str(goal or "").lower().split())
    explicit_release_rules = (
        ("HOTFIX", r"\bhot[ -]?fix\b|\bemergency patch\b"),
        ("RELEASE", r"\brelease\b|\bdeploy(?:ment)?\b|\bpublish\b|\bship to production\b"),
    )
    for request_class, pattern in explicit_release_rules:
        if re.search(pattern, text):
            return request_class
    if not bool(project_facts.get("has_project_files")):
        return "NEW_PROJECT"
    rules = (
        ("BUG_FIX", r"\bbug\b|\bfix\b|\bbroken\b|\bregression\b|\berror\b|\bcrash\b"),
        ("TECHNICAL_IMPROVEMENT", r"\brefactor\b|\bperformance\b|\btechnical debt\b|\bcleanup\b|\bharden\b|\boptimi[sz]e\b"),
        ("EXPERIMENT", r"\bexperiment\b|\bprototype\b|\bproof of concept\b|\bpoc\b|\bspike\b"),
        ("CONTINUATION", r"\bcontinue\b|\bresume\b|\bfinish the existing\b|\bpick up\b"),
        ("IDEA_REVISION", r"\brevise\b.{0,40}\bidea\b|\bpivot\b|\brethink\b|\bidea revision\b"),
        ("FEATURE_CHANGE", r"\bfeature\b|\benhancement\b|\badd support\b|\bnew capability\b"),
        ("CHANGE_REQUEST", r"\bchange request\b|\bmodify\b|\bupdate\b|\badjust\b|\bchange\b"),
    )
    for request_class, pattern in rules:
        if re.search(pattern, text):
            return request_class
    if re.search(r"\bnew project\b|\bfrom scratch\b|\bcreate\b|\bbuild\b", text):
        return "NEW_PROJECT"
    return "CHANGE_REQUEST"


def selected_stages(request_class: str, policy: dict[str, Any] | None = None) -> tuple[str, ...]:
    selected_policy = policy or load_policy()
    value = str(request_class or "").upper()
    if value not in REQUEST_CLASSES:
        raise GovernanceError(f"Unknown Studio request class: {value}")
    return tuple(selected_policy["request_class_stage_plans"][value])


def _parse_inline_list(raw: str) -> list[str]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    return [item.strip().strip("\"'") for item in next(csv.reader([inner], skipinitialspace=True)) if item.strip()]


def _scalar(raw: str) -> Any:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        return _parse_inline_list(value)
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if re.fullmatch(r"\d+", value):
        return int(value)
    return value.strip("\"'")


def _frontmatter(text: str) -> tuple[dict[str, Any], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise GovernanceError("Trusted agent is missing frontmatter.")
    try:
        end = next(index for index in range(1, len(lines)) if lines[index].strip() == "---")
    except StopIteration as exc:
        raise GovernanceError("Trusted agent frontmatter is not terminated.") from exc
    header: dict[str, Any] = {}
    index = 1
    while index < end:
        line = lines[index]
        match = re.match(r"^([A-Za-z][A-Za-z0-9]*):(?:\s*(.*))?$", line)
        if not match:
            index += 1
            continue
        key, raw = match.group(1), (match.group(2) or "")
        index += 1
        if raw in {">", ">-", "|", "|-"}:
            values: list[str] = []
            while index < end and (not lines[index].strip() or lines[index][0].isspace()):
                values.append(lines[index].strip())
                index += 1
            header[key] = " ".join(item for item in values if item)
            continue
        if raw == "":
            values = []
            while index < end and (not lines[index].strip() or lines[index][0].isspace()):
                item = lines[index].strip()
                if item.startswith("- "):
                    values.append(item[2:].strip().strip("\"'"))
                index += 1
            header[key] = values
            continue
        header[key] = _scalar(raw)
    return header, "\n".join(lines[end + 1:]).strip()


def load_trusted_agents(
    names: Iterable[str],
    policy: dict[str, Any] | None = None,
    *,
    authoritative_permission_mode: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Return canonical --agents JSON and SHA-verified provenance records."""
    selected_policy = policy or load_policy()
    configured = selected_policy.get("trusted_agents") or {}
    payload: dict[str, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []
    for raw_name in dict.fromkeys(str(item or "").strip() for item in names):
        if not _AGENT_NAME_RE.fullmatch(raw_name) or raw_name not in configured:
            raise GovernanceError(f"Untrusted Studio agent: {raw_name}")
        agent_policy = configured[raw_name]
        relative = str(agent_policy.get("file") or "")
        path = (_ROOT / relative).resolve()
        if path.parent != _TRUSTED_AGENT_ROOT or path.name != f"{raw_name}.md":
            raise GovernanceError(f"Agent path escapes the trusted repository roster: {raw_name}")
        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise GovernanceError(f"Trusted agent could not be read: {raw_name}") from exc
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        expected_digest = str(agent_policy.get("sha256") or "").lower()
        if not _SHA256_RE.fullmatch(expected_digest) or digest != expected_digest:
            raise GovernanceError(f"Trusted agent SHA-256 mismatch: {raw_name}")
        header, prompt = _frontmatter(source)
        required = {"name", "description", "tools", "model", "permissionMode", "maxTurns"}
        if required - set(header) or header.get("name") != raw_name or not prompt:
            raise GovernanceError(f"Trusted agent frontmatter is invalid: {raw_name}")
        tools = header.get("tools")
        allowed_tools = list(agent_policy.get("allowed_tools") or [])
        if not isinstance(tools, list) or tools != allowed_tools:
            raise GovernanceError(f"Trusted agent tool profile mismatch: {raw_name}")
        profile = str(agent_policy.get("tool_profile") or "")
        if profile not in {"read_only", "research", "implementation", "test"}:
            raise GovernanceError(f"Trusted agent tool profile is invalid: {raw_name}")
        if profile == "read_only" and tuple(tools) != READ_ONLY_TOOLS:
            raise GovernanceError(f"Read-only agent has non-read-only tools: {raw_name}")
        if profile == "research" and tuple(tools) != RESEARCH_TOOLS:
            raise GovernanceError(f"Research agent has tools outside the fixed research profile: {raw_name}")
        if profile in {"implementation", "test"}:
            permitted = _IMPLEMENTATION_TOOLS if profile == "implementation" else _TEST_TOOLS
            agent_tools = [tool for tool in tools if tool.startswith("Agent(")]
            ordinary_tools = [tool for tool in tools if not tool.startswith("Agent(")]
            if any(tool not in permitted for tool in ordinary_tools):
                raise GovernanceError(f"Agent has an unknown or forbidden tool: {raw_name}")
            if agent_tools and (raw_name != "developer-team" or agent_tools != [_DEVELOPER_AGENT_ALLOWLIST]):
                raise GovernanceError(f"Agent delegation allowlist is invalid: {raw_name}")
        header_permission = str(header.get("permissionMode") or "")
        if header_permission not in _PERMISSION_MODES:
            raise GovernanceError(f"Trusted agent permissionMode is invalid: {raw_name}")
        selected_permission = str(authoritative_permission_mode or header_permission)
        if selected_permission not in _PERMISSION_MODES:
            raise GovernanceError(f"Unsafe or invalid authoritative permission mode: {selected_permission}")
        # bypassPermissions = the agent runs everything (including Bash) with NO prompt.
        # That is what "auto mode, don't make me click yes" actually requires, but it is
        # also the widest blast radius in the system, so it stays OFF unless the operator
        # opts in explicitly with NEXI_STUDIO_UNATTENDED=1. It is never reachable by a
        # model: this is read from the environment, not from agent-supplied data.
        if selected_permission == "bypassPermissions" and not _unattended_enabled():
            raise GovernanceError(
                "bypassPermissions requires NEXI_STUDIO_UNATTENDED=1 (unattended writes are "
                "opt-in; acceptEdits still prompts for Bash)")
        max_turns = header.get("maxTurns")
        if not isinstance(max_turns, int) or isinstance(max_turns, bool) or not 1 <= max_turns <= 100:
            raise GovernanceError(f"Trusted agent maxTurns is invalid: {raw_name}")
        payload[raw_name] = {
            "description": str(header["description"]),
            "prompt": prompt,
            "tools": tools,
            "model": str(header["model"]),
            "permissionMode": selected_permission,
            "maxTurns": max_turns,
        }
        records.append({
            "name": raw_name,
            "path": relative.replace("\\", "/"),
            "sha256": digest,
            "tool_profile": profile,
        })
    if not payload:
        raise GovernanceError("At least one trusted agent is required.")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")), records
