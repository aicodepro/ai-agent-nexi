# Final Autonomy Gap Analysis: Nexi/Jarvis

## Executive Summary

Nexi has a comprehensive architecture with TWO intent routers, a rich tool registry with slot validation, a voice state machine, follow-up tracking, and an agency engine. **However, the system is architecturally complete but behaviorally defaulted to passive/hibernating.** Almost all autonomy-enabling features are gated behind environment variables that default to `false`. The system wakes, processes one command, speaks, and sleeps — by design, not by oversight.

## Critical Gaps (9/9 — ALL PRESENT)

### Gap 1: Follow-up Listening is OFF by Default

**Evidence**: `runtime_bridge.py:207-208`
```python
auto_followup = (os.getenv("NEXI_AUTO_FOLLOWUP_AFTER_TTS", "false") ...)
```
**Impact**: After every TTS response, `handle_bridge_event()` calls `_finish_session()` (line 215-217) by default, killing the session. The system can't chain commands.

**Severity**: CRITICAL — This is the single biggest blocker to the "desktop operator" feel.

**Fix**: Change default to `true`, or ensure the `_maybe_start_auto_followup()` path in `speak()` reliably overrides this.

### Gap 2: Agency Engine is OFF by Default

**Evidence**: `engine/agency/__init__.py` — `NEXI_AGENCY_AUTONOMY` env var, not set in `.env.example`.

**Impact**: The pass-based workflow engine (planner→research→tool→verify→reflect→report) requires explicit env activation. Without it, Nexi is a command-response system.

**Severity**: HIGH — No background task execution without this.

**Fix**: Default to auto mode, or at minimum document in `.env.example`.

### Gap 3: No Post-Brain Output Classifier

**Evidence**: `engine/command.py` — `_mark_question_response()` uses only `response_asks_question()` (checks for `?`). `engine/assistant_response.py:41` — pure text-based detection.

**Impact**: When route="brain", Gemini's free-form text goes directly to TTS. If Gemini rambles, hallucinates, suggests an action, or returns an error, there's no mechanism to classify, filter, or restructure the output. The system cannot distinguish "I'll open Chrome for you" (should execute) from "Chrome is a browser by Google" (should speak).

**Severity**: HIGH — Brain output is 100% uncontrolled.

**Fix**: Add post-brain classifier that returns structured output: `{type: "answer" | "action_suggestion" | "error" | "clarification" | "unsafe", content: "...", confidence: 0.95}`.

### Gap 4: No ReAct Planner Integration

**Evidence**: `engine/react_planner.py` exists and is registered as a tool route but is NOT connected to the main flow. `_handle_product_intelligence_v2()` never calls it by default.

**Impact**: Multi-step reasoning (e.g., "book a flight, then check the weather at my destination") has no built-in handling. Each step must be a new command.

**Severity**: HIGH — No compound task execution.

**Fix**: Wire `react_planner.py` as a fallback when route != "tool" and confidence < 0.7.

### Gap 5: Tool Result Verification is Stub-Level

**Evidence**: `engine/tool_result_verifier.py` — Only checks `os.path.exists()` for `create_file` and `create_folder`.

**Impact**: The system can't confirm if:
- An app actually opened (vs. failed silently)
- A web page loaded (vs. error page)
- A search returned useful results (vs. "no results found")
- A file was written with correct content

**Severity**: HIGH — System has no self-check ability.

**Fix**: Add tool-specific verifiers (e.g., `verify_app_opened(app_name)` → check `tasklist.exe`).

### Gap 6: Single-Active Workflow State

**Evidence**: `engine/workflow_state.py` — single `_active_workflow` attribute, no queuing.

**Impact**: Only ONE workflow can be active at a time. A workflow started but not completed blocks all other workflows. No background/parallel workflow support.

**Severity**: MEDIUM — Workflow system is effectively single-threaded.

**Fix**: Add workflow queue with pause/resume/cancel management.

### Gap 7: Brain Provider is Hard-Coded to Gemini

**Evidence**: `engine/features.py:598-619` — `chatBot()` uses `_get_provider()` which returns Gemini by default. `engine/providers/provider_registry.py` has DeepSeek/GLM/Qwen/Kimi/MiniMax but they're not auto-wired.

**Impact**: Single point of failure. If Gemini is down or slow, the system has no fallback LLM for Q&A.

**Severity**: MEDIUM — Air-gap or offline use requires different provider.

**Fix**: Wire provider registry into `features.chatBot()` with fallback chain.

### Gap 8: Follow-up Uses Legacy `takecommand()` Instead of Modern Pipeline

**Evidence**: `engine/command.py:502-525` — `_maybe_start_auto_followup()` calls `takecommand()` which opens a new mic stream using SpeechRecognition (not the modern wake pipeline with VAD + Groq ASR).

**Impact**: Follow-up input bypasses:
- VAD noise rejection
- Groq Whisper ASR accuracy
- Session sequence number tracking
- Wake session lifecycle

**Severity**: MEDIUM — Follow-up audio quality is degraded.

**Fix**: Wire follow-up through `command_bus` instead of `takecommand()`.

### Gap 9: No Approval Timeout for High-Risk Actions

**Evidence**: `engine/approval_queue.py` — `approve_next()` and `reject_next()` have no timeout mechanism.

**Impact**: If UI is not visible (headless mode) or user doesn't respond, high-risk actions block the system indefinitely. No voice prompt for pending approvals.

**Severity**: MEDIUM — Silent stall on high-risk actions.

**Fix**: Add configurable timeout that auto-rejects after N seconds with TTS notification.

## Architectural Strengths (What Works Well)

1. **Intent Router V2** — Rich schema (14 routes, slot validation, clarification, confidence scoring, LLM fallback)
2. **Voice State Machine** — Clear 8-state lifecycle with transition guards
3. **Tool Registry** — Comprehensive `ToolSpec` with required/optional slots, risk levels, aliases
4. **Clarification Flow** — Multi-turn slot filling works through router + workflow + followup pipeline
5. **Session Lock** — Prevents concurrent wake sessions via `wake_session_manager`
6. **Approval Queue** — Clear risk-based gating for dangerous actions
7. **UI State Emission** — Canonical state manager (`ui_state_manager.py`) with proper state mapping
8. **Barge-in Support** — Interrupt controller to stop TTS mid-speech
9. **Test Coverage** — 329 test files, well-structured, good coverage of router + pipeline

## Fix Priority

```
CRITICAL (P0):
├── Gap 1: Change NEXI_AUTO_FOLLOWUP_AFTER_TTS default to true

HIGH (P1):
├── Gap 3: Add post-brain output classifier
├── Gap 4: Wire ReAct planner into main flow
├── Gap 5: Implement proper tool result verification
└── Gap 2: Enable agency engine by default or document env

MEDIUM (P2):
├── Gap 8: Wire follow-up through modern pipeline
├── Gap 7: Wire provider registry fallback
├── Gap 6: Add workflow queuing
└── Gap 9: Add approval timeout
```

## Behavioral Outcome After Fixes

With ALL gaps addressed, the system would:
1. Wake → command → respond → **auto-listen for follow-up** (instead of sleeping)
2. Classify brain output → detect action suggestions → offer to execute
3. Execute multi-step tasks via ReAct planner
4. Verify tool results → confirm success/failure
5. Run background workflows via agency engine
6. Fallback between multiple LLM providers
7. Time-out high-risk approvals with voice notification
8. Queue and manage multiple workflows

Without fixes → chatbot that wakes, responds to one query, and sleeps.
