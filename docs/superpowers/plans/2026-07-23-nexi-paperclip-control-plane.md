# Nexi Paperclip Control Plane Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Nexi to a separately deployed Paperclip instance through a typed, fail-closed control-plane adapter, with durable policy and approval state, governed workers, voice/UI controls, verification, and gated release operations.

**Architecture:** Nexi remains the user-facing cognitive and desktop authority. Paperclip owns company execution state, while `engine/integrations/paperclip/` normalizes its API and enforces Nexi policy before mutations. Capability modes are separate: `read`, `approved_mutate`, `full_auto`, and `release`. An installed-version report can permit reads or scoped, explicitly approved mutations without permitting autonomous execution; full auto additionally requires synchronous mutation and execution enforcement.

**Tech Stack:** Python 3.12, `requests`, dataclasses, atomic JSON persistence, pytest, Eel/vanilla JavaScript, Paperclip server 0.3.1, Paperclip plugin SDK 1.0.0, TypeScript/Vitest.

## Global Constraints

- Preserve `engine/command.py::allCommands` routing order and ImportError fallbacks.
- Do not call Paperclip during import, wake detection, sleep detection, or unrelated personal commands.
- Default Paperclip API origin is exactly `http://127.0.0.1:3100/api`; reject non-loopback hosts and redirects.
- Set `requests.Session.trust_env = False`, connect timeout to 2 seconds, response timeout to 10 seconds, and maximum response body to 1 MiB.
- Never log Paperclip credentials, cookies, request bodies, response bodies, or unredacted worker evidence.
- Persist non-secret Paperclip state only under ignored `data/paperclip/` using atomic replace.
- Never reuse `engine/approval_queue.py` capabilities for Paperclip approvals.
- Never expose a generic public HTTP method or caller-selected Paperclip path.
- Never silently fall back from Paperclip mode to local Studio execution.
- Keep Paperclip IDs opaque; do not convert them into `wf_*` IDs.
- Do not label host-local worktree execution as automatic containment.
- Run Paperclip and all local plugins under a separate ACL-restricted service account before trusting process isolation; plugin manifest capabilities are not an OS sandbox.
- Paperclip `done` maps to `verification_pending` until Nexi's verifier accepts independent evidence.
- Do not commit, push, merge, install, deploy, or alter secrets unless Darsh explicitly authorizes that operation.
- Compatibility baseline for planning is official Paperclip commit `ad74fb5450258f5d09ff7df2f695cc0ba525bf78`, server `0.3.1`, plugin SDK `1.0.0`.
- The baseline plugin SDK has no synchronous pre-mutation or pre-dispatch authorization hook; tests must report this as a hard blocker for full auto rather than weaken the approved design.

---

## Increment A: Deployment And Compatibility

### Task 1: Installed-Version Compatibility Report

**Files:**
- Create: `engine/integrations/paperclip/__init__.py`
- Create: `engine/integrations/paperclip/contracts.py`
- Create: `engine/integrations/paperclip/compatibility.py`
- Create: `scripts/paperclip_compatibility_check.py`
- Create: `tests/test_paperclip_compatibility.py`

**Interfaces:**
- Produces: `CompatibilityCapability(name: str, supported: bool, evidence: str)`.
- Produces: `PaperclipCompatibilityReport(server_version: str, plugin_sdk_version: str, source_revision: str, checked_at: str, capabilities: tuple[CompatibilityCapability, ...])`.
- Produces: `PaperclipCompatibilityReport.allows(mode: str) -> bool`, where modes are `read`, `full_auto`, and `release`, plus `allows_operation(operation: str) -> bool` for explicitly approved mutations.
- Produces report provenance: API origin, server boot identity, server/source version, credential principal ID and capability digest, OpenAPI digest, governance plugin ID/version/digest, sandbox profile digest, checked-at time, and expiry.
- Produces: `build_report(probes: CompatibilityProbes) -> PaperclipCompatibilityReport`; `CompatibilityProbes` contains health, OpenAPI, authenticated-principal, plugin, workspace, sandbox, control, backup/restore, rollback, and runtime behavior evidence.
- Produces: `CompatibilityReportVerifier.verify_against_live_server(report, client) -> VerifiedCompatibility`, required before every mutation and cached for at most 30 seconds. Offline fixtures always set `activatable=false`.

- [ ] **Step 1: Write failing compatibility tests**

Test exact detection of health, authenticated/private mode, loopback origin, companies, projects, issues, activity, approvals, costs, tree holds, execution workspaces, sandbox driver, cancellation, event cursors, metadata correlation, idempotency, plugin API routes, plugin host capabilities, synchronous pre-mutation authorization, synchronous pre-dispatch lease authorization, backups, and migration rollback. Assert an operation is enabled only when its exact route/schema, principal authorization, idempotency/reconciliation probe, write-ahead recovery, backup restore, and migration rollback proof pass. Assert `full_auto=False` when either synchronous hook is absent. Reject expired, unsigned, fixture-only, or stale reports whose origin, server boot ID, principal digest, OpenAPI digest, plugin digest, or sandbox digest differs from live probes.

