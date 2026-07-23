# NEXI AI Team — Master-Class Upgrade Plan

**Status:** plan only (no code executed for this document, per request).
**Date:** 2026-07-18
**Scope:** Hermes · OpenCode · Claude Code, coordinated by NEXI as CEO.

> **Honesty markers used throughout**
> `✅ EXISTS` — verified present in this repo or this machine during this session.
> `⚠️ VERIFY` — named by Darsh; exact package/install string **not yet confirmed**. Do not
> paste blindly; run the verification step first. Marked so nothing here is invented.

---

## 1. System Architecture Overview

```
                    ┌──────────────────────────────┐
                    │   NEXI  (CEO / Supervisor)   │  voice + desktop + vision
                    │  intent router → task kind   │  engine/groq_intent_router_v2
                    └──────────────┬───────────────┘
                                   │ task_kind + acceptance criteria
                    ┌──────────────▼───────────────┐
                    │  Studio Supervisor (G0–G11)  │  engine/studio/supervisor.py  ✅ EXISTS
                    │  gates · verify · rollback   │
                    └──────────────┬───────────────┘
                                   │ chooses RUNTIME (not model)
        ┌──────────────────────────┼──────────────────────────┐
        ▼                          ▼                          ▼
  ┌───────────┐            ┌───────────┐              ┌───────────┐
  │  Hermes   │            │ OpenCode  │              │Claude Code│
  │ multi-prov│            │ free pool │              │Sonnet/Opus│
  └─────┬─────┘            └─────┬─────┘              │  /Fable   │
        │                        │                    └─────┬─────┘
        └────────────────────────┴──────────────────────────┘
                                 │ model chosen per task, free-first
                    ┌────────────▼─────────────┐
                    │  MODEL LAYER (no hardcode)│  ✅ EXISTS (built this session)
                    │ model_discovery  → live   │  reads provider catalogue
                    │ model_policy     → chain  │  free-first, task-mapped
                    │ model_health     → bench  │  fail → drop → next best
                    └───────────────────────────┘
                                 │
                    ┌────────────▼─────────────┐
                    │  TEAM ROLES (your zip)   │
                    │ Producer · BA · Dev(Lead,│
                    │ Nova, Sage, Milo) · QA · │
                    │ DevOps                   │
                    └──────────────────────────┘
```

**Hierarchy rule:** NEXI never picks a *model*. It picks a **task kind** and a **runtime**;
the model layer resolves the model. This is what keeps the system free of hardcoded model
logic — the constraint you set.

**Role → runtime → task_kind mapping** (roles come from `ai-team-agents-v2.zip`):

| Team role | task_kind | Preferred runtime | Why |
|---|---|---|---|
| Producer | `orchestration` | Claude Code (Opus tier) | hardest planning/reasoning |
| Business Analyst | `orchestration` | Claude Code / Hermes | requirements precision |
| Dev — Lead | `orchestration` | Claude Code | decomposition + release PR |
| Dev — Nova (frontend) | `code` | OpenCode (free coder model) | high volume, cost-sensitive |
| Dev — Sage (backend) | `code` | OpenCode / Hermes | high volume |
| Dev — Milo (visual) | `ui` | OpenCode + design skills | UI polish |
| QA | `test` | OpenCode (free) | high volume, verifiable output |
| DevOps | `orchestration` | Claude Code | infra risk |

---

## 2. Configuration Files

### 2.1 Team-level model policy — `config/nexi_team_models.yml`

**No model ids are hardcoded as required values.** Ids appear only as *fallback hints* used
when live discovery is unreachable; the live catalogue always wins.

