# Nexi Agency Engine — Integration Report

Clean-room autonomous background workflow engine. **No CrewAI imported or copied; no CrewAI
branding in commands, files, logs, reports, or feature IDs** (concept kept, name dropped).
Isolated under `engine/agency/`. The live voice fast-path is untouched.

## What it is now (not a stub chatbot)
A workflow run carries a **goal** and a **plan**, and flows through agent passes:
`Planner → Research → ToolOperator → Verifier → Reflection → Report`, emitting events and a
markdown report artifact. Passes are **model-ready**: with `NEXI_AGENCY_AUTONOMY=true` they call
the Gemini brain; otherwise deterministic stubs (default — safe, offline, test-stable). Runs
**persist to JSONL** (survive restart) and can run **in the background** (voice thread stays free).

## Files (under `engine/agency/`)
| File | Role |
|---|---|
| `workflow_engine.py` | state + goal/plan + run-local memory + events + persistence + background runner + agent passes + autonomy modes |
| `__init__.py` | the 10 `nexi_*` Nexi tools |
| `nexi_tool_proxy.py` | safety boundary — mode + risk gating (low→execute+verify, risky→approval, locked→refuse) |
| `web_server.py` | optional stdlib `http.server` control API (127.0.0.1:8127, never auto-starts, no dependency) |
| `tests/test_nexi_agency_workflows.py` | engine, autonomy, persistence, proxy/modes, tools, routing, server, branding |

## Feature IDs (all `nexi_*`, route=tool, category=workflow)
`nexi_run_router_audit`, `nexi_run_codebase_research`, `nexi_run_test_generation`,
`nexi_run_integration_plan`, `nexi_workflow_status`, `nexi_agent_activity`,
`nexi_workflow_logs`, `nexi_workflow_artifacts`, `nexi_cancel_workflow`, `nexi_continue_workflow`.
Wired in `tool_registry.py` (+ `nexi_` dispatch), `groq_intent_router_v2.py` (aliases),
`intent_taxonomy.py` (whitelist). `command.py` / `src/orin` refactor untouched.

## Autonomy
- **Modes** (`NEXI_AGENCY_MODE`, default `supervised`): `locked` (no tools) · `manual` (every
  tool needs approval) · `supervised` (low-risk auto, risky → approval) · `autonomous_safe`
  (low auto, medium/high/critical → approval). Enforced in `nexi_tool_proxy`.
- **Background**: with autonomy on, `nexi_run_*` returns immediately ("working in the
  background…") and the crew runs in a daemon thread; ask `nexi_agent_activity`/`nexi_workflow_logs`.
- **Persistence**: `data/nexi/agency/workflow_runs.jsonl` (append + load-on-import).
- **HUD**: `EVENT_SINK` hook streams events; `nexi_agent_activity` exposes current agent/step.

## Live voice (after `python run.py`)
- "start an agent audit of the intent router" → `nexi_run_router_audit` (Planner builds a plan;
  console shows `[NEXI_AGENCY] … plan_created`). **Never says "CrewAI".**
- "show current agent activity" → `nexi_agent_activity` · "show agent logs" → `nexi_workflow_logs`
  · "show the agent report" → `nexi_workflow_artifacts` · "cancel workflow" → `nexi_cancel_workflow`.
- An agent action needing a tool routes through `nexi_tool_proxy` → approval (e.g. "click" pauses).

## Tests
`pytest tests/test_nexi_agency_workflows.py -q` → **15 passed** (plan/findings/reflection,
background completion, JSONL persistence, locked-mode refusal, approval gating, routing, stdlib
server, and "no CrewAI branding"). Engine + proxy have `__main__` self-checks. No deps, no temp files.

## Known limitations / next
- Model-backed passes are off by default (stub). Set `NEXI_AGENCY_AUTONOMY=true` (+ Gemini key)
  to make passes reason for real; `_model()` falls back to stub on any failure.
- ToolOperator does no tool by default (analysis-first); when a pass needs a tool it must call
  `nexi_tool_proxy.request_tool`. `ponytail:` comments mark the upgrade points.