- [ ] **Step 2: Run the focused test and verify failure**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_compatibility.py -v`

Expected: collection fails because `engine.integrations.paperclip.compatibility` does not exist.

- [ ] **Step 3: Implement immutable report contracts and capability matrix**

Use frozen dataclasses, reject duplicate capability names, and implement mode requirements as checked-in constants:

```python
MODE_REQUIREMENTS = {
    "read": frozenset({"health", "authenticated_private", "companies_read", "issues_read"}),
    "full_auto": frozenset({"governance_plugin_digest", "actor_restrictions", "policy_digest_enforcement", "synchronous_pre_mutation_hook", "synchronous_pre_dispatch_hook", "sandbox_driver", "lease_expiry_cancellation", "atomic_budget_reservation", "worker_capability_drift_gate", "backup_restore_probe", "migration_rollback_probe"}),
    "release": frozenset({"verified_evidence", "release_gateway", "rollback_probe"}),
}
OPERATION_REQUIREMENTS = {
    "pause_mission": frozenset({"route:tree_hold_pause", "principal:tree_hold_pause", "reconcile:tree_hold_pause"}),
    "cancel_mission": frozenset({"route:tree_hold_cancel", "principal:tree_hold_cancel", "reconcile:tree_hold_cancel"}),
}
MUTATION_BASE_REQUIREMENTS = frozenset({"metadata_correlation", "write_ahead_recovery", "backup_restore_probe", "migration_rollback_probe"})
```

- [ ] **Step 4: Implement the offline and live report command**

The script accepts `--base-url`, `--fixture-dir`, and `--output`. It reads the credential only from `PAPERCLIP_API_TOKEN`, prints no token or response body, writes redacted JSON, and exits `0` for a valid report or `2` for malformed/unreachable input. Live mode probes health, OpenAPI, `/cli-auth/me`, plugin inspection/health, selected company access, issue metadata round-trip in a disposable company, tree controls, workspaces, sandbox selection, cancellation, costs, approvals, backup status, and runtime idempotency. Destructive probes require `--disposable-company-id`. Restore and migration-rollback evidence is signed by a local compatibility signing key from the OS secret store and bound to instance ID, data directory digest, server revision, test time, and result digest. The final report is signed by the same trust root; fixture reports are never activatable.

- [ ] **Step 5: Verify the current upstream compatibility gate**

Run the focused tests with a fixture matching server `0.3.1` and SDK `1.0.0`.

Expected: report generation passes; `full_auto` is false because no synchronous pre-mutation or general pre-dispatch hook exists. A plugin environment driver may prove synchronous pre-adapter execution for its own environment, but that evidence cannot satisfy either missing general hook.

### Task 2: Deployment And Recovery Harness

**Files:**
- Create: `scripts/paperclip_deployment_check.ps1`
- Create: `scripts/paperclip_backup_restore_check.ps1`
- Create: `tests/test_paperclip_deployment_scripts.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: environment keys `NEXI_CONTROL_PLANE`, `PAPERCLIP_BASE_URL`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_API_TOKEN`, `PAPERCLIP_COMPATIBILITY_REPORT`, and `PAPERCLIP_WORKER_STAGING_ROOT`.

- [ ] **Step 1: Test scripts as text and mocked subprocess contracts**

Assert they require `authenticated/private`, `server.bind=loopback`, telemetry disabled, database backup output outside the live data directory, a successful disposable restore, and a failed-migration rollback proof. Assert they never echo token-valued environment variables.

- [ ] **Step 2: Implement non-destructive checks**

`paperclip_deployment_check.ps1` runs `paperclipai doctor`, validates health JSON, verifies `127.0.0.1:3100`, and writes a report. It must not install or start Paperclip. `paperclip_backup_restore_check.ps1` requires explicit `-DisposableDataDir` and refuses the live configured directory.

- [ ] **Step 3: Document only non-secret configuration in `.env.example`**

Use empty token/company values and defaults:

```text
NEXI_CONTROL_PLANE=local_legacy
PAPERCLIP_BASE_URL=http://127.0.0.1:3100/api
PAPERCLIP_COMPANY_ID=
PAPERCLIP_API_TOKEN=
PAPERCLIP_COMPATIBILITY_REPORT=data/paperclip/compatibility.json
PAPERCLIP_WORKER_STAGING_ROOT=
```

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_deployment_scripts.py -v`

Expected: all tests pass without a live Paperclip instance.

## Increment B: Typed Read Integration

### Task 3: Hardened HTTP Client

**Files:**
- Create: `engine/integrations/paperclip/client.py`
- Create: `tests/test_paperclip_client.py`

