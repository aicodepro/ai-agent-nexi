# CrewAI-style Workflow Plugin — Integration Report

Clean-room (no CrewAI source copied, repo not merged). Isolated under
`engine/integrations/crewai_style/`. Background multi-agent workflows only — the live
voice fast-path is untouched.

## Summary
A stdlib in-memory workflow engine runs a fixed "crew" pass (Manager → Research → Audit →
Test → Verify → Report) that emits events/logs and writes a markdown report artifact. It is
exposed to Nexi as 7 voice tools and (optionally) over a local FastAPI control API. All
agent tool use is forced through a safety proxy → Nexi's approval gate.

## Files created
| File | Role |
|---|---|
| `engine/integrations/__init__.py`, `engine/integrations/crewai_style/__init__.py` | package + the 7 Nexi tool fns |
| `engine/integrations/crewai_style/workflow_engine.py` | models + state + run-local memory + events + runner + agent passes (stdlib) |
| `engine/integrations/crewai_style/nexi_tool_proxy.py` | safety boundary (low→execute+verify, risky→approval gate, unknown→refuse) |
| `engine/integrations/crewai_style/web_server.py` | optional FastAPI API (import-guarded, 127.0.0.1:8127, never auto-starts) |
| `tests/test_crewai_style_workflows.py` | engine, proxy, tools, routing, server-health |

**ponytail collapse:** the spec's 12 files → 5. `models.py / workflow_state.py /
workflow_memory.py / event_bus.py / workflow_runner.py / agents.py / workflow_registry.py`
are folded into `workflow_engine.py` (one consumer, no isolation need yet). 6 agent classes →
named pass-functions taking `(run, ctx)` so a pass can become a real LLM call in place. Event
bus → one optional `EVENT_SINK` hook. Split any of these out when a second consumer needs it.

## Files modified (clean files only)
- `engine/tool_registry.py` — 7 `_spec`s (category `workflow`) + one `crewai_*` dispatch branch.
- `engine/groq_intent_router_v2.py` — alias routes for the 7 tools.
- `engine/intent_taxonomy.py` — 7 names in `ALLOWED_INTENTS` + `TOOL_INTENTS`.
- `command.py` / `src/orin` refactor: **not touched** (per standing instruction).

## Feature IDs / routes
`crewai_run_router_audit`, `crewai_run_codebase_research`, `crewai_run_test_generation`,
`crewai_run_integration_plan`, `crewai_workflow_status`, `crewai_workflow_logs`,
`crewai_cancel_workflow` — all `route=tool` (execute in-process; no `command.py` `route=workflow`
handler needed). Example: "run an agent audit of the router" → `crewai_run_router_audit`.

## Web server endpoints (optional)
`GET /health · GET/POST /workflows · GET /workflows/{id} · /events · /logs · /artifacts ·
POST /workflows/{id}/continue · /cancel`. Run: `.venv\Scripts\python -m engine.integrations.crewai_style.web_server`.
Requires `pip install fastapi uvicorn` (not installed; engine + voice tools work without it).

## Tests
`pytest tests/test_crewai_style_workflows.py -q` → **10 passed, 1 skipped** (server test skips
without fastapi). Routing/registry regression → 144 passed. Engine + proxy have `__main__`
self-checks. No temp/scratch files created.

## Safety
- Agents never touch the PC. `nexi_tool_proxy.request_tool` is the only path to tools:
  low-risk → `execute_tool` (verified); medium/high/critical → `approval_queue.gate` (queued,
  never executed); unknown → `tool_not_available`. Verified by `test_proxy_*`.
- Workflow memory is run-local; Nexi's autonomous memory remains source of truth.

## Known limitations / next phase
- Agent passes are deterministic placeholders — wire Groq/Gemini into a pass when needed
  (signature already `(run, ctx)`).
- Runs are synchronous (passes are instant) + in-memory only — move to a thread + persistence
  when a pass does real IO. `ponytail:` comments mark both upgrade paths.
- Web server needs `fastapi`/`uvicorn` installed to run.
