# Agency Readiness Report — Verified

## Classification: **Config-Gated Autonomous** (tool-backed, model-ready, disabled by default)

## Agency Engine Architecture

```
user says "run an agent audit of the intent router"
  → router v2 intent="nexi_run_router_audit"
  → execute_tool("nexi_run_router_audit")
    → engine.agency.nexi_run_router_audit(slots)
      → _run("router_audit", ...)
        → workflow_engine.create_run(type, goal, background=...)
          → if background=True: returns immediately, runs in thread
          → if background=False: runs synchronously
        → 6-pass loop: planner → research → tool → verify → reflect → report
```

## Autonomy Gate

`workflow_engine.py:33-34`:
```python
def autonomy_enabled() -> bool:
    return str(os.getenv("NEXI_AGENCY_AUTONOMY", "")).strip().lower() in {"1", "true", "yes", "on"}
```

**Default: disabled** (empty string → False). Not documented in `.env.example`.

## Background Execution

`__init__.py:36-43`:
```python
if background:  # autonomous: return immediately
    return _ok(f"Started the {wtype} agent workflow ({run.run_id}). "
               f"I'll work on it in the background...")
```

When `NEXI_AGENCY_AUTONOMY=true`, the workflow runs in a daemon thread. When false, it runs synchronously.

## Pass Functions (workflow_engine.py)

| Pass | File | Backed By | Status |
|------|------|-----------|--------|
| Planner | `workflow_engine.py:249-274` | LLM (Gemini) when autonomy=true, stub otherwise | ✅ model-ready |
| Research | `workflow_engine.py:276-299` | Gemini + file/web read tools | ✅ model-ready |
| Tool | `workflow_engine.py:301-329` | Proxy → approval gate + executing tools | ✅ tool-backed |
| Verify | `workflow_engine.py:331-349` | Gemini reflection + tool result check | ✅ model-ready |
| Reflect | `workflow_engine.py:351-373` | Gemini + memory update | ✅ model-ready |
| Report | `workflow_engine.py:375-396` | Gemini-generated report → artifact | ✅ model-ready |

## Approved Tools (via nexi_tool_proxy)

The agency engine can use: `open_app, open_website, web_search, search_youtube, read_current_page, list_browser_tabs, read_browser_console, browser_click, browser_fill, screen_read, click_ui_element, type_text`

ALL gated by `approval_queue` for high/critical risk.

## HUD Integration

- `presence_state.py` — tracks mode, attention, current_goal, last_event
- `workflow_engine.py:30` — `EVENT_SINK` hook for HUD updates
- Dashboard events sent via `EVENT_DASHBOARD_UPDATE` through bridge

## Persistence

- `data/nexi/agency/workflow_runs.jsonl` — JSONL-based persistence
- Survives restart
- Each run has: run_id, workflow_type, goal, status, plan, findings, artifacts, logs

## Defects

1. **NEXI_AGENCY_AUTONOMY not in .env.example** — users never discover it
2. **Single workflow at a time** — `_RUNS` dict in workflow_engine.py supports multiple runs but only one runs at a time
3. **No inter-pass recovery** — if a pass fails, no retry or alternative path
4. **Tool proxy approval is synchronous** — waiting for approval blocks the pass
5. **No workflow orchestration web UI** — only CLI/voice interaction