**Interfaces:**
- Produces: `PaperclipClient(base_url: str, token: str, *, session: requests.Session | None = None)`.
- Produces typed methods: `health()`, `openapi()`, `current_principal()`, `list_companies()`, `get_company(company_id)`, `list_projects(company_id)`, `get_issue(issue_id)`, `list_issue_activity(issue_id)`, `list_company_activity(company_id, after=None)`, `list_issue_runs(issue_id)`, `list_issue_documents(issue_id)`, `list_issue_work_products(issue_id)`, `list_agents(company_id)`, `list_approvals(company_id)`, and `list_costs(company_id)`.
- Produces normalized `PaperclipError(code, status, retryable, reconciliation_required)`.

- [ ] **Step 1: Write transport security tests**

Cover loopback validation, DNS/IPv6 loopback forms, userinfo rejection, query/fragment rejection, `trust_env=False`, no redirects, bounded streamed reads, JSON content type, timeouts, token-origin binding, credential redaction, malformed JSON, and normalized `401/403/404/409/429/5xx` behavior.

- [ ] **Step 2: Implement one private `_request` method**

Only typed methods may call it. Use `allow_redirects=False`, `stream=True`, `timeout=(2.0, 10.0)`, a 1 MiB byte counter, and `Authorization: Bearer ...`. Reject every `3xx` before reading a target location.

- [ ] **Step 3: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_client.py -v`

Expected: all client tests pass and no secret appears in captured logs.

### Task 4: Mission Store, Mapper, And Read Service

**Files:**
- Create: `engine/integrations/paperclip/mission_store.py`
- Create: `engine/integrations/paperclip/mapper.py`
- Create: `engine/integrations/paperclip/service.py`
- Create: `tests/test_paperclip_mission_store.py`
- Create: `tests/test_paperclip_mapper.py`
- Create: `tests/test_paperclip_read_service.py`

**Interfaces:**
- Produces all normalized frozen contracts required by the specification: `PaperclipHealth`, `CompanyRef`, `MissionEnvelope`, `MissionRecord`, `MissionPolicyRevision`, `AuthorityLease`, `MissionRef`, `ProjectRef`, `WorkItem`, `WorkEvent`, `WorkerSummary`, `BudgetSummary`, `ApprovalRequest`, `OperationRequest`, `OperationDecision`, `OperationResult`, `ReconciliationResult`, `DataEgressPolicy`, and `BudgetPolicy`.
- Produces: `MissionStore(path).create(record)`, `.get(mission_id)`, `.latest()`, `.list_non_terminal()`, `.append_revision()`, and `.update_reconciliation()`.
- Produces: `PaperclipService.status(mission_id=None)`, `.activity(mission_id=None)`, `.logs(mission_id=None)`, `.artifacts(mission_id=None)`, `.budgets(mission_id=None)`, and `.pending_approvals(mission_id=None)`.

- [ ] **Step 1: Write restart, corruption, and state mapping tests**

Verify atomic temp-file replacement, an inter-process file lock, compare-and-swap mission revisions, restrictive Windows-readable state, schema version checks, corrupt-file quarantine without authority reconstruction, Paperclip state mapping, unknown-state fail closure, event length bounds, secret redaction, synthetic `(createdAt, id)` high-water deduplication when the installed API has no native cursor, and `done -> verification_pending`.

- [ ] **Step 2: Implement the normalized contracts and mapper**

The mapper accepts only known response fields, caps IDs at 128 characters, text at 500 characters, list counts at 100, and timestamps as timezone-aware ISO-8601 strings.

- [ ] **Step 3: Implement read-only service composition**

The service loads the compatibility report first, requires `allows("read")`, resolves external IDs from `MissionStore`, and never reconstructs mission authority from Paperclip or memory.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_mission_store.py tests/test_paperclip_mapper.py tests/test_paperclip_read_service.py -v`

Expected: all tests pass.

## Increment C: Governance Enforcement

### Task 5: Deterministic Policy Registries And Audit

**Files:**
- Create: `config/paperclip/operation_policy.json`
- Create: `config/paperclip/protected_paths.json`
- Create: `config/paperclip/network_allowlist.json`
- Create: `config/paperclip/supply_chain_policy.json`
- Create: `config/paperclip/data_egress_policy.json`
- Create: `engine/integrations/paperclip/policy.py`
- Create: `engine/integrations/paperclip/audit.py`
- Create: `tests/test_paperclip_policy.py`
- Create: `tests/test_paperclip_audit.py`

**Interfaces:**
- Produces: `OperationRequest`, `OperationDecision`, `DataEgressPolicy`, and `BudgetPolicy`.
- Produces: `PolicyEngine.evaluate(request) -> OperationDecision` with exactly `AUTO`, `ASK`, or `FORBIDDEN`.
- Produces: `BridgeAuditLedger.append(event) -> str` returning an event digest.

- [ ] **Step 1: Write the complete policy matrix tests**

Test every AUTO, ASK, and FORBIDDEN class from the design. Unknown operation, path, host, package action, provider, and data classification must be ASK. Explicit Nexi tool access, active-checkout access, secret access, destructive Git, control disabling, live self-modification, replication, wallets, and silent fallback must be FORBIDDEN.

