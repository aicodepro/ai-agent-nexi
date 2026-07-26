#!/usr/bin/env python3
"""Build config/agents/catalog.json - the single canonical agent source.

The catalog is authored here as compact tuples and emitted as JSON so the 63
entries stay reviewable. Everything downstream (.claude/agents, .opencode/agents,
runtime registry, permission matrix, UI cards) is generated from the emitted
JSON by scripts/compile_agent_catalog.py - never hand-maintained.

Run:  python scripts/build_agent_catalog.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "config" / "agents" / "catalog.json"

# Stage owners that engine/studio/governance.py already enforces. The catalog
# must AGREE with this map; the compiler asserts it rather than redefining it.
GOVERNANCE_STAGE_OWNERS = {
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

# id, name, class, permission_intent, responsibility, output
RUNTIME_AGENTS = [
    ("R01", "nexi-executive-supervisor", "orchestrator", "plan",
     "Own the user goal, choose the next specialist, combine verified results, keep one authoritative run state.",
     "GoalPlan + DelegationPlan + final verified response"),
    ("R02", "intent-planner", "routing", "plan",
     "Convert natural language into a structured goal, subgoals, candidate capabilities, missing fields, risk and success conditions.",
     "RouteDecision JSON"),
    ("R03", "conversation-clarifier", "dialogue", "plan",
     "Ask the minimum typed clarification and bind the reply to an expected schema.",
     "ClarificationRequest / ClarificationResolution"),
    ("R04", "desktop-control-agent", "action", "ask",
     "Operate Windows applications through UI Automation first, input only as fallback, never claiming success without independent verification.",
     "ActionPlan + ToolResult evidence"),
    ("R05", "browser-control-agent", "action", "ask",
     "Navigate, fill, click and submit through semantic locators; detect ambiguity and verify resulting state.",
     "BrowserActionResult + verifier evidence"),
    ("R06", "screen-understanding-agent", "perception", "plan",
     "Build ScreenState from accessibility tree, OCR and vision fallback without acting.",
     "ScreenState + candidate targets"),
    ("R07", "live-intelligence-agent", "research", "plan",
     "Search, open sources, extract content, rank authority and freshness, compare claims and produce citations.",
     "EvidenceReport with timestamps and citations"),
    ("R08", "productivity-agent", "action", "ask",
     "Handle email, calendar, contacts and files through bounded connectors with explicit confirmation for irreversible actions.",
     "ProductivityActionResult"),
    ("R09", "media-control-agent", "action", "ask",
     "Search and rank tracks, playlists and devices, clarify close matches, control playback and verify player state.",
     "PlaybackResult + state evidence"),
    ("R10", "developer-workspace-agent", "bridge", "ask",
     "Validate CLI, auth and project, create or resume a named session, and delegate coding work to the selected runtime.",
     "RuntimeDispatch + live trace"),
    ("R11", "workflow-automation-agent", "planner", "ask",
     "Compose reusable multi-step workflows with retries, timeouts, compensation and approval gates.",
     "WorkflowDefinition + execution trace"),
    ("R12", "accessibility-companion-agent", "assistance", "plan",
     "Provide eyes-free guidance, announce state and errors, and adapt verbosity for screen-reader and keyboard-only use.",
     "AccessibleGuidanceResponse"),
    ("R13", "memory-context-agent", "context", "write",
     "Retrieve relevant context, separate durable from temporal facts, expire stale state and summarise with provenance.",
     "ContextPack + MemoryWriteProposal"),
    ("R14", "system-health-recovery-agent", "operations", "ask",
     "Check microphone, wake engine, TTS, browser, CLIs and MCP servers; isolate root cause and perform bounded reversible repairs.",
     "HealthReport + RecoveryPlan"),
    ("R15", "privacy-approval-explainer", "risk", "plan",
     "Explain why an action needs approval, summarise data leaving the device and present allow-once/always/deny.",
     "ApprovalExplanation"),
]

# id, name, domain, stage, permission_intent, responsibility
STUDIO_AGENTS = [
    ("S01", "project-strategist", "strategy", "advisory", "plan", "Objectives, success metrics, non-goals, assumptions and risks."),
    ("S02", "business-analyst", "requirements", "requirements", "plan", "Versioned requirements, rules, actors, permissions, failure cases and acceptance candidates."),
    ("S03", "ux-researcher", "requirements", "requirements", "plan", "User journeys, task analysis, usability risks and evidence-backed design hypotheses."),
    ("S04", "accessibility-architect", "requirements", "requirements", "plan", "Keyboard, screen-reader, voice, contrast, text-size and assistive-technology requirements."),
    ("S05", "research-analyst", "research", "research", "plan", "Current primary-source research with citations, confidence, conflicts and open questions."),
    ("S06", "codebase-analyst", "research", "research", "plan", "Architecture map, dependency graph, entry points and change-impact report."),
    ("S07", "dependency-supply-chain-analyst", "research", "research", "plan", "Dependency inventory, license and provenance review, lockfile and update strategy."),
    ("S08", "solution-architect", "architecture", "architecture", "plan", "Selected design, interfaces, trust boundaries, migration, rollback and failure modes."),
    ("S09", "mcp-tool-architect", "architecture", "architecture", "plan", "MCP server and tool contracts, auth, schemas, consent, rate limits and timeouts."),
    ("S10", "skill-capability-designer", "architecture", "architecture", "plan", "Reusable skills, triggers, inputs, evaluations and cross-CLI compatibility."),
    ("S11", "product-manager", "planning", "sprint_plan", "plan", "Prioritised delivery slices, dependencies, acceptance IDs and definition of done."),
    ("S12", "developer-team", "lead", "implementation", "acceptEdits", "Partition implementation, delegate non-overlapping specialists and reconcile interfaces."),
    ("S13", "frontend-engineer", "implementation", "implementation", "write", "Client state, components, forms, loading and error states, accessibility and frontend tests."),
    ("S14", "backend-engineer", "implementation", "implementation", "write", "APIs, services, data contracts, retries, idempotency and authorization."),
    ("S15", "design-engineer", "implementation", "implementation", "write", "Design-system components, responsive behaviour, keyboard and focus semantics."),
    ("S16", "desktop-automation-engineer", "implementation", "implementation", "write", "Windows UI Automation adapters, control patterns, fallback input and verification seams."),
    ("S17", "browser-automation-engineer", "implementation", "implementation", "write", "Playwright semantic locators, ambiguity resolution and postcondition verification."),
    ("S18", "voice-realtime-engineer", "implementation", "implementation", "write", "Wake, VAD, ASR, TTS, barge-in, audio-device recovery and live-voice adapters."),
    ("S19", "llm-routing-engineer", "implementation", "implementation", "write", "Structured routing, capability retrieval, plan validation and model policies."),
    ("S20", "agent-runtime-engineer", "implementation", "implementation", "write", "Claude Code and OpenCode adapters, session resume, event normalisation and isolation."),
    ("S21", "mcp-integration-engineer", "implementation", "implementation", "write", "MCP client and server integration, auth flow, timeouts, retries and audit logging."),
    ("S22", "data-memory-engineer", "implementation", "implementation", "write", "Run ledger, project memory, temporal expiry, migrations, retrieval and redaction."),
    ("S23", "devops-engineer", "implementation", "implementation", "write", "Reproducible environments, dependency groups, CI matrix and build diagnostics."),
    ("S24", "observability-engineer", "implementation", "implementation", "write", "Structured events, traces, metrics, correlation IDs and failure diagnostics."),
    ("S25", "performance-engineer", "implementation", "implementation", "write", "Latency budgets, profiling, concurrency and load-test harnesses."),
    ("S26", "security-remediation-engineer", "implementation", "implementation", "write", "Fix authorised security findings without self-approving, preserving tests and evidence."),
    ("S27", "migration-refactor-engineer", "implementation", "implementation", "write", "Consolidate duplicate routing, state and memory systems behind compatibility layers."),
    ("S28", "root-cause-debugger", "implementation", "implementation", "write", "Form competing hypotheses, reproduce failures, make the smallest fix and keep regression tests."),
    ("S29", "documentation-engineer", "docs", "implementation", "write", "Keep README, architecture, operations and API documentation aligned with behaviour."),
    ("S30", "source-control-coordinator", "git", "external", "ask", "Prepare branches, commits and PR metadata; never approve or merge its own work."),
    ("S31", "test-engineer", "tests", "developer_tests", "write", "Deterministic happy, edge, failure, recovery and permission tests with preserved evidence."),
    ("S32", "qa-verifier", "acceptance", "qa", "plan", "Map every acceptance criterion to PASS/FAIL/UNVERIFIED/NOT_RUN using bound evidence."),
    ("S33", "accessibility-verifier", "acceptance", "qa", "plan", "Keyboard, focus, screen-reader, text-scaling and reduced-motion checks."),
    ("S34", "security-reviewer", "security", "security_review", "plan", "Threat model, auth, secrets, prompt injection, tool abuse and data-flow review."),
    ("S35", "integration-verifier", "integration", "integration", "plan", "Contract, build, startup and smoke checks with current-SHA evidence."),
    ("S36", "performance-verifier", "integration", "integration", "plan", "Validate latency, throughput, memory and cancellation budgets without editing code."),
    ("S37", "repository-hygiene-auditor", "release", "release", "plan", "Detect generated or private data, missing source, machine paths and packaging drift."),
    ("S38", "release-manager", "release", "release", "plan", "Assess checks, versioning, changelog, rollback and reviewer independence; never self-release."),
    ("S39", "knowledge-curator", "closeout", "closeout", "plan", "Provenance-linked closeout, decision log, evidence index and reusable project memory."),
]

# id, name, responsibility, implemented_by (empty string = NOT yet a single authority)
CONTROLLERS = [
    ("C01", "session-controller", "Owns wake/listen/think/speak/cooldown/barge-in generations and stale-event rejection.", "engine/wake_session_manager.py"),
    ("C02", "transcript-decision-engine", "Classifies complete, incomplete, cut-off, noise, continuation and typed short answers.", "engine/transcript_filter.py"),
    ("C03", "policy-authorization-engine", "Enforces allow/ask/deny, project scope, risk and irreversible-action gates.", "engine/approval_queue.py"),
    ("C04", "capability-registry", "Versioned input schema, platform, dependencies, risk, verifier, timeout and undo per capability.", "engine/tool_registry.py"),
    ("C05", "executor", "Runs a validated capability with timeouts, cancellation, idempotency and bounded output.", "engine/tool_registry.py"),
    ("C06", "verifier-registry", "Independently verifies tool outcomes; handlers never verify themselves.", "engine/tool_result_verifier.py"),
    ("C07", "response-coordinator", "Only component allowed to speak, emit terminal state, request follow-up or end a turn.", "engine/response_coordinator.py"),
    ("C08", "accessible-ui-store", "Accepts only sequenced backend events and exposes screen-reader-safe state.", "engine/ui_state_manager.py"),
    ("C09", "run-ledger", "Persists sessions, turns, tool events, approvals, diffs, evidence, costs and provenance.", ""),
]

VERSION = "1.0.0"


def _entry(**kw) -> dict:
    body = json.dumps(kw, sort_keys=True).encode()
    kw["sha256"] = hashlib.sha256(body).hexdigest()
    return kw


def build() -> dict:
    runtime = [
        _entry(id=i, name=n, version=VERSION, agent_class=c, platform="nexi",
               permission_intent=perm, description=resp, output=out,
               stage="runtime", tools=[], skills=[], mcp_servers=[], delegates=[],
               risk="high" if perm in {"ask", "write"} else "low",
               approval_policy="per_action" if perm == "ask" else "none",
               timeout_seconds=120, max_turns=8, memory_scope="session",
               verifier="verifier-registry", owner="nexi-runtime", status="specified")
        for i, n, c, perm, resp, out in RUNTIME_AGENTS
    ]
    studio = [
        _entry(id=i, name=n, version=VERSION, agent_class="studio", platform="claude+opencode",
               permission_intent=perm, description=resp, output="StageArtifact",
               stage=stage, domain=dom, tools=[], skills=[], mcp_servers=[], delegates=[],
               risk="medium" if perm in {"write", "acceptEdits"} else "low",
               approval_policy="gate" if perm != "plan" else "none",
               timeout_seconds=600, max_turns=20, memory_scope="project",
               verifier="qa-verifier", owner="nexi-studio",
               status="existing" if i in {"S01","S02","S05","S08","S11","S12","S13","S14","S15","S23","S31","S32","S34","S35","S38","S39"} else "new")
        for i, n, dom, stage, perm, resp in STUDIO_AGENTS
    ]
    controllers = [
        _entry(id=i, name=n, version=VERSION, agent_class="deterministic_controller",
               platform="nexi", permission_intent="code_only", description=resp,
               implemented_by=impl, status="implemented" if impl else "not_implemented",
               note="Deterministic Python service. Must never become an LLM persona.")
        for i, n, resp, impl in CONTROLLERS
    ]
    return {
        "schema_version": 1,
        "catalog_version": VERSION,
        "principles": [
            "Nexi Python is the only authorization and gate authority.",
            "Execution and verification are separate.",
            "Only ResponseCoordinator may speak or close a turn.",
            "One canonical catalog generates Nexi, Claude Code and OpenCode definitions.",
            "Read-only analysis and write-enabled implementation are separate roles.",
        ],
        "governance_stage_owners": GOVERNANCE_STAGE_OWNERS,
        "runtime_agents": runtime,
        "studio_agents": studio,
        "deterministic_controllers": controllers,
    }


def main() -> int:
    catalog = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    print(f"  runtime agents : {len(catalog['runtime_agents'])}")
    print(f"  studio agents  : {len(catalog['studio_agents'])}")
    print(f"  controllers    : {len(catalog['deterministic_controllers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