```yaml
schema_version: 1

# Global rules the model layer enforces (engine/agent_runtime/model_policy.py)
policy:
  free_first: true              # free-tier models before subscription
  never_default_to: ['google/gemini-2.5-flash']   # explicitly ruled out
  chain_not_single: true        # a task resolves to an ordered chain
  discovery:
    enabled: true
    provider_catalogue: 'https://openrouter.ai/api/v1/models'   # ✅ verified live: 23 free models
    ttl_seconds: 3600
    warm: background            # never fetch inside a voice turn
  health:
    fail_threshold: 2           # N failures → bench the model
    cooldown_seconds: 1800      # then re-probe (free tiers rate-limit, then recover)
    on_success: clear_failures

runtimes:
  claude-code:
    auth: subscription           # Claude Max. NOT usable as an API key elsewhere.
    pool_source: static          # the Claude family is fixed, not discoverable
    models: ['claude-opus-4-8', 'claude-sonnet-5', 'claude-fable-5', 'claude-haiku-4-5']
    tasks:
      orchestration: 'claude-opus-4-8'
      code: 'claude-sonnet-5'
      test: 'claude-sonnet-5'
      quick: 'claude-haiku-4-5'

  opencode:
    auth: api_key                # ⚠️ a Claude Code token is NOT an API key here
    pool_source: discovery       # live free models; static list is fallback only
    prefer: free
    fallback_hints: []           # intentionally empty — discovery supplies these

  hermes:
    auth: mixed                  # OpenAI + Anthropic + opencode providers
    pool_source: discovery
    prefer: free
    fallback_hints: []
```

### 2.2 Per-runtime plugin attachment — `config/nexi_team_plugins.yml`

```yaml
schema_version: 1

# Canonical plugin set. `targets` says which CLIs get it.
# `verify` MUST pass before the plugin is considered attached (anti-hallucination).
plugins:
  - id: ponytail             # ✅ EXISTS (installed here)
    targets: [hermes, opencode, claude-code]
    kind: skill
    priority: critical       # Darsh: "important"
  - id: superpowers          # ✅ EXISTS
    targets: [hermes, opencode, claude-code]
    kind: skill
  - id: context7             # ✅ EXISTS (MCP)
    targets: [hermes, opencode, claude-code]
    kind: mcp
  - id: graphify             # ✅ EXISTS
    targets: [hermes, opencode, claude-code]
    kind: skill
    hook: pre_project        # run before coding starts on a new project
  - id: playwright           # ✅ EXISTS (webapp-testing / playwright installed)
    targets: [hermes, opencode, claude-code]
    kind: mcp
  - id: gstack               # ✅ EXISTS
    targets: [hermes, opencode, claude-code]
    kind: skill
  - id: frontend-design      # ✅ EXISTS
    targets: [hermes, opencode, claude-code]
    kind: skill
  - id: ui-ux-pro-max        # ✅ EXISTS (global CLAUDE.md)
    targets: [hermes, opencode, claude-code]
    kind: skill
  - id: ruflo                # ✅ EXISTS (MCP in workspace .mcp.json)
    targets: [hermes, opencode]
    kind: mcp
  - id: claude-mem           # ⚠️ VERIFY exact package
    targets: [hermes, opencode, claude-code]
    kind: memory
  - id: octogent             # ⚠️ VERIFY
    targets: [hermes, opencode]
    kind: agent-orchestrator
  - id: opencode-agent-skills # ⚠️ VERIFY
    targets: [opencode]
    kind: skill-pack
  - id: opencode-morph-plugin # ⚠️ VERIFY
    targets: [opencode]
    kind: plugin
  - id: plannotator          # ⚠️ VERIFY
    targets: [hermes, opencode]
    kind: plugin
  - id: hermes-webui         # ⚠️ VERIFY — Hermes-specific by name
    targets: [hermes]
    kind: ui
  - id: impeccable           # ⚠️ VERIFY
    targets: [hermes, opencode]
    kind: skill
  - id: skillui              # ⚠️ VERIFY
    targets: [hermes, opencode]
    kind: skill
  - id: crawl4ai             # ⚠️ VERIFY — must be configured key-free (no API cost)
    targets: [hermes, opencode]
    kind: mcp
    config: { mode: local, api_key_required: false }

# Plugins removed from claude-code go here WITH A REASON (your conflict-resolution rule).
claude_code_exclusions:
  - id: hermes-webui
    reason: 'Hermes-specific UI; no Claude Code surface.'
  - id: opencode-agent-skills
    reason: 'OpenCode-native skill format.'
  - id: opencode-morph-plugin
    reason: 'OpenCode-native plugin API.'
```

