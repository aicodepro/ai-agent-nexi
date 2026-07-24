# Agency Engine Audit

## Architecture

`engine/agency/` contains the **Nexi Agency Engine** — an experimental autonomous background workflow system.

### Files
- `engine/agency/__init__.py` — Feature registration, tool wrappers
- `engine/agency/workflow_engine.py` — 6-pass execution: planner→research→tool→verify→reflect→report
- `engine/agency/nexi_tool_proxy.py` — Tool proxy with safety gate

### How It Works

`workflow_engine.py:116` — `run_workflow_pass()`:
```python
def run_workflow_pass(pass_name, context):
    ...
    next_pass = PASS_ORDER[pass_name]
    context["pass"] = next_pass
    ...
```

6 passes executed sequentially:
1. `planner` — Determines what to do
2. `research` — Gathers information (web search, file read)
3. `tool` — Executes tools (if research succeeded)
4. `verify` — Checks tool results (minimal: path exists check)
5. `reflect` — Considers if results are sufficient
6. `report` — Generates final response

### AI Router Integration

In `__init__.py:52-155`, there's an `ai_router_mode_auto()` function that:
1. Checks `NEXI_AGENCY_AUTONOMY` env var (default: not set)
2. If enabled → uses `groq_intent_router_v2.py` preferentially, with agency fallback
3. Exposes `nexi_run_router_audit`, `nexi_fix_router_slot`, `nexi_refresh_manifest` as tools

### Agency Tools (exposed as Nexi features)

From `__init__.py`:
- `ai_lookup_route` — Re-route a command through the AI router
- `nexi_run_router_audit` — Diagnose routing issues
- `nexi_fix_router_slot` — Fix slot assignment issues
- `nexi_refresh_manifest` — Refresh tool manifest
- `nexi_manual_override_tool` — Force a tool execution with custom parameters

### Persistence

- `data/nexi/agency/` — Workflow run persistence directory
- Contains subdirectories with run IDs, logs, and results

### Critical Findings

1. **DISABLED BY DEFAULT** — `NEXI_AGENCY_AUTONOMY` is not set in `.env.example`. The agency engine and its tools are registered but the AI router mode is not active by default.

2. **STUB-VALIDATION** — The verification pass (`nexi_tool_proxy.py`) does path-existence checks only. No semantic verification, no result quality assessment.

3. **NO BACKGROUND EXECUTION** — Passes run sequentially in the foreground. The agency engine is synchronous, not background processing.

4. **LIMITED RECOVERY** — If a pass fails, there's no retry logic or alternative path selection. The error propagates up.

5. **SINGLE-WORKFLOW CONCURRENCY** — The `workflow_state.py` only supports one active workflow at a time. No queuing, no parallel workflows.
