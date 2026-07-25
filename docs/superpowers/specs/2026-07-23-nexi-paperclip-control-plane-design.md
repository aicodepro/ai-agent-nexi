# Nexi and Paperclip Control Plane Design

**Date:** 2026-07-23
**Status:** Approved architecture design
**Scope:** Full Nexi control of Paperclip with low-interruption auto mode

## 1. Decision

Nexi remains the owner-aligned, voice-first Cognitive OS. Paperclip runs as a
separate local service and becomes Nexi Studio's company and workforce control
plane. Claude Code, Codex, and specialist agents execute work managed by
Paperclip. Selected Automaton patterns inform Nexi's cognitive loop and
self-improvement lab, but Automaton is not embedded as Nexi's core.

The authority hierarchy is:

```text
Darsh
  -> Nexi Cognitive Kernel
      -> Nexi Mission and Authority Policy
          -> Paperclip control plane
              -> Nexi governance plugin (policy digest + authority lease)
              -> Claude Code, Codex, and specialist workers
                  -> sandboxed disposable Git worktrees
          <- status, evidence, costs, gates, and audit events
      -> Nexi verifier and conversational reporting
```

Paperclip is under Nexi. Paperclip does not replace Nexi, call Nexi tools, or
inherit authority over the Windows desktop.

## 2. Goals

1. Let a voice or text goal become a governed multi-agent software mission.
2. Let Paperclip own company goals, projects, issues, workers, heartbeats,
   budgets, execution workspaces, approvals, and workforce audit history.
3. Let Nexi create, assign, pause, resume, retry, cancel, inspect, and report
   Paperclip work through a typed adapter.
4. Keep routine isolated work autonomous, similar to Claude Code auto mode.
5. Interrupt Darsh only when work crosses a material trust boundary.
6. Require disposable Git worktrees inside an enforceable sandbox or a separate
   low-privilege OS account for autonomous code changes.
7. Preserve Nexi's local safety, voice, memory, verification, and rollback
   responsibilities.
8. Fail closed. Paperclip outages or permission failures must never silently
   fall back to a wider local execution path.

## 3. Non-Goals

This design does not:

- turn Paperclip into Nexi's chat or cognitive layer;
- register Paperclip as one worker runtime adapter;
- expose Nexi's tool registry, PC control, Forge, MCP bridge, or approval queue
  to Paperclip;
- merge Paperclip source into the Nexi repository;
- fork Paperclip during initial adoption;
- import active legacy Studio runs into Paperclip automatically;
- let workers edit Nexi's active checkout;
- enable live self-modification, self-replication, wallets, on-chain payments,
  survival incentives, or autonomous purchases;
- let Paperclip approval imply consent for a Nexi desktop or external action;
- deploy or merge code without the policy gates defined below.

## 4. System Ownership

| Capability | Nexi owns | Paperclip owns |
|---|---|---|
| Voice, wake, ASR, TTS, interruption | Yes | No |
| Conversation and goal understanding | Yes | No |
| Personal memory and project recall | Yes | No |
| Windows and application control | Yes | No |
| Mission classification and policy | Yes | No |
| Company, project, and issue graph | No | Yes |
| Org chart and worker assignment | No | Yes |
| Heartbeats and task checkout | No | Yes |
| Worker session persistence | No | Yes |
| Workforce budgets and costs | Policy envelope | Ledger and enforcement |
| Disposable execution worktrees | Boundary validation | Creation and lifecycle |
| Workforce approval objects | Relay and authority policy | State and audit |
| Local desktop approvals | Yes | Never |
| Tests and evidence verification | Final trust decision | Collection and routing |
| Merge, release, deploy, rollback | Nexi governance | Work coordination only |
| Workforce audit | Local bridge ledger | Company audit source |

Nexi chooses the mission, allowed role/template set, data-egress class, budget
envelope, and operation classes. Paperclip chooses a concrete worker from the
allowed roster and resolves its configured runtime/model. A direct human Board
override by Darsh remains authoritative and is reconciled as an out-of-band
human decision; no other Paperclip actor may widen a Nexi-managed mission.

## 5. Existing Nexi Components

### 5.1 Retain

- `engine/studio/commands.py`: explicit voice authorization grammar.
- `engine/studio/intent_detect.py`: inferred mission confirmation.
- `engine/groq_intent_router_v2.py`: deterministic Studio and mission routing.
- `engine/command.py::allCommands`: sensitive voice/text command entry point.
- `engine/app/phase3_command_bridge.py`: legacy/new command-flow bridge.
- `engine/tool_registry.py`: stable northbound voice tool names.
- `engine/agency/__init__.py`: stable facade for status and mission operations.
- `engine/control/safety.py`: emergency stop and local sandbox policy.
- `engine/control/action_gate.py`: local action policy.
- `engine/approval_queue.py`: local PC/browser approvals only.
- `engine/workflow_state.py`: short-lived conversational workflow state.
- `engine/context_budget_manager.py`: bounded cognitive context.
- `engine/claude_code/verifier.py`: local workspace and test evidence helpers.
- `engine/agent_runtime/adapters.py`: worker-side transports where still needed.
- `engine/memory_safety.py`: secret redaction.
- `engine/ui_event_bridge.py`: Studio event projection.
- `www_mark/studio_panel.js`: compact Nexi view of workforce activity.

### 5.2 Replace as the active workforce authority

When Paperclip mode is enabled, the following become legacy read-only
implementations:

- `engine/agency/workflow_engine.py` for company mission persistence;
- `engine/studio/supervisor.py` for G0-G11 workforce orchestration;
- local Studio agent-roster and stage assignment logic;
- local JSONL and `run.json` files as active company state;
- direct Nexi selection and dispatch of implementation workers;
- local Studio retries, stage gates, and completion truth.

Paperclip mode cannot be enabled while a local Studio run is non-terminal. Such a
run must first complete or be cancelled through the legacy path. After activation,
legacy runs are archived and read-only. New missions have exactly one authority:
Paperclip.

### 5.3 Do not reuse as the Paperclip boundary

- `engine/agency/web_server.py` exposes Nexi workflow internals and uses a broad
  shared bearer token.
- `engine/agency/nexi_tool_proxy.py` is a generic execution proxy and accepts a
  caller-provided risk value.
- `engine/approval_queue.py` approvals represent local actions, not Paperclip
  workforce gates.
- `CustomCliAdapter` represents a worker process, not a control plane.
- Paperclip must not call `engine.tool_registry.execute_tool`.

## 6. Paperclip Deployment

Paperclip runs outside the Nexi repository as a separately managed service.

Required configuration:

```text
runtime mode: authenticated
exposure: private
bind: loopback
listen address: 127.0.0.1
default port: 3100
telemetry: disabled
database: embedded PostgreSQL for the first local deployment
```

Current machine preflight on 2026-07-23:

- Node.js 24.12.0 is installed.
- pnpm 10.18.2 is installed.
- Paperclip CLI is not currently installed.
- No service is listening on `127.0.0.1:3100`.

Paperclip's documented minimums are Node.js 20+ and pnpm 9.15+, so the local
runtime satisfies the version floor.

The default Paperclip quickstart uses `local_trusted`. Nexi must not rely on that
mode for the full-control adapter. Initial setup must explicitly produce
`authenticated/private` with loopback binding and a real Board principal.

Paperclip installation, lifecycle, data directory, and logs are independent of
Nexi startup. Nexi may report that Paperclip is unavailable, but must not install,
start, reconfigure, or upgrade it as a side effect of import or a normal voice
turn.

Full auto mode additionally requires a versioned Nexi governance plugin installed
in Paperclip. The plugin validates the mission policy digest, rejects unauthorized
actors, enforces an expiring authority lease before dispatch, and pauses managed
work when the lease expires. If the installed Paperclip plugin API cannot enforce
those hooks, full auto mode is unavailable; the integration is limited to reads
and explicitly approved one-shot mutations.

Paperclip remains independently operable by Darsh through its authenticated
Board UI. Board changes to a Nexi-managed mission are treated as explicit human
overrides. A Paperclip-side pre-mutation hook atomically invalidates the current
lease and blocks new scheduling before applying the Board override. The adapter
then imports the Board decision into a new mission revision before issuing a new
lease. Polling is observability only, not the enforcement mechanism. If the
installed plugin API cannot enforce this transactionally, native Board mutation
of managed missions is disabled while full auto is active.

## 7. Adapter Boundary

Add a dedicated anti-corruption layer:

```text
engine/integrations/paperclip/
  __init__.py
  contracts.py
  client.py
  policy.py
  mapper.py
  service.py
  mission_store.py
  approvals.py
  evidence.py
  attention.py
  audit.py
```

The Paperclip-side enforcement package is a separate deployable plugin, not a
Paperclip fork:

```text
external/paperclip-nexi-governance/
  plugin manifest
  policy and lease validation
  managed-mission actor restrictions
  pre-dispatch workspace/sandbox checks
  lease-expiry pause/cancel job
```

### 7.1 `contracts.py`

Defines Nexi-owned normalized data types. Paperclip response dictionaries do not
escape the integration package.

Core types:

```text
PaperclipHealth
CompanyRef
MissionEnvelope
MissionRef
ProjectRef
WorkItem
WorkEvent
WorkerSummary
BudgetSummary
ApprovalRequest
OperationRequest
OperationDecision
OperationResult
ReconciliationResult
MissionPolicyRevision
AuthorityLease
DataEgressPolicy
BudgetPolicy
```

### 7.2 `client.py`

Owns HTTP only. It does not contain mission policy or voice formatting.

Rules:

- default base URL is exactly `http://127.0.0.1:3100/api`;
- allowed hosts are loopback addresses unless an explicit future design widens
  the boundary;
- `requests.Session.trust_env` is false;
- redirects are disabled;
- connect timeout is 2 seconds;
- response timeout is 10 seconds for normal API calls;
- response bodies are bounded before parsing;
- credentials are sent only to the configured origin;
- credentials, cookies, request bodies, and response bodies are never logged;
- all mutations require an idempotency key or a reconciliation strategy;
- methods return normalized errors, not raw HTTP exceptions.

The implementation must verify Paperclip's current routes and schemas from the
installed version. It must not guess endpoint paths from this design document.

### 7.3 `policy.py`

Makes deterministic `AUTO`, `ASK`, or `FORBIDDEN` decisions before any Paperclip
mutation. The same versioned policy digest is enforced by the Paperclip governance
plugin before worker dispatch. Model output cannot override either decision.

Policy categories come from checked-in registries rather than free-form model
labels:

```text
config/paperclip/operation_policy.json
config/paperclip/protected_paths.json
config/paperclip/network_allowlist.json
config/paperclip/supply_chain_policy.json
config/paperclip/data_egress_policy.json
```