- [ ] **Step 2: Add closed registries**

Use versioned JSON objects with sorted arrays and SHA-256 digest validation. Do not accept free-form model risk labels.

- [ ] **Step 3: Implement append-only redacted audit**

Write canonical JSONL under an inter-process lock with a hash chain, event ID, previous digest, policy revision, decision, operation digest, external IDs, result state, and timestamps. Verify the chain on startup, quarantine a torn tail, and require compare-and-swap revisions for concurrent writers. On write failure, the policy layer blocks high-risk mutations.

- [ ] **Step 4: Run policy and audit tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_policy.py tests/test_paperclip_audit.py -v`

Expected: all tests pass.

### Task 6: Approval Capabilities And Attention Deduplication

**Files:**
- Create: `engine/integrations/paperclip/approvals.py`
- Create: `engine/integrations/paperclip/attention.py`
- Create: `tests/test_paperclip_approvals.py`
- Create: `tests/test_paperclip_attention.py`

**Interfaces:**
- Produces: `ApprovalCapabilityStore.issue(...)`, `.begin(approval_id)`, `.mark_applied()`, `.mark_rejected()`, `.mark_unknown()`, `.reconcile_pending()`.
- Produces: states `pending`, `in_flight`, `applied`, `rejected`, `unknown`, `expired`, and `superseded`.
- Produces: `AttentionManager.ingest(event) -> AttentionDecision`.

- [ ] **Step 1: Test canonical binding, expiry, assurance, and crash recovery**

Verify sorted canonical JSON, five-minute default expiry, one use, exact target/effect/cost/rollback text, voice assurance restrictions, write-ahead before mutation, timeout to unknown, restart reconciliation, and suppression of equivalent capabilities.

- [ ] **Step 2: Implement separate Paperclip capability persistence**

Use `secrets.token_urlsafe(32)` for approval IDs and SHA-256 only for argument digests. Never import or call `engine.approval_queue`.

- [ ] **Step 3: Implement attention grouping**

Group by stable mission, external target, operation, and argument digest. Emit one first prompt, one cooldown reminder, and one escalation; aggregate concurrent budget requests without widening each capability.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_approvals.py tests/test_paperclip_attention.py -v`

Expected: all tests pass.

### Task 7: Paperclip Governance Plugin And Hard Activation Gate

**Files:**
- Create: `external/paperclip-nexi-governance/package.json`
- Create: `external/paperclip-nexi-governance/tsconfig.json`
- Create: `external/paperclip-nexi-governance/src/manifest.ts`
- Create: `external/paperclip-nexi-governance/src/worker.ts`
- Create: `external/paperclip-nexi-governance/src/lease.ts`
- Create: `external/paperclip-nexi-governance/src/policy.ts`
- Create: `external/paperclip-nexi-governance/tests/plugin.test.ts`
- Modify: `engine/integrations/paperclip/compatibility.py`

**Interfaces:**
- Produces company-scoped plugin API routes `GET /leases/:missionId`, `POST /leases/:missionId`, `PATCH /leases/:missionId`, and `DELETE /leases/:missionId` with company ID resolution, actor, policy digest, worker capability digest, sandbox profile, and expiry validation.
- Produces scheduled lease-expiry reconciliation that marks plugin lease state expired, records activity, pauses supported managed agents, and requests issue updates. It must not claim tree-hold creation or heartbeat-run cancellation because SDK 1.0.0 exposes neither operation to plugins.
- Does not claim synchronous dispatch enforcement unless Paperclip exposes and passes the required host hook.

- [ ] **Step 1: Write plugin unit tests using `@paperclipai/plugin-sdk/testing`**

Test signature/digest validation, stale revision rejection, actor rejection, expiry state transition, supported agent-pause requests, Board override invalidation request, secret redaction, and inability to grant broader capabilities.

- [ ] **Step 2: Implement the least-capability manifest**

Export a compiled manifest module through `package.json.paperclipPlugin.manifest`. Request only plugin state, API route, job, issue subtree read, issue update, agent pause, and activity log capabilities actually used. Do not request outbound HTTP, secrets, local folders, agent tools, or environment drivers. Run the plugin process under the Paperclip ACL-restricted service account because these manifest capabilities do not sandbox ordinary Node APIs.

- [ ] **Step 3: Implement lease state and expiry reconciliation**

Store leases in plugin state, compare timestamps monotonically where available, and treat missing/invalid state as expired. The scheduled job is recovery defense only, not proof of synchronous mutation or scheduling enforcement. Do not pretend an `environment_driver` can wrap a real sandbox provider: future full auto requires either a complete governance-aware sandbox provider or an upstream synchronous interceptor around the selected Kubernetes/sandbox provider.

- [ ] **Step 4: Keep full auto disabled on SDK 1.0.0**

