# DeepSeek Final Verdict — Nexi Autonomy Audit

## 1. Current Status
**Partially autonomous** — Architecturally complete but configured passive. The system has all the pieces (router v2, tool registry, slot validation, follow-up tracking, agency engine, safety gates, state machine) but key env vars default to `false`, turning a capable desktop operator into a single-command chatbot.

## 2. Main Reason It Feels Like a Chatbot

**One command, one response, then sleep.** The single root cause is: `NEXI_AUTO_FOLLOWUP_AFTER_TTS` defaults to `false` at `runtime_bridge.py:207-208`, which means after every command TTS completes, the bridge calls `_finish_session()` (line 215), releases the session lock, and Nexi goes to sleep. Even though the `speak()` function has its own follow-up mechanism via `_maybe_start_auto_followup()`, it runs in a race with the bridge's session finish and uses legacy `takecommand()` (SpeechRecognition) instead of the modern VAD/Groq pipeline. Without chained commands, the system feels like a Q&A chatbot, not an autonomous operator.

## 3. Confirmed Architecture

| Subsystem | Status | Evidence |
|-----------|--------|----------|
| **Runtime** | 2-process (UI + audio), bridge queue | `run.py:114-115`, `runtime_bridge.py:393-425` |
| **Voice** | openWakeWord + Silero VAD + Groq ASR | `engine/audio_wake_pipeline.py` |
| **State Machine** | 8-state lifecycle with guards | `engine/voice_state_machine.py` |
| **Router** | v2 deterministic + LLM (Groq), legacy fallback | `engine/groq_intent_router_v2.py`, `engine/intent_router.py` |
| **Router Features** | 14+ route types, slot validation, clarification, confidence scoring | All confirmed via code inspection |
| **Brain** | Gemini default, hardcoded in features.py | `engine/features.py:598-619` |
| **Tool Registry** | 100+ ToolSpecs with required/optional slots, risk levels, aliases | `engine/tool_registry.py:48-159` |
| **Agency Engine** | 6-pass workflow planner→research→tool→verify→reflect→report | `engine/agency/workflow_engine.py` |
| **Safety** | Approval queue (min_risk=high), safety gate, verifier | `engine/approval_queue.py`, `engine/safety_gate.py` |
| **Memory** | Semantic, episodic, session, preference, correction, reflection | `engine/memory/` subsystem |
| **UI** | State manager, presence HUD, dashboard | `engine/ui_state_manager.py`, `engine/presence_state.py` |
| **Tests** | 2116 pass / 86 fail (67 module-import, 19 real) | Verified via `pytest` |

## 4. Confirmed Defects

| Severity | Defect | Evidence | Impact | Fix |
|----------|--------|----------|--------|-----|
| **P0** | `NEXI_AUTO_FOLLOWUP_AFTER_TTS=false` by default | `runtime_bridge.py:207-208` | Session dies after every command. No follow-up listening. | Change default to `true` + add to `.env.example` |
| **P0** | Follow-up uses legacy `takecommand()` not modern pipeline | `command.py:502-525` | Follow-up audio bypasses VAD + Groq ASR, uses SpeechRecognition | Wire follow-up through command_bus directly |
| **P0** | `_FOLLOWUP_SOURCES` missing `"double_clap"` | `command.py:482` vs pipeline source values | Double clap wakes can never auto-follow-up | Add `"double_clap"` to `_FOLLOWUP_SOURCES` |
| **P1** | No post-brain classifier | `features.py:598-619`, `command.py:166-206` | Gemini output goes to TTS unfiltered. Action suggestions, unsafe content, errors spoken directly | Add structured output classifier |
| **P1** | ReAct planner has no handler in allCommands | `groq_intent_router_v2.py:376-377` routes `react`, but `_handle_product_intelligence_v2()` has no case for it | Multi-step tasks routed but not executed | Add `react` case to `_handle_product_intelligence_v2()` |
| **P1** | Tool result verifier is stub-level | `tool_result_verifier.py:16-17` | Only checks `path.exists()` for 4 file tools | Add tool-specific verifiers |
| **P1** | `NEXI_AGENCY_AUTONOMY` not documented in `.env.example` | `.env.example` line 1-92 | Users never know agency engine exists | Add to `.env.example` |
| **P1** | Bridge path wins over auto-follow-up race | `runtime_bridge.py:213-215` vs `command.py:368-369` | Bridge's `_finish_session()` can race with `_maybe_start_auto_followup()` | Coordinate session finish between paths |
| **P2** | Brain provider is hardcoded to Gemini | `features.py:598-619` vs `providers/provider_registry.py` | No fallback if Gemini is down | Wire provider registry into fallback chain |
| **P2** | Workflow state is single-active | `workflow_state.py` | Only one workflow at a time | Add workflow queue |
| **P2** | Approval queue has no timeout | `approval_queue.py` | High-risk actions block indefinitely | Add configurable auto-reject timeout |
| **P2** | Some tools have only optional slots | `click_ui_element`, `type_text`, `weather_lookup` | Execute with empty values → silent failure | Add required slot or guard |

## 5. Router and Follow-up Diagnosis

