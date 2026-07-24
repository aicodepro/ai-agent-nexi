# DeepSeek Verification Audit — Existing Report Claims vs Actual Code

## Verdict: 10 correct, 2 wrong/stale, 2 partially correct

## Claims Verified CORRECT

| # | Claim | Evidence | Status |
|---|-------|----------|--------|
| 1 | `run.py` spawns 2 processes (UI + audio) | `run.py:114-115`: `Process(target=startNexi)`, `Process(target=listenHotword)` | ✅ |
| 2 | `startNexi()` → `main.main()` → Eel | `run.py:43-46`, `main.py:223-262` | ✅ |
| 3 | Audio process uses openWakeWord → Silero VAD → Groq ASR → command_queue | `run.py:67-86`, `engine/audio_wake_pipeline.py` | ✅ |
| 4 | Bridge pump thread consumes queue events | `runtime_bridge.py:393-425`: `start_ui_bridge_pump()` | ✅ |
| 5 | `command_bus.submit_user_command()` is true entrypoint | `command_bus.py:35` — called from bridge (line 197) and legacy Eel path (line 1753) | ✅ |
| 6 | `allCommands()` still has competing routing logic | `command.py:1746-1963` — pre-routing (steps 1-10) before router v2 (step 11) | ✅ |
| 7 | `groq_intent_router_v2.py` routes are: tool, clarify, brain, system, memory, training, workflow, react, followup, cancel, interrupt, reject, sleep, wake, feature_gap | `groq_intent_router_v2.py:288-423` — ALL confirmed | ✅ |
| 8 | Legacy router `route_intent()` still used as fallback | `command.py:1920` — called after v2 fails | ✅ |
| 9 | Router receives full tool registry manifest | `tool_manifest_loader.py:97-118`: `router_capability_manifest()` loads from `tool_registry.router_tool_manifest()` | ✅ |
| 10 | `NEXI_AUTO_FOLLOWUP_AFTER_TTS` defaults to false | `runtime_bridge.py:207-208`: `os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "false")` | ✅ |

## Claims Verified WRONG

| # | Claim | Actual | Evidence | Status |
|---|-------|--------|----------|--------|
| 1 | `speech_started` maps to "recognising" | **Maps to "listening"** | `runtime_bridge.py:54`: `EVENT_SPEECH_STARTED: "listening"` | ❌ OLD AUDIT WRONG |
| 2 | `react_planner.py` is "never called from main flow" | **Router v2 CAN route to `react` intent** at `groq_intent_router_v2.py:376-377`, but there's **no dedicated handler** in `_handle_product_intelligence_v2()` | Router identifies react intent but `command.py` handling is missing | ❌ PARTIALLY WRONG — router does route to `react`, but no handler exists for it |

## Claims Partially Correct

| # | Claim | Correction | Evidence |
|---|-------|-----------|----------|
| 1 | Follow-up uses legacy `takecommand()` | ✅ CORRECT — `command.py:520`: `query = takecommand()` in `_maybe_start_auto_followup()` | But ALSO: `command_bus.py:286-296` has transcript filter for voice commands. The follow-up path bypasses modern VAD/Groq pipeline. |
| 2 | Tool verification is "stub-level" | ✅ CORRECT — `tool_result_verifier.py:16-17` checks only path.exists() for 4 file tools, otherwise relies on explicit `verified: True` flag | However, some handlers DO set verified=True for real operations (e.g., tell_time, tell_joke always return verified=True) |

## Claims Needing Correction

| # | Old Claim | Corrected |
|---|-----------|-----------|
| 1 | "No ReAct planner connection" | Router v2 DOES route `_react_like()` at line 376-377 → `route="react"`, but `_handle_product_intelligence_v2()` in `command.py` has no case for `route="react"`. The react planner exists at `engine/react_planner.py` but is NOT wired into the main flow. |
| 2 | "Follow-up routing in allCommands() runs BEFORE router v2" | Workflow dialog (line 1825-1838) runs BEFORE v2 (line 1856). Memory (line 1842) and output (line 1849) also run before v2. This means workflow dialog, memory, and output commands intercept BEFORE v2 can see them. |
| 3 | "config/tool_manifest.json is stale" | It's BYPASSED as source of truth — runtime registry is authoritative (`tool_manifest_loader.py:97-118`). JSON is only used for optional alias overlay. |