Update compatibility evidence so post-event subscriptions and scheduled jobs do not satisfy `synchronous_pre_mutation_hook` or `synchronous_pre_dispatch_hook`.

- [ ] **Step 5: Run plugin and Python compatibility tests**

Run: `pnpm --dir external/paperclip-nexi-governance test`

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_compatibility.py -v`

Expected: plugin tests pass; baseline full-auto activation remains denied.

## Increment D: Mission And Work Control

### Task 8: Idempotent Mission Mutations And Reconciliation

**Files:**
- Modify: `engine/integrations/paperclip/client.py`
- Modify: `engine/integrations/paperclip/service.py`
- Modify: `engine/integrations/paperclip/mission_store.py`
- Create: `engine/integrations/paperclip/leases.py`
- Create: `engine/integrations/paperclip/emergency_bridge.py`
- Modify: `engine/control/safety.py`
- Create: `tests/test_paperclip_mutations.py`
- Create: `tests/test_paperclip_controls.py`
- Create: `tests/test_paperclip_leases.py`

**Interfaces:**
- Produces: `create_or_reuse_mission(envelope)`, `pause_mission()`, `resume_mission()`, `cancel_mission()`, `retry_work_item()`, `reassign_work_item()`, `respond_to_approval()`, and `reconcile()`.
- Produces stable `idempotency_fingerprint(mission_id, operation, target_id, arguments, plan_revision=None)`.
- Produces: `AuthorityLeaseManager.issue()`, `.refresh()`, `.revoke()`, `.reconcile()`, and `.on_emergency_stop()`.
- Produces typed client methods for plugin lease create/read/update/revoke, each bound to company and mission IDs.

- [ ] **Step 1: Write mocked HTTP mutation tests**

Cover full `MissionEnvelope` validation and persistence, exact-once project/root issue creation, durable metadata correlation, timeouts, `409`, `404`, partial tree acknowledgments, repeated terminal controls, active-owner retry refusal, allowed-template reassignment, approval unknown state, lease signing/refresh/revocation, template/provider/sandbox digest drift, emergency stop, key rotation freeze, and no duplicate mutation.

- [ ] **Step 2: Add only explicit typed mutation methods**

Use current installed OpenAPI routes. Every explicitly approved one-shot mutation requires `CompatibilityReportVerifier.verify_against_live_server(...)`, operation-specific `allows_operation(operation)`, an `ASK` decision with a valid one-use capability, durable write-ahead state, backup/restore and rollback proof, exact route/principal authorization, and native idempotency or operation-specific reconciliation. An `AUTO` decision requires `allows("full_auto")`.

Paperclip 0.3.1 may enqueue implicit wakes after approval resolution, assignment/reassignment, resume/status changes, comments, and accepted-plan decomposition. Classify these as dispatching operations and require `full_auto`; do not expose them through one-shot mutation authority. Keep approval relay, retry, reassign, resume, assigned issue creation, and accepted-plan decomposition disabled on the baseline. Pause/cancel may be enabled only if their exact operation probes pass and they cannot enqueue new work. Because 0.3.1 Board keys are not route-scoped, affected Board-only operations remain disabled unless a future installed version proves a least-privileged service principal; one-company Board membership is not represented as equivalent proof.

- [ ] **Step 3: Implement lease lifecycle and emergency revocation**

Load a signing key only from the OS secret store or ignored local configuration, bind leases to mission revision, operation classes, immutable worker/template/provider/tool/sandbox/egress digests, and use a short configured expiry. Refresh only healthy enabled missions. Add a small callback registration API to `EmergencyStop`; callbacks run after releasing its lock. The Paperclip callback revokes local lease state first, then sends bounded pause/cancel requests without blocking the emergency-stop caller.

- [ ] **Step 4: Implement budget hard stops**

Require a nonzero budget before paid execution. Treat Paperclip budget reservation support as mandatory for automatic dispatch; delayed costs reduce future availability and never authorize an overspend.

- [ ] **Step 5: Run focused mutation tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_mutations.py tests/test_paperclip_controls.py tests/test_paperclip_leases.py -v`

Expected: all tests pass against mocks; live mutation remains disabled if Increment A requirements fail.

## Increment E: Sandboxed Coding Workforce

### Task 9: Workspace Boundary And Hostile Evidence Verification

**Files:**
- Create: `engine/integrations/paperclip/workspaces.py`
- Create: `engine/integrations/paperclip/evidence.py`
- Create: `engine/integrations/paperclip/verifier_sandbox.py`
- Create: `config/paperclip/trusted_test_manifests.json`
- Create: `tests/test_paperclip_workspaces.py`
- Create: `tests/test_paperclip_evidence.py`
- Create: `tests/test_paperclip_verifier_sandbox.py`