---

## 3. Plugin Integration Steps

**Step 0 — Verify before attaching (mandatory, anti-hallucination).**
For every `⚠️ VERIFY` entry, resolve the real package first. Do not guess an install string.
```bash
npx skills find <name>          # skills ecosystem
# and/or the plugin's own repo README for MCP servers
```
Record the resolved id in `config/nexi_team_plugins.yml`. **If it cannot be resolved,
mark it `status: unresolved` and skip it** — an unresolved plugin must never be silently
assumed present.

**Step 1 — Hermes.** Attach every plugin whose `targets` includes `hermes`.
**Step 2 — OpenCode.** Attach every plugin whose `targets` includes `opencode`.
OpenCode consumes skills via its agent-skills format and MCP via its config; both are
declared in the adapter's generated config (`engine/agent_runtime/adapters.py`,
`OpenCodeAdapter.child_environment` ✅ EXISTS).
**Step 3 — Claude Code (conditional).** Attach only if compatible. On any error, remove it
and append an entry to `claude_code_exclusions` **with the reason** — per your conflict rule.

**Step 4 — Parity check.** Your requirement "everything in OpenCode also in Hermes":
```
assert set(plugins_for('opencode')) - set(opencode_only) ⊆ set(plugins_for('hermes'))
```
Fail the deployment if parity breaks.

---

## 4. MCP Connection Strategy  ← *your most concrete pain point*

**Problem observed:** only 1–2 MCPs connect on CLI start; the rest need manual reconnect.

**Rule: no task starts until the MCP preflight passes.** This is a gate, not a hope.

```yaml
# config/nexi_mcp_preflight.yml
schema_version: 1

preflight:
  run_before: any_task_execution     # hard gate
  parallel: true
  per_server:
    connect_timeout_s: 10
    retries: 3
    backoff: exponential             # 1s, 2s, 4s
  on_partial_failure: degrade_explicitly   # never silently continue
  required:                          # task is BLOCKED if these are down
    - context7
    - ruflo
  optional:                          # log + continue if down
    - playwright
    - crawl4ai
  health_probe: list_tools           # a server that connects but exposes 0 tools is DOWN
  report: 'artifacts/mcp_preflight.json'
```

**Procedure**
1. Enumerate every configured MCP server for the target CLI.
2. Connect **in parallel**, each with timeout + 3 retries (exponential backoff).
3. **Probe, don't trust:** call `list_tools` on each. A connected server exposing zero tools
   counts as **DOWN** — this is the failure mode that makes agents hallucinate a tool that
   isn't really there.
4. Classify: `required` down → **block the task** with a clear message. `optional` down →
   proceed, but explicitly tell the agent that server is unavailable so it cannot assume it.
5. Write `artifacts/mcp_preflight.json` (server, status, tool count, attempts, latency).
6. Re-run preflight on session resume, not just cold start.

**Why the tool-count probe matters:** the anti-hallucination guarantee comes from the agent
being *told* what is actually available, rather than inferring from a config file that lists
a server which never connected.

---

## 5. Intent Router Enhancement

NEXI's router already has a tiered pipeline (`engine/groq_intent_router_v2.py` +
`engine/router/` ✅ EXISTS: deterministic guards → e5 semantic → confidence bands → LLM tier).
The upgrade is to emit a **task_kind** alongside the intent, because task_kind is what drives
runtime + model selection.