Unknown operations, paths, hosts, package actions, or data classes default to
`ASK`; explicitly prohibited values are `FORBIDDEN`.

### 7.4 `mapper.py`

Maps Paperclip identities and states into bounded Nexi voice and UI models.
Paperclip IDs remain opaque and are never rewritten as local `wf_*` IDs.

### 7.5 `service.py`

Implements control-plane use cases:

- health and capability discovery;
- company selection;
- mission create-or-reuse;
- project and root issue creation;
- issue decomposition and assignment;
- worker status and activity;
- pause, resume, retry, cancel, and reassign;
- budget reads and policy-controlled changes;
- approval listing and policy-controlled responses;
- event polling and mission reconciliation;
- verified completion summaries.

The canonical external mission anchor is one Paperclip root issue. A Nexi
`mission_id` maps one-to-one to that root issue; its Paperclip project and goal
provide context. The root issue stores the `mission_id`, current policy revision,
policy digest, and idempotency fingerprint in a supported metadata/document
surface. If the installed version cannot preserve this correlation durably, mission
mutations remain disabled.

### 7.6 `mission_store.py`

Atomically persists the non-secret mission aggregate under ignored local state.
It owns policy revisions, Paperclip IDs, authority lease state, idempotency
fingerprints, approval capability/write-ahead state, event cursor, attention
state, and last reconciliation result. A restart never reconstructs authority
from conversation memory.

### 7.7 `approvals.py`

Maintains Paperclip-specific approval capabilities. It does not reuse local
desktop approval IDs or handlers.

### 7.8 `evidence.py`

Treats all worker output as hostile evidence. It validates artifact paths,
workspace baselines, trusted test commands, changed tests, independent reviewer
identity, command exit codes, and repository state before Nexi accepts completion.

### 7.9 `attention.py`

Groups approval/blocker events by stable fingerprint, suppresses duplicate prompts,
applies reminder cooldowns, and escalates one unresolved decision instead of
repeatedly interrupting the user.

### 7.10 `audit.py`

Appends redacted bridge events to a durable local ledger with restrictive file
permissions. Paperclip remains the workforce audit source; the local ledger
records the Nexi-to-Paperclip trust-boundary decision.

## 8. Stable Northbound Tools

Existing user-facing Studio tool names remain stable during migration:

```text
nexi_start_studio_build
nexi_studio_status
nexi_cancel_studio_build
nexi_continue_studio_build
nexi_workflow_status
nexi_agent_activity
nexi_workflow_logs
nexi_workflow_artifacts
```

In Paperclip mode these delegate through `engine/agency/__init__.py` to the new
control-plane service. Tool responses must indicate `control_plane=paperclip` so
the UI, logs, and tests can detect accidental fallback.

New explicit tools may be added for:

```text
nexi_pause_mission
nexi_resume_mission
nexi_retry_work_item
nexi_reassign_work_item
nexi_budget_status
nexi_pending_workforce_approvals
nexi_approve_workforce_action
nexi_reject_workforce_action
```

Paperclip approval commands must never route to `approve_action` or
`reject_action`, which are reserved for local Nexi actions.

## 9. Mission Aggregate And Policy Revisions

Every business/project mission starts from an immutable revision 1 envelope.
Approved changes create a new immutable revision; they never overwrite the prior
authority record:

```text
mission_id
schema_version
policy_revision
source_turn_id
requester_principal
raw_user_goal_digest
resolved_goal
acceptance_criteria
configured_company_id
configured_project_id, if continuing an existing project
paperclip_root_issue_id, after creation
allowed_repository_root
allowed_worker_templates: template ID, immutable revision, config digest,
  capability digest, adapter/provider identity, sandbox profile, tool classes,
  and network/data-egress policy
allowed_operation_classes
data_classification
allowed_model_providers
allowed_network_hosts
budget_policy: currency, period, cap, warning threshold, reservation rules
external_effects_allowed=false
created_at
expires_at for start authorization
supersedes_revision, after revision 1
revision_reason, after revision 1
```

The envelope is created from the user's current voice or text turn after material
ambiguities are resolved. It is not generated solely from a model plan.

The initial mission request authorizes creation and routine isolated execution
inside this envelope. It does not authorize later trust-boundary crossings.

The mission store persists every revision before Paperclip receives its digest.
Paperclip's root issue is the canonical external aggregate anchor. Personal memory
stores only the mission reference and verified summary, never the authority data.

Template, adapter, provider, tool, sandbox, or capability drift invalidates the
mission lease. A changed template is not an AUTO reuse; it requires a new policy
revision and the applicable ASK decision.

No autonomous paid execution starts until a nonzero budget policy is configured.
Before dispatch, Paperclip reserves the run's configured maximum estimated cost
against mission, agent, project, and company limits. Actual reported cost releases
or consumes that reservation. Delayed costs reduce future available budget; they
never retroactively authorize overspend. Concurrent reservations are atomic in
Paperclip. Budget changes create a new mission policy revision and follow the ASK
rules.

## 10. Low-Interruption Auto Mode

### 10.1 AUTO

The following proceed without another human interruption when they remain inside
the mission envelope:

- read Paperclip status, tasks, events, budgets, costs, and evidence;
- create or reuse a mission initiative, project, root issue, and sub-issues;
- add blockers, comments, documents, assignments, and internal review stages;
- assign pre-approved Claude Code, Codex, and specialist worker templates;
- create managed disposable worktrees and mission branches;
- read, search, and edit inside the assigned worktree;
- run allowlisted tests, linters, type checks, builds, and security scans;
- make local commits on the mission branch;
- request analyst, architecture, QA, security, and reviewer work;
- retry transient provider or infrastructure failures at most two times with
  exponential backoff;
- pause or cancel failed internal work;
- consume budget below the configured mission, agent, project, and company caps;
- produce bounded progress and completion reports.

### 10.2 ASK

Nexi interrupts Darsh only when:

- unresolved ambiguity would materially change the product or acceptance
  criteria;
- a new permanent agent, permission, tool class, integration, or secret is
  required;
- an operation leaves the disposable worktree;
- an operation touches protected governance, credential, or system files;
- unrestricted or unapproved network access is required;
- a dependency install or upgrade runs third-party install scripts or changes the
  approved supply-chain surface;
- a mission, agent, project, or company budget cap would be exceeded;
- bounded retries and independent review cannot resolve a blocker;
- work would merge to a protected branch;
- work would publish, deploy, modify production data, send external messages,
  charge money, or create another external or difficult-to-reverse effect;
- rollback cannot be proven before promotion.

Autonomous shell, build, test, and edit operations are AUTO only when an
enforcement-capable sandbox or separate ACL-restricted worker account applies the
mission filesystem, process, secret, and network policy. A host-local worktree by
itself never qualifies for AUTO execution.

### 10.3 FORBIDDEN

The following are never authorized by auto mode:

- Paperclip approving Nexi desktop actions;
- Paperclip or workers calling Nexi's tool registry, Forge, PC control, or MCP
  bridges;
- worker access to Nexi secrets, browser profiles, SSH keys, or personal memory;
- direct edits to Nexi's active checkout;
- destructive Git commands or protected-branch rewrites;
- disabling tests, policy, audit, verification, or rollback controls;
- live modification of running Nexi code;
- self-replication, wallets, on-chain actions, survival incentives, or autonomous
  purchases;
- interpreting model-generated plans as owner approval;
- silent local fallback after a Paperclip permission or availability failure.

## 11. Approval Capabilities

Each ASK decision produces a Paperclip-specific capability bound to:

```text
approval_id: cryptographically random
operation
target_type and target_id
normalized argument digest
canonicalization schema version
mission_id
mission policy revision
paperclip company/project/issue IDs
paperclip approval ID and revision
requester principal
voice/text source turn
approval assurance level
budget impact
risk reason
created_at
expires_at: five minutes by default
single_use: true
```

Approval text must name the effect, target, cost or risk, and rollback boundary.
"Approve" without a current unambiguous Paperclip approval must not approve the
oldest pending action.

Paperclip's internal approval record is workforce state. Nexi's capability is
proof that the human or policy authority allowed Nexi to answer that specific
record. Neither can authorize a local Windows action.

Arguments are canonicalized as versioned, sorted JSON before hashing. Capability
state moves atomically through `pending -> in_flight -> applied|rejected|unknown`.
The Paperclip mutation uses the capability digest as its idempotency key. A timeout
leaves the capability `unknown` until reconciliation proves whether the effect
occurred; it cannot be reused or replaced by an equivalent capability meanwhile.

Capability state is persisted with a write-ahead record before the remote
mutation. After restart, deferred recovery reconciles every `in_flight` or
`unknown` capability before an equivalent approval can be issued. Applied,
rejected, expired, and superseded records remain in the durable audit history.

Voice approval has the existing local-OS-principal assurance only. It may approve
normal ASK operations but is not sufficient for secrets, money, protected-branch
merge, production data, publish, or deploy. Those require confirmation in Nexi's
secure UI by the authenticated local user. A future stronger voice identity may
raise that assurance only through a separate design.

## 12. Authentication And Secrets

1. Paperclip uses `authenticated/private` mode on loopback.
2. A real Board user owns the instance.
3. Nexi uses the least-privileged credential type supported by the installed
   Paperclip version for each control operation.
4. Browser session cookies are not copied into Nexi configuration.
5. A broad Board credential is not used if a narrower service principal can be
   configured.
6. If Paperclip cannot represent the required least-privilege principal, the
   affected mutation remains disabled until an explicit design review.
7. Secrets live only in ignored local configuration or the OS secret store.
8. Secret values never enter prompts, memory, logs, UI payloads, artifacts, test
   fixtures, or worker environments unless a separately approved run requires a
   scoped Paperclip secret binding.
9. Paperclip credentials cannot be reused for Nexi's Agency API or local tools.
10. Nexi credentials cannot be injected into Paperclip workers.
11. A dedicated Paperclip company is initially managed by Darsh's Board
    principal and Nexi's scoped service principal only.
12. Agent and non-Darsh API principals cannot mutate policy metadata, budgets,
    approval ownership, worker permissions, or governance-plugin configuration.
13. A Darsh Board override is accepted as human authority, but must be imported
    as a new mission revision before automatic execution resumes.

## 13. Workspaces And Worker Execution

All autonomous implementation uses Paperclip-managed execution workspaces with
Git worktree mode plus an enforceable runtime boundary.

Required invariants:

- company, project, issue, repository, base ref, branch, and worktree IDs agree;
- the worktree path is outside Nexi's active checkout;
- the path is inside a configured worker staging root;
- the worktree is registered with Git before execution;
- the branch is not protected;
- the worker process receives only the worktree path and scoped run context;
- the worker runs in a Paperclip sandbox driver or a separate low-privilege OS
  account whose ACLs expose only the staging root;
- sandbox/process policy blocks parent paths, junction/reparse escapes, device
  paths, unapproved child processes, and unapproved network egress;
- Git hooks and repository configuration are inspected or disabled before running
  repository-controlled commands;
- no Nexi, browser, SSH, cloud, or user-profile secrets exist in the worker
  environment;
- user-level OpenCode plugins, MCPs, and configuration passthrough are disabled
  for governed work;
- worker tools cannot address paths outside the worktree;
- successful finalization verifies the expected branch and workspace digest;
- dirty or incoherent workspaces fail closed and create a recovery action;
- clean worktrees may be deleted after a configured retention window;
- failed worktrees are retained long enough for evidence and recovery.

Paperclip's `low_trust_review` preset is required for work that consumes hostile
or prompt-injected inputs. Such work must use Paperclip's sandbox driver and
isolated workspace mode. Host-local adapters are not sufficient containment.

Ordinary repository code is also untrusted when executed by tests, builds,
package managers, or Git hooks. If the runtime cannot enforce filesystem and
network containment, planning and static read-only analysis may continue, but
commands and writes require explicit per-run approval and cannot be labeled auto
mode.

## 14. Workforce Model

Initial managed roles:

```text
Nexi Executive Supervisor
  -> Business Analyst
  -> Product Manager
  -> Solution Architect
  -> UI/UX Designer
  -> Lead Developer
      -> Claude Code Developer
      -> Codex Developer
  -> QA Engineer
  -> Security Reviewer
  -> DevOps Engineer
  -> Release Manager
```

Paperclip owns the org chart and concrete task assignment. Nexi selects mission
intent, allowed role/template set, data-egress policy, and budget envelope, not
individual model IDs. Paperclip chooses a concrete worker from the allowed roster;
that worker's approved adapter configuration chooses runtime and model. An explicit
human reassign command may name a concrete worker, but automatic reassignment may
only choose within the allowed role/template set.

Repository content sent to a model is an egress event. Each mission names its data
classification and allowed model providers. Provider credentials are configured
at the worker runtime, not copied from Nexi. Unknown classifications or providers
are ASK; secrets and prohibited files remain FORBIDDEN.

Permanent agent creation, permission expansion, or new adapter installation is an
ASK operation. Reusing an approved inactive worker template is AUTO.

## 15. Mission Data Flow

### 15.1 Start

```text
voice/text goal
-> Nexi resolves personal/project memory
-> classify personal task vs company mission
-> ask only material missing questions
-> build MissionEnvelope
-> policy decision
-> create/reuse Paperclip initiative, project, and root issue
-> assign planning owner
-> start Paperclip heartbeat execution
```

### 15.2 Plan And Execute

```text
business analysis
-> acceptance criteria
-> architecture and design
-> issue decomposition with blocker relationships
-> disposable worktree allocation
-> Claude Code/Codex implementation
-> tests, security checks, and independent review
-> correction loop with bounded retries
```

Worker evidence is never trusted because it says "passed." Nexi's evidence
verifier compares the worktree to a pre-run baseline, validates changed paths,
flags test modifications, chooses test commands from trusted repository policy,
runs verification in a clean environment, and requires an independent reviewer
that did not author the implementation. Generated logs, patches, paths, artifacts,
screenshots, and test output are bounded and prompt-injection scanned before they
enter model context.

### 15.3 Finish

```text
Paperclip reports evidence-backed completion
-> Nexi verifies required evidence and workspace state
-> if promotion is gated, ask Darsh
-> create PR or promote only through the approved release path
-> canary and health check
-> rollback on regression
-> store bounded verified outcome in Nexi procedural/project memory
-> conversational result report
```

Paperclip never performs the final external release on Nexi's behalf. A separate
Nexi Release Gateway, invoked by Nexi after polling a gated Paperclip result, owns
the dedicated Git-host/deployment credentials. It may create a draft PR from the
verified mission branch. Protected-branch merge, publish, deploy, production
mutation, canary promotion, and rollback are executed only by this gateway under
the approved operation capability. Paperclip receives the resulting status and
evidence as issue comments/work products.

## 16. Status And UI Mapping

The existing Studio panel becomes a compact Paperclip companion, not a second
task manager.

| Paperclip state | Nexi display state |
|---|---|
| `backlog` | queued |
| `todo` | ready |
| `in_progress` | active |
| `blocked` | blocked |
| `in_review` | reviewing |
| `done`, not yet independently verified | verification pending |
| `done`, verification passed | completed |
| `done`, verification failed | verification failed |
| `cancelled` | cancelled |
| unavailable/stale | offline or stale |

The payload includes the native Paperclip state and external ID. Nexi must not
pretend Paperclip work is in a legacy G0-G11 stage.

Paperclip event text is untrusted. It is bounded, redacted, and rendered with
`textContent`, never executable HTML.

Nexi never speaks or displays "completed" solely from Paperclip `done`. The
mission store records `verification_pending`, and only the evidence verifier can
promote it to `completed`.

## 17. Polling And Proactive Attention

- No Paperclip calls occur during module import, wake-word scoring, sleep
  detection, or unrelated personal commands.