**Interfaces:**
- Produces: `WorkspacePolicy.validate(workspace, repository) -> WorkspaceDecision`.
- Produces: `EvidenceVerifier.verify(bundle) -> VerificationResult` and `TrustedVerifierRunner.run(manifest, clean_workspace) -> VerificationResult`.
- Produces: `VerifierSandbox.run(argv, workspace, limits) -> SandboxResult`; no command execution is permitted when a proven sandbox or dedicated ACL-restricted verifier account is unavailable.

- [ ] **Step 1: Write Windows boundary tests**

Test active-checkout denial, staging-root containment, drive/device paths, `..`, symlinks, junctions/reparse points, Git registration, protected branches, hooks/config inspection, environment secret stripping, child process limits, network allowlists, dirty baselines, and retention behavior.

- [ ] **Step 2: Implement fail-closed workspace validation**

Resolve final paths with Windows APIs, inspect reparse points for every component, compare case-insensitively, and require Paperclip sandbox-driver evidence before returning AUTO command/write authority.

- [ ] **Step 3: Write and implement hostile evidence tests**

Validate pre-run baseline, branch/worktree digest, changed paths, changed-test flagging, trusted test commands, independently derived reviewer identity, bounded logs, redaction, and prompt-injection markers. Run trusted commands through `TrustedVerifierRunner` in a fresh clean verifier workspace inside `VerifierSandbox`; use a secretless environment, network deny/allowlist, filesystem confinement, process-tree termination, CPU/memory/time/output limits, and a dedicated verifier account or proven sandbox driver. Derive exit codes and repository state locally rather than accepting worker-supplied claims. Without this containment, verification is static/read-only and cannot promote completion.

- [ ] **Step 4: Run focused tests and safety verification**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_workspaces.py tests/test_paperclip_evidence.py tests/test_paperclip_verifier_sandbox.py -v`

Run: `.venv\Scripts\python.exe scripts/verify_safety.py`

Expected: all tests pass.

### Task 9.1: Workforce, Plugin, And Isolation Provisioning

**Files:**
- Create: `config/paperclip/worker_templates.json`
- Create: `config/paperclip/workforce.json`
- Create: `scripts/paperclip_configure_workforce.py`
- Create: `scripts/paperclip_verify_service_isolation.ps1`
- Create: `tests/test_paperclip_workforce_config.py`

**Interfaces:**
- Produces: an idempotent desired-state document for the approved org, Claude Code/Codex worker templates, immutable adapter/provider/tool/capability digests, selected real sandbox provider, `low_trust_review` preset, budgets, and retention.
- Produces: `plan` mode by default and `--apply` only after `approved_mutate` compatibility plus explicit operator authorization.

- [ ] **Step 1: Test deterministic desired state and drift handling**

Assert exact role/template IDs, config digests, no broad environment inheritance, no user OpenCode/MCP/plugin passthrough, a real supported sandbox provider, low-trust containment, no release credentials, and ASK on permanent-agent or capability drift. Assert that selecting a lease-only environment driver never satisfies sandbox or dispatch enforcement.

- [ ] **Step 2: Implement plugin build and inspection checks**

Build the plugin to `dist/manifest.js` and `dist/worker.js`, pin plugin SDK compatibility, install only through Paperclip's explicit plugin command, inspect the installed digest/capabilities, and keep full auto disabled when the installed digest differs.

- [ ] **Step 3: Implement service-account isolation verification**

The PowerShell check accepts an explicit Paperclip process ID and service-account name, verifies the process token, denies read access to Nexi `.env`, browser profiles, SSH keys, and user-profile secret directories, and verifies only the worker staging root is writable. It does not create or modify an OS account.

- [ ] **Step 4: Run provisioning tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_workforce_config.py -v`

Expected: desired-state and isolation checks pass with mocked Paperclip; live apply remains gated by explicit authorization and compatibility.

## Increment F: Voice, Tools, And UI

### Task 10: Control-Plane Mode Facade And Stable Tools

**Files:**
- Modify: `engine/agency/__init__.py`
- Modify: `engine/tool_registry.py`
- Modify: `engine/intent_taxonomy.py`
- Modify: `engine/groq_intent_router_v2.py`
- Modify: `engine/studio/commands.py`
- Create: `tests/test_paperclip_agency_facade.py`
- Create: `tests/test_paperclip_routing.py`
- Create: `tests/test_paperclip_voice_lifecycle.py`

**Interfaces:**
- Produces: `control_plane_mode() -> Literal["local_legacy", "migration_blocked", "paperclip"]`.
- Adds tools `nexi_pause_mission`, `nexi_resume_mission`, `nexi_retry_work_item`, `nexi_reassign_work_item`, `nexi_budget_status`, `nexi_pending_workforce_approvals`, `nexi_approve_workforce_action`, and `nexi_reject_workforce_action`.

- [ ] **Step 1: Test dual-authority exclusion and no fallback**

Assert Paperclip activation enters explicit `migration_blocked` while any local Studio run is non-terminal, only legacy status/cancel remains available in that state, all Paperclip responses include `control_plane=paperclip`, Paperclip outage never starts local Studio, and legacy status remains readable after migration. Assert offline, stale, malformed, and verification-pending responses are never returned through the current `_ok()` helper with `verified=True`.