**Router**: The v2 router at `groq_intent_router_v2.py` is cohesive and well-structured. It has:
- A deterministic phase (exact matches, regex, aliases) — fast, model-independent
- An LLM phase (Groq with capability manifest) — handles fuzzy/ambiguous input
- Slot enrichment via `llm_parameter_extractor.py`
- Confidence scoring via `confidence_manager.py`
- Schema validation via `intent_validator.py`
- Normalization via `slot_normalizer.py`

The problem is not the router itself — it's what happens AFTER routing.

**Follow-up**: The follow-up pipeline is fractured across THREE paths:
1. `speak()` → `_maybe_start_auto_followup()` → `takecommand()` (legacy, in command.py)
2. `runtime_bridge.py:207-215` → checks `NEXI_AUTO_FOLLOWUP_AFTER_TTS` (default false)
3. `_handle_product_intelligence_v2()` → `_respond_to_user()` → `ask_user()` → `speak()` + `_maybe_start_auto_followup()`

These paths compete and the bridge's `_finish_session()` typically wins, killing the session.

## 6. Brain/Gemini Diagnosis

**Uncontrolled**: Gemini output goes through:
1. `features.chatBot()` → `ask_brain()` → Gemini generates text
2. `guard_unverified_action_message()` — text pattern filter (not a classifier)
3. `speak()` → `_mark_question_response()` — checks for `?` only

No structured output, no action detection, no safety filter, no confidence assessment. The system trusts Gemini to not hallucinate actions or return unsafe content.

## 7. Agency Engine Diagnosis

**Config-gated autonomous**: The agency engine is:
- **Tool-backed** — can execute real tools through the proxy
- **Model-ready** — each pass uses Gemini when `NEXI_AGENCY_AUTONOMY=true`
- **Stub-default** — without the env var, passes use deterministic stubs
- **Background-capable** — runs in daemon thread when autonomy enabled
- **Persistent** — workflow runs survive restart via JSONL

It is NOT stub-only. It's a real, working multi-agent workflow engine. But it is invisible to users because `NEXI_AGENCY_AUTONOMY` is not in `.env.example`.

## 8. Safety Diagnosis

Gaps:
- **Brain output bypasses ALL safety** — route="brain" has no gate, no filter, no verifier
- **Verifier is file-path only** — no semantic verification for app opens, web searches, browser actions
- **No approval timeout** — high-risk actions block indefinitely
- **Medium-risk tools skip approval** — create_folder, open_website are medium but don't require confirmation

## 9. Top Fix Order (Implementation-Ready)

```
Sprint 1 — Immediate (P0):
  1. Change NEXI_AUTO_FOLLOWUP_AFTER_TTS default to true
  2. Add "double_clap" to _FOLLOWUP_SOURCES  
  3. Add NEXI_AUTO_FOLLOWUP_AFTER_TTS to .env.example

Sprint 2 — Router + Follow-up (P1):  
  4. Wire follow-up through command_bus instead of takecommand()
  5. Add react route handler to _handle_product_intelligence_v2()
  6. Coordinate session finish between speak() and runtime_bridge

Sprint 3 — Brain Safety (P1):
  7. Add post-brain classifier (answer/action_suggestion/unsafe/error)

Sprint 4 — Verification (P1):
  8. Add tool-specific verifiers (verify_app_opened, verify_page_loaded)

Sprint 5 — Discovery (P1-P2):
  9. Add NEXI_AGENCY_AUTONOMY to .env.example
  10. Add approval timeout
  11. Wire provider registry as fallback chain
```

## 10. Implementation Prompt for Next Phase

```
Fix Nexi follow-up pipeline so the system chains commands instead of sleeping after every response:
1. Change NEXI_AUTO_FOLLOWUP_AFTER_TTS default from "false" to "true" in runtime_bridge.py
2. Add "double_clap" to _FOLLOWUP_SOURCES set in command.py
3. Add NEXI_AUTO_FOLLOWUP_AFTER_TTS=true to .env.example
4. Wire _maybe_start_auto_followup() through command_bus instead of legacy takecommand()
5. Ensure speak() follow-up does not race with bridge _finish_session()
Verify: after "What time is it?" the system stays listening for follow-up, and after "open" → "Which app?" → Chrome opens.
```

## 11. Live Commands to Validate

| Command | Expected Router | Expected State Chain | Expected Follow-up |
|---------|----------------|----------------------|-------------------|
| "Hey Nexi, open up" | clarify → open_app, missing app_name | online → listening → recognising → thinking → saying → listening | ✅ "Which app?" → auto-listen |
| "Chrome" (after above) | tool → open_app, app_name=chrome | → thinking → saying → sleep | Should open Chrome |
| "Hey Nexi, what time is it?" | tool → tell_time | → thinking → saying → listening (if auto-followup on) | Should speak time, then wait |
| "Hey Nexi, create a folder" | workflow → create_folder | → thinking → saying → listening | ✅ "What should I name it?" |
| "reports" (after above) | workflow → create_folder fill | → thinking → saying → sleep | Should create folder |
| "Hey Nexi, plan my AI assistant demo" | brain → general_qa | → thinking → saying → sleep/listening | Gemini responds, follow-up if ? |
| "Hey Nexi, show current agent activity" | tool → nexi_agent_activity | → thinking → saying → sleep | Reports agent state |
| "Hey Nexi, click the submit button" | tool → click_ui_element, target=submit | → thinking → approval → saying → sleep | Requires approval, risk=high |
| "reject" (after above) | followup → reject | → thinking → saying → sleep | Rejects pending approval |
