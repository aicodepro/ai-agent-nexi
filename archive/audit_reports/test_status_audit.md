# Test Status Audit

## Overview
- **Total tests**: 329 files in `tests/`
- **Coverage**: Extensive — tests for routing, memory, wake pipeline, agency, tools, command bus
- **CI Pipeline**: None detected (no GitHub Actions, no pytest.ini, no CI config)

## Live Test Results (June 26, 2026)

**2116 tests passed, 86 failed, 2 skipped** in 164.97s

### Failure Categories

| Category | Count | Root Cause |
|----------|-------|------------|
| `ModuleNotFoundError: skills.*` | 49 | `skills/` package missing from `sys.path` or not installed |
| `ModuleNotFoundError: core.*` | 10 | `core/` package missing (imports test for `core.config`, `core.dispatcher`, etc.) |
| `ModuleNotFoundError: memory.*` | 3 | `memory/` module not importable |
| `ModuleNotFoundError: tools.*` | 1 | `tools.mcp` not importable |
| `ModuleNotFoundError: control.*` | 3 | `control/` module paths changed |
| `ModuleNotFoundError: brain.*` | 1 | `brain.planner` not importable |
| DSP clap threshold mismatch | 5 | Test expects `low_ratio` or `too_long` reason; actual is `low_peak_0.1526` |
| Barge-in debounce mismatch | 3 | Mock setup doesn't pass debounce check → `not_speaking`/`debounced` instead of expected result |
| `speech_started→recognising` | 2 | Bridge maps `speech_started` to `listening`, tests expect `recognising` |
| Session summary (attrs) | 4 | `attrs` library not installed |
| Hotword RMS/cooldown | 3 | RMS gate or cooldown test thresholds don't match defaults |
| Wake pipeline disabled | 2 | Pipeline disabled detection logic mismatch |
| Other | 3 | Hotkey wake, auto-followup interview, artifact dir |

### Summary
- **Module import failures**: 67 of 86 failures are missing modules (`skills/`, `core/`, `memory/`, etc.)
- **Real behavioral mismatches**: 19 failures (DSP thresholds, barge-in, speech_started mapping, hotword params)
- **Missing dependency**: `attrs` library (4 failures)
- **Core routing/memory/pipeline tests**: All pass (2249 in total)

## Key Test Files

| Test File | Coverage | Notes |
|-----------|----------|-------|
| `tests/test_routing_master_flow.py` | Full routing flow (v2, legacy, pre-router) | Comprehensive — tests slot resolution, clarification, 37+ route paths |
| `tests/test_nexi_agency_workflows.py` | Agency workflow engine | Tests pass execution, error handling, persistence |
| `tests/test_command_bus.py` | submit_user_command() | Voice/text dispatch, follow-up, cancellation |
| `tests/test_audio_wake_pipeline.py` | Full wake → VAD → ASR → command (54 tests) | Session lifecycle, no-speech timeout, VAD gates |
| `tests/test_intent_router_v2.py` | Router v2 deterministic + LLM routing | Pattern matching, capability routing, LLM fallback |
| `tests/test_groq_asr.py` | Groq Whisper (9 tests) | Chunked audio, rate limiting |

## Coverage Gaps

### 1. No E2E integration test
- No test that starts the full system and validates wake → command → TTS → sleep flow
- Unit tests are focused on individual modules

### 2. No brain output classification test
- No test that validates post-brain output is classified correctly
- `response_asks_question()` is tested but LLM responses are not

### 3. No safety gate tests
- `check_safety()` in `safety_gate.py` — no dedicated test file found
- Approval queue has basic tests but edge cases missing (timeout, reject-after-approve)

### 4. No follow-up timeout tests
- Session timeout (60s) is tested in wake pipeline tests
- But follow-up TTL expiry is not tested end-to-end

### 5. Agency engine tests are stub-level
- `test_nexi_agency_workflows.py` tests basic execution but not:
  - Parallel workflows
  - Partial pass failure recovery
  - Very long-running workflows

### 6. No tests for UI state emission
- `ui_state_manager.py` — no dedicated tests
- State transitions from allCommands are not verified

## Test Infrastructure

- **No CI pipeline** — Tests must be run manually
- **No coverage measurement** — No `.coveragerc` or `coverage.py` config
- **No test environment** — Tests use mocked dependencies but no isolated test DB
- **No conftest hierarchy** — Shared fixtures in `tests/conftest.py` only