- [ ] **Step 2: Route facade operations by explicit mode**

Import Paperclip integration lazily inside handlers. Keep local legacy behavior unchanged when configured. In Paperclip mode, disable new local Studio creation and delegate stable status/activity/log/artifact/control tools to `PaperclipService`.

- [ ] **Step 3: Separate workforce approval commands**

Mark workforce approval tools model-forbidden and human-only. Never alias bare `approve` to workforce approval; require an explicit current Paperclip approval ID or a single unambiguous conversational capability.

- [ ] **Step 4: Run routing and facade tests**

Test wake -> listen -> ASR -> command -> TTS -> sleep, post-TTS follow-up capture, emergency interruption, no Paperclip request before wake, no request for unrelated personal commands, and session cleanup on offline/error/empty response. Keep these tests independent from real worker execution.

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_agency_facade.py tests/test_paperclip_routing.py tests/test_paperclip_voice_lifecycle.py tests/test_nexi_agency_workflows.py -v`

Expected: all tests pass.

### Task 11: Deferred Recovery And Studio Companion UI

**Files:**
- Modify: `engine/ui_event_bridge.py`
- Modify: `www_mark/studio_panel.js`
- Modify: `tests/test_studio_panel_playwright.py`
- Modify: `engine/memory_safety.py`
- Create: `engine/integrations/paperclip/recovery.py`
- Create: `engine/integrations/paperclip/monitor.py`
- Create: `tests/test_paperclip_recovery.py`
- Create: `tests/test_paperclip_monitor.py`

**Interfaces:**
- Produces: `paperclip_event(event: WorkEvent) -> dict`.
- Produces: `start_deferred_recovery(ui_ready: Event, stop: Event) -> Thread | None`.
- Produces: `MissionMonitor.run(stop: Event)`, foreground interval 5 seconds, background interval 30 seconds, bounded exponential backoff, synthetic/native cursor recovery, attention ingestion, reconciliation, and lease refresh.

- [ ] **Step 1: Test startup isolation**

Import command, wake, UI, and integration modules with an HTTP spy and assert zero Paperclip requests. Set UI-ready and assert non-terminal reconciliation starts asynchronously without blocking voice readiness.

- [ ] **Step 2: Implement active-mission monitoring**

Start only after UI-ready and only while at least one tracked mission is non-terminal. Deduplicate by durable external ID plus timestamp/revision, rebuild bounded state after cursor loss, refresh healthy leases, revoke on drift, and never schedule workers from polling.

- [ ] **Step 3: Implement bounded event projection**

Include native Paperclip state, external ID, mapped state, verification state, one attention item, and bounded redacted text. Replace the existing label-only UI redactor with `engine.memory_safety.redact_sensitive` plus structured field filtering. Test labeled secret values, bearer tokens, mixed-case labels, cookies, and bare vendor-key formats. Do not emit legacy G0-G11 stages.

- [ ] **Step 4: Update the existing Studio panel**

Render all external strings with `textContent`, show offline/stale and verification pending/failed, display budgets and attention, and preserve hidden-until-active behavior.

- [ ] **Step 5: Run backend and browser tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_recovery.py tests/test_paperclip_monitor.py tests/test_studio_panel_playwright.py -v`

Expected: all tests pass.

## Increment G: Release Gateway

### Task 12: Separate Gated Release Service

**Files:**
- Create: `engine/release_gateway.py`
- Create: `engine/release_approvals.py`
- Create: `config/paperclip/release_policy.json`
- Modify: `engine/ui_event_bridge.py`
- Modify: `www_mark/studio_panel.js`
- Create: `tests/test_release_gateway.py`
- Create: `tests/test_release_approvals.py`

**Interfaces:**
- Produces: `ReleaseGateway.create_draft_pr()`, `.merge_protected()`, `.deploy()`, `.verify_canary()`, and `.rollback()`.
- Every mutating method consumes a secure-UI assurance capability and a passed `VerificationResult`.
- Produces: `ReleaseApprovalStore.issue_from_verified_challenge()`, `.consume()`, and `.expire()`; voice, ordinary Eel events, and Paperclip actors cannot mint this capability.

- [ ] **Step 1: Test credential and authority separation**

Assert Paperclip credentials cannot authenticate the release gateway, Paperclip cannot call it, voice assurance cannot merge/deploy, an ordinary localhost/Eel click cannot mint release authority, only a verified one-time challenge bound to the authenticated Windows identity and exact repository/branch/operation can mint the capability, unverified work cannot create a PR, rollback proof is mandatory, and credentials never enter worker environments.

- [ ] **Step 2: Implement provider-neutral command contracts**

Use allowlisted argument arrays with `shell=False`, explicit repository/branch targets, bounded output, and redacted audit. Start with disabled provider configuration so no release occurs without explicit setup.