- After the UI and bridge are ready, a deferred integration-recovery job loads
  non-terminal mission references from the local mission store and reconciles
  them. This job is not part of wake startup and cannot block voice readiness.
- User-requested status reads are immediate and timeout-bounded.
- Active mission monitoring runs only while at least one Nexi-tracked Paperclip
  mission is non-terminal.
- Foreground mission views may poll every five seconds.
- Background monitoring defaults to 30 seconds with exponential backoff.
- Event cursors and external IDs deduplicate updates.
- Paperclip heartbeats schedule worker execution. Nexi polling never becomes a
  second scheduler.
- Nexi surfaces only changes requiring attention or requested summaries, not raw
  heartbeat noise.
- Attention fingerprints group equivalent approvals and blockers. Duplicate
  events do not reprompt. A pending request has one reminder cooldown and one
  escalation deadline; concurrent budget requests are summarized into one scoped
  decision without broadening any capability.

## 17.1 Mission Authority Lease

Every automatic mission has a short renewable authority lease signed by Nexi and
validated by the Paperclip governance plugin. The lease binds mission ID, policy
revision, allowed operation classes, immutable worker/template capability digests,
sandbox profile, data-egress policy, and expiry.

- Nexi refreshes the lease only while the mission remains enabled and policy state
  is healthy.
- Emergency stop revokes the local lease and sends Paperclip a pause/cancel request.
- If Nexi crashes, loses credentials, or stops refreshing, the plugin blocks new
  heartbeats and mutations after expiry and requests cancellation of managed
  running work.
- The lease never authorizes external effects or operations outside the mission
  policy.
- Full auto mode cannot be enabled unless installed-version tests prove the plugin
  can fail closed on lease expiry and stop future dispatch.

## 18. Idempotency And Reconciliation

Every mutation gets an idempotency fingerprint derived from:

```text
mission_id
operation class
target external ID
normalized arguments
accepted plan revision, when applicable
```

Rules:

- a timeout never causes a blind duplicate mutation;
- Nexi queries Paperclip for the fingerprint or resulting object;
- completed operations return the existing result;
- in-flight operations remain in-flight;
- ownership `409` responses stop retrying and trigger state reconciliation;
- accepted-plan decomposition is exact-once per source issue and accepted plan
  revision;
- retries reuse existing child issues and worktrees;
- stale locks are handled by Paperclip recovery semantics, not forced by Nexi;
- Nexi records the reconciliation outcome in the bridge audit ledger.

## 18.1 Mission Control Semantics

Control operations are idempotent state transitions, not fire-and-forget commands:

- **Pause:** blocks future wakes for the selected issue tree, requests graceful
  cancellation of active runs, waits for acknowledgment, and preserves worktrees.
- **Resume:** requires a valid mission policy revision and authority lease, then
  wakes only healthy assigned work whose blockers and gates are clear.
- **Cancel:** marks the selected issue tree cancelled, stops queued/running work,
  preserves evidence, revokes related pending approvals, and never deletes a
  worktree automatically.
- **Retry:** creates or adopts one bounded successor run for a failed work item,
  reuses the same issue/worktree/idempotency context, and refuses terminal success
  or an active live owner.
- **Reassign:** atomically changes one issue owner, cancels stale wakes for the old
  owner, and queues at most one wake for the new allowed owner.

Tree operations use Paperclip preview/dry-run data when available, record affected
issue/run IDs, and reconcile partial acknowledgment. Terminal repeated operations
return the existing state rather than producing new side effects.

## 19. Failure Handling

| Failure | Required behavior |
|---|---|
| Paperclip offline | Report unavailable; preserve mission state; no local Studio fallback |
| `401/403` | Freeze Paperclip mutations; report configuration/authority failure |
| `404` | Reconcile configured company/project/object IDs; do not recreate blindly |
| `409` | Treat as ownership, lock, or gate conflict; fetch current state |
| `429` | Bounded backoff; preserve remaining budget and deadline |
| `5xx` | Retry reads/idempotent operations at most twice; otherwise block visibly |
| Timeout after mutation | Reconcile by idempotency fingerprint before retrying |
| Malformed/oversized response | Reject and record bounded evidence |
| Unknown state/schema | Fail closed and require adapter compatibility review |
| Worker crash | Let Paperclip surface/recover; do not silently run a local worker |
| Failed tests/review | Return to assigned work with bounded correction attempts |
| Budget hard stop | Pause affected work and raise one scoped budget request |
| Worktree incoherence | Stop execution and open a recovery action |
| Audit write failure | Block high-risk mutations; low-risk reads may continue visibly degraded |
| Nexi crash or lease expiry | Governance plugin blocks new dispatch and pauses/cancels managed work |
| Paperclip database/migration failure | Freeze mutations; require verified backup/repair before resume |
| Disk full | Stop dispatch and mutations; preserve bounded diagnostics only |
| API version changes mid-mission | Freeze incompatible operations and require compatibility recheck |
| Invalid/expired event cursor | Rebuild bounded state from mission anchor, then store a new cursor |
| Out-of-order/duplicate events | Order and deduplicate by durable external ID and timestamp/revision |
| Hung worker process tree | Paperclip cancellation grace, then sandbox/process-tree termination |
| Delayed cost report | Reconcile reservation; reduce future availability; never erase overspend |
| Credential rotation | Freeze affected operations until the new principal passes capability checks |
| Concurrent Board/Nexi mutation | Treat Darsh Board action as override; otherwise reject and pause on drift |