```yaml
# Routing rules — intent → task_kind → runtime (model resolved downstream, never here)
routing:
  - match: ['build', 'implement', 'create feature', 'add endpoint', 'write code']
    intent: studio_build
    task_kind: code
    runtime: opencode           # free pool
    team_role: dev

  - match: ['plan', 'design', 'architect', 'break down', 'decompose']
    intent: studio_plan
    task_kind: orchestration
    runtime: claude-code        # Opus tier
    team_role: producer

  - match: ['test', 'verify', 'qa', 'check it works']
    intent: studio_test
    task_kind: test
    runtime: opencode
    team_role: qa

  - match: ['fix yourself', 'improve your own', 'add a tool for yourself']
    intent: nexi_forge_tool     # ✅ EXISTS (self-development loop)
    task_kind: self_improve
    runtime: claude-code
    guard: forge_safety_gate    # gate BEFORE execution; never model-mintable

  - match: ['research', 'find out', 'look up', 'what is the best']
    intent: web_research
    task_kind: research
    runtime: hermes
    guard: camel_quarantine     # fetched text must NOT reach a tool-calling context

bands:
  act:     '>= 0.75'   # execute
  confirm: '0.55–0.75' # ask a single confirming question
  chat:    '< 0.55'    # answer conversationally, do not act
```

**Self-improvement routing (your ask):** `self_improve` must always pass the Forge safety
gate *before* execution, use a **held-out evaluation the generator never sees**, and write to
an **archive with one-command rollback**. (Rationale: measured 73.8% of self-improving code
agents reward-hack their own gate — see `NEXI_AUTONOMY_IDEAS.md` #82/#83.)

---

## 6. Verification & Testing Checklist

**A. Model layer (no hardcoding)**
- [ ] `model_chain(runtime, task)` returns ≥2 models (a chain, never a single default)
- [ ] No chain's first entry is `gemini-2.5-flash` ✅ *test exists and passes*
- [ ] Live discovery returns >0 free models; static list used only when offline ✅ *verified: 23 free*
- [ ] Failing a model benches it and the next is selected ✅ *test exists and passes*
- [ ] A benched model recovers after cooldown ✅ *test exists and passes*
- [ ] All models benched → still returns a chain (never a total outage) ✅ *test exists*

**B. MCP preflight**
- [ ] Every configured MCP reports `connected` **and** `tool_count > 0`
- [ ] A deliberately-broken server blocks the task when `required`
- [ ] An optional server down → task proceeds AND the agent is told it's unavailable
- [ ] `artifacts/mcp_preflight.json` written every run

**C. Plugin parity**
- [ ] Every non-OpenCode-specific plugin present in both Hermes and OpenCode
- [ ] Every Claude Code omission has a written reason in `claude_code_exclusions`
- [ ] Zero plugins in `unresolved` state at deploy time

**D. Anti-hallucination**
- [ ] Agents receive the *probed* tool list, not the configured one
- [ ] Studio verifies every claimed file write against the real filesystem ✅ *EXISTS*
- [ ] A stage that claims success with no artifact **fails** the gate

**E. Team workflow (from your zip)**
- [ ] Work branches from `development`, never `main`
- [ ] No agent approves or merges its own PR
- [ ] `qa-gate`, `build`, `test` pass before `development → main`

---

## 7. Honest gaps — what this plan does NOT yet cover

1. **8 plugins are `⚠️ VERIFY`** (octogent, opencode-morph-plugin, Plannotator, Hermes-WebUI,
   Impeccable, SkillUI, Crawl4AI, opencode-agent-skills). I will not fabricate install
   strings. Step 0 resolves them; unresolved ones are skipped, not assumed.
2. **"Oh my opencode" repo** — you mentioned it but the URL didn't come through. Send it and
   it gets folded into §3.
3. **Sub-agent ↔ sub-agent messaging** is not designed here. Today delegation is
   supervisor→agent. True peer messaging needs a message bus + loop/credit controls; that is
   its own design, not a config change.
4. **Per-task live benchmark research** ("Sakana Fugu") is implemented as *live discovery +
   task categorization*, deliberately **off** the voice hot path. A full web-benchmark crawl
   per selection would freeze the UI — the exact failure that caused the 83-second hang.

---

## 8. Recommended build order

1. **MCP preflight (§4)** — highest ROI; fixes a daily failure and removes a hallucination source.
2. **Plugin resolution Step 0 (§3)** — turns 8 unknowns into facts.
3. **task_kind in the router (§5)** — the seam the whole team model rests on.
4. **Team role → runtime wiring (§1)** — connects your zip's roles to real runtimes.
5. **Sub-agent messaging** — only after 1–4 are stable.