- [ ] **Step 3: Wire secure-UI release approval and Paperclip result reporting**

Render exact repository, branch, effect, cost/risk, and rollback details in the Studio companion. Define a `SecureConfirmationProvider` boundary with challenge, expiry, operation digest, Windows-principal binding, and assertion verification. Ship the provider disabled until a reviewed Windows Hello/WebAuthn or equivalent implementation is configured; Eel presence and OS username alone are insufficient. Post a release result and bounded evidence back to the Paperclip root issue through typed client methods only after verification; never expose release credentials to Paperclip.

- [ ] **Step 4: Run release tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_release_gateway.py tests/test_release_approvals.py -v`

Expected: all tests pass with provider operations mocked and live release disabled.

## Increment H: Cognitive Patterns And Improvement Lab

### Task 13: Bounded Mission Reflection And Improvement Proposals

**Files:**
- Create: `engine/improvement_lab.py`
- Create: `engine/integrations/paperclip/circuit_breaker.py`
- Create: `tests/test_improvement_lab.py`
- Create: `tests/test_paperclip_circuit_breaker.py`

**Interfaces:**
- Produces: `OperationCircuitBreaker.record(fingerprint, evidence_digest)`, `.allow(fingerprint)`, and `.reset_after_verified_change()`.
- Produces: `ImprovementLab.propose(failure) -> ImprovementProposal` and `.verify(proposal) -> VerificationResult`.

- [ ] **Step 1: Test loop detection and circuit breakers**

Trip after repeated identical operation fingerprints with unchanged evidence, preserve retry count across restart, permit at most two transient retries with exponential backoff, and require a verified evidence change before reset.

- [ ] **Step 2: Test isolated improvement behavior**

Require a disposable worktree, regression test, full relevant verification, independent code/security review, draft PR only, and explicit review for governance, secrets, release, and identity files. Assert no running-process edits, package/MCP installation, replication, wallets, or self-generated authority.

- [ ] **Step 3: Implement bounded verified memory output**

Store only mission reference, verified outcome, approved correction, reusable procedure, or repeated verified failure. Do not mirror raw task graphs, prompts, logs, or unverified claims.

- [ ] **Step 4: Run focused tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_improvement_lab.py tests/test_paperclip_circuit_breaker.py -v`

Expected: all tests pass.

## End-To-End Acceptance

### Task 14: Mocked And Live-Gated End-To-End Harness

**Files:**
- Create: `tests/harness/paperclip_fake_server.py`
- Create: `tests/test_paperclip_e2e.py`
- Create: `scripts/paperclip_e2e_check.py`
- Create: `docs/paperclip-operations.md`

**Interfaces:**
- Produces deterministic fake Paperclip server states for success, approval, outage, timeout, lease expiry, Board override, actor drift, budget stop, malformed response, and verification failure.

- [ ] **Step 1: Implement the deterministic fake server**

Expose only the installed-version routes used by `PaperclipClient`. Record mutation fingerprints and make duplicate requests return the existing result.

- [ ] **Step 2: Implement mocked end-to-end acceptance**

Run text and the complete wake/listen/ASR/command/TTS/sleep voice lifecycle, mission creation, project/issues, separate Claude/Codex work items, independently rerun evidence, one scoped ASK gate, rejection safety, one-use approval, verification pending, completion, cancellation, emergency-stop lease revocation, lease expiry, Board override reconciliation, non-Board drift denial, and cleanup.

- [ ] **Step 3: Implement live-gated acceptance**

The script first reads and revalidates `PaperclipCompatibilityReport` provenance against the live server. It exits `3` with an explicit blocking capability list when the installed version cannot enforce a requested mutation/full-auto scenario; blocked work is never reported as passed or skipped-success. It uses a disposable repository and refuses Nexi's active checkout.

- [ ] **Step 4: Run all verification gates**

Run: `.venv\Scripts\python.exe -m pytest tests/test_paperclip_*.py tests/test_release_gateway.py tests/test_improvement_lab.py -v`

Run: `.venv\Scripts\python.exe -m compileall engine`

Run: `.venv\Scripts\python.exe scripts/verify_safety.py`

Run: `.venv\Scripts\python.exe scripts/verify_dependencies.py`

Run: `.venv\Scripts\python.exe scripts/playwright_runtime_check.py`

Run: `.venv\Scripts\python.exe -m pytest tests/ -v`

Run: `git diff --check`

Expected: all compatible tests pass. Live full-auto acceptance remains blocked, not passed or skipped as success, until synchronous Paperclip governance hooks and the sandbox/backup gates are proven.

## Activation Decision

The first implementation pass is successful when Increments A and B work against Paperclip 0.3.1, Increments C through H have fail-closed unit/integration coverage, and the compatibility report prevents unsafe activation. The complete architecture acceptance criteria are not satisfied until Paperclip exposes synchronous pre-mutation and pre-dispatch enforcement or another reviewed non-fork mechanism proves equivalent atomic enforcement.