## 20. Memory Boundaries

Nexi memory stores:

- the user's goal and durable preferences;
- the Paperclip company/project/mission references needed for recall;
- bounded verified outcomes;
- approved decisions and corrections;
- successful procedural patterns;
- repeated failures and their verified fixes.

Nexi memory does not mirror:

- the full Paperclip task graph;
- raw worker logs;
- raw prompts or model output;
- secrets or credentials;
- unverified claims of completion;
- every heartbeat or transient status.

Paperclip remains the source of truth for company execution context.

## 21. Automaton-Inspired Patterns

The following patterns may be reimplemented under Nexi governance:

- `Think -> Act -> Observe -> Reflect` as a bounded cognitive mission loop;
- heartbeat scheduling for proactive attention, not worker execution duplication;
- working, episodic, semantic, procedural, and relationship memory layers;
- loop detection based on repeated operation fingerprints and unchanged evidence;
- retry with exponential backoff and circuit breakers;
- tool policy evaluation before execution;
- prompt-injection checks and low-trust review containment;
- protected governance paths;
- self-repair audit history;
- spend-aware model and worker routing;
- a controlled `NEXI_IDENTITY.md` changed only by reviewed PR.

Explicit exclusions:

- wallet creation and crypto payments;
- survival tiers or self-preservation goals;
- autonomous revenue-seeking behavior;
- domain purchases;
- self-replication;
- live source modification;
- runtime package or MCP installation without policy approval;
- silent local fallback;
- self-generated trust or sovereignty over owner authority.

## 22. Self-Improvement Lab

Self-improvement is a separate mission class and never edits the running Nexi
process.

```text
detect failure
-> capture redacted evidence
-> reproduce in an isolated worktree
-> add an evaluation/regression test
-> propose prompt, skill, config, or code change
-> run full relevant verification
-> independent security and code review
-> create PR
-> approval when required by policy
-> canary
-> promote or roll back
```

Protected governance, secrets, release, and identity files require explicit
review regardless of automated test results.

## 23. Compatibility Gate And Delivery Increments

This document is an umbrella architecture, not one implementation plan. Each
increment below requires its own focused specification, plan, tests, and acceptance
gate.

### Increment A: deployment and compatibility

- install Paperclip separately in authenticated/private loopback mode;
- create the Board user and candidate Nexi service principal;
- generate a `PaperclipCompatibilityReport` from the installed version;
- verify exact API routes, auth principal capabilities, metadata correlation,
  idempotency support, budgets, approvals, plugin hooks, execution workspaces,
  sandbox driver, cancellation, event cursors, and adapter versions;
- configure scheduled Paperclip database backups outside the live data directory;
- prove one backup restore and one failed-migration rollback in a disposable
  Paperclip instance before enabling mutable increments;
- disable any later increment whose required capability cannot be proven.

### Increment B: typed read integration

- implement contracts, loopback transport, mapper, health, capability reads,
  mission status, activity, budgets, approvals display, and UI projection;
- add the durable mission-reference store and deferred post-UI recovery;
- make no Paperclip mutations.

### Increment C: governance enforcement

- implement the deterministic registries, policy engine, mission revisions,
  bridge audit, attention manager, approval capabilities, data-egress policy, and
  Paperclip governance plugin;
- prove actor restrictions and lease-expiry fail-closed behavior;
- mutations remain disabled until this increment passes.

### Increment D: mission and work control

- enable root-mission create/reuse, project/issue operations, assignment, pause,
  resume, retry, cancel, reassign, budget reservations, approval relay, and
  reconciliation;
- use one disposable non-code mission before worker execution.

### Increment E: sandboxed coding workforce

- configure the approved org, Claude Code/Codex adapters, sandbox/low-privilege
  runtime, data egress, disposable worktrees, trusted test manifests, hostile
  evidence verifier, independent reviews, and retention cleanup;
- run one disposable repository mission with no release authority.

### Increment F: voice and UI control

- preserve routing order through `engine/command.py::allCommands`,
  `engine/app/phase3_command_bridge.py`, and the tool registry;
- route full Paperclip mission control and attention requests conversationally;
- test wake/listen/TTS/follow-up behavior independently of worker execution.

### Increment G: release gateway

- add dedicated Git-host/deployment credentials, draft PR creation, protected
  merge gates, canary, health verification, and rollback;
- Paperclip remains a coordinator and evidence store, not the credential holder.

### Increment H: cognitive patterns and improvement lab

- add Automaton-inspired memory, loop detection, circuit breakers, reflection,
  proactive attention, and the isolated self-improvement PR loop;
- keep this separate from Paperclip adoption and release authority.

Mode migration rules:

1. Add `local_legacy` vs `paperclip` mode with no silent fallback.
2. Refuse Paperclip activation while any legacy run is non-terminal.
3. Complete or explicitly cancel those runs before switching.
4. After activation, archive all legacy runs read-only and disable new local
   Studio creation.
5. Keep status tools stable and mark every result with `control_plane`.

## 24. Testing Strategy

### 24.1 Unit tests

- contract validation and schema bounds;
- URL, host, redirect, proxy, timeout, and response-size guards;
- credential redaction;
- AUTO/ASK/FORBIDDEN policy matrix;
- approval capability binding, expiry, and single use;
- mapper behavior for every known and unknown state;
- idempotency fingerprint stability;
- error normalization and retry eligibility;
- audit append and redaction;
- mission envelope validation.
- mission revision persistence and restart recovery;
- operation/path/network/supply-chain/data-egress registry defaults;
- budget reservation and delayed-cost reconciliation;
- attention grouping, reminder suppression, and escalation;
- hostile evidence and changed-test detection.

### 24.2 Integration tests with mocked HTTP

- health and capability discovery;
- company/project/mission create-or-reuse;
- assignment, pause, resume, retry, cancel, and reassign;
- budgets and hard stops;
- approval list/respond behavior;
- pagination and event cursors;
- timeout reconciliation;
- `401`, `403`, `404`, `409`, `429`, `5xx`, malformed JSON, and oversized payloads;
- no duplicate mutations after retries;
- no local Studio fallback;
- no access to local approval actions.
- governance-plugin actor and policy-digest enforcement;
- authority lease refresh, expiry, emergency revocation, and process cancellation;
- Board override reconciliation and non-Board drift rejection;
- approval `pending/in_flight/unknown/applied` timeout behavior;
- approval write-ahead crash recovery and equivalent-approval suppression;
- full pause/resume/retry/cancel/reassign state transitions.

### 24.3 Boundary tests

- no Paperclip request during import, wake startup, sleep, wake detection, or
  unrelated personal commands;
- deferred recovery begins only after UI/bridge readiness and cannot block voice;
- adapter exposes no generic HTTP or arbitrary endpoint method;
- Paperclip IDs never enter local workflow identity namespaces;
- Paperclip reads do not mutate local Studio persistence;
- workers cannot access the active checkout or paths outside their worktree;
- user configuration and extension passthrough are disabled for governed runs;
- Paperclip approval cannot execute Nexi tools;
- secrets never appear in logs, memory, UI, or fixtures;
- dual authority is impossible in Paperclip mode.
- host-local uncontained workers cannot receive AUTO write/command authority;
- sandbox escapes through parent paths, symlinks, junctions/reparse points, Git
  hooks, process trees, and network egress are denied;
- only Darsh Board override or the scoped Nexi service principal can change a
  managed mission;
- worker/provider egress stays within mission data classification and allowlists.
- worker template/config/capability drift invalidates the lease before dispatch;
- a Board override atomically revokes the prior lease before scheduling can resume.

### 24.4 UI tests

- Paperclip status and event projection;
- native/external state labels;
- stale/offline display;
- bounded event text and HTML sanitization;
- pending attention and approval display;
- no false G0-G11 claims.
- `done` remains `verification pending` until independent evidence passes;
- verification failure is visible and never displayed as completed.

### 24.5 End-to-end acceptance test

Use a disposable repository and a small application mission:

1. Nexi creates the Paperclip mission from text first, then voice.
2. Paperclip creates the goal, project, issues, org assignments, and worktree.
3. Claude Code and Codex complete separate assigned tasks.
4. Tests, security review, and independent review produce evidence.
5. Routine work completes without human interruption.
6. A deliberately gated action pauses and asks once with exact effect details.
7. Rejecting the gate leaves the repository and Paperclip state safe.
8. Approving it consumes one scoped capability.
9. Completion is reported only after evidence verification.
10. The disposable worktree can be cleaned or rolled back.
11. Killing Nexi causes authority lease expiry and stops new Paperclip execution.
12. A direct Darsh Board override is reconciled; an agent/admin drift attempt
    is rejected or pauses the mission.

## 25. Acceptance Criteria

The integration is complete only when:

- Paperclip is a separate authenticated/private loopback service;
- Paperclip database backup, restore, and migration rollback have passed in a
  disposable instance;
- the installed-version compatibility report proves every capability required by
  the enabled increment;
- Nexi remains the only user-facing cognitive and desktop authority;
- one explicit mission creates governed Paperclip work;
- routine work runs autonomously inside sandboxed disposable worktrees or an
  equivalent ACL-restricted low-privilege worker boundary;
- trust-boundary actions request scoped approval;
- full mission control is available through typed Nexi tools;
- Paperclip cannot call Nexi tools or access Nexi secrets;
- an expiring mission authority lease prevents continued autonomous execution
  after Nexi failure or emergency stop;
- non-Darsh Paperclip actors cannot widen Nexi-managed mission authority;
- active local Studio and Paperclip orchestration cannot run for the same new
  mission;
- costs and hard budget stops are visible and enforced;
- retries are bounded and mutations are idempotent;
- tests and reviewers provide verifiable evidence;
- Paperclip `done` is not presented as completion before Nexi verification;
- merge/release/deploy follows the gated PR, canary, and rollback path;
- failures do not widen authority or trigger silent fallback;
- a disposable-repository end-to-end mission passes.

## 26. Sources

- Paperclip README: https://github.com/paperclipai/paperclip
- Paperclip deployment modes:
  https://github.com/paperclipai/paperclip/blob/master/doc/DEPLOYMENT-MODES.md
- Paperclip execution semantics:
  https://github.com/paperclipai/paperclip/blob/master/doc/execution-semantics.md
- Paperclip low-trust presets:
  https://github.com/paperclipai/paperclip/blob/master/doc/LOW-TRUST-PRESETS.md
- Paperclip roadmap:
  https://github.com/paperclipai/paperclip/blob/master/ROADMAP.md
- Automaton architecture reference:
  https://github.com/Conway-Research/automaton/blob/main/ARCHITECTURE.md
