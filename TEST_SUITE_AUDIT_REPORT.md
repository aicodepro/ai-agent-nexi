# Nexi AI Assistant — Test Suite Quality Audit Report

**Date:** 2026-07-21  
**Auditor:** Code Reviewer Agent  
**Scope:** `E:\ai-agnet-nexi\tests\` (375 files, flat directory)

---

## Executive Summary

| Metric | Value |
|--------|-------|
| Total test files | 375 |
| Directory structure | Flat (no subdirectories) |
| Files using `@pytest.fixture` | 47 |
| Files using `@pytest.mark.parametrize` | 24 |
| Files with zero assertions | 0 |
| Conftest fixtures | 0 (safety patches only) |
| CI/pytest configuration | **NONE** |
| Coverage breadth | Diverse (wake, voice, vision, memory, intent, safety, studio, etc.) |
| Coverage depth | **Highly uneven** (from 46-line smokes to 1101-line exhaustive tests) |

**Overall assessment: Good breadth, uneven depth, no CI integration, no organizational structure.**

The suite covers most major subsystems but has critical gaps in CI integration, organizational structure, shared fixtures, and end-to-end/integration testing. Individual test files range from excellent (well-mocked, parametrized, edge-case-rich) to skeletal (single-happy-path-only).

---

## 🔴 Critical Findings

### CRIT-001: No CI or pytest Configuration
**Severity:** 🔴 Blocker  
**Files affected:** N/A (project-wide)

No `pytest.ini`, `pyproject.toml` with pytest config, `setup.cfg`, or CI workflow files (`.github/workflows/*.yml`, `.gitlab-ci.yml`) exist anywhere in the project.

**Impact:** Tests cannot run in CI. No markers registered (`slow`, `integration`, `smoke`). No default test paths, timeout settings, or coverage reporting configured. Every developer must know the invocation incantation manually.

**Recommendation:**
- Create `pyproject.toml` with `[tool.pytest.ini_options]` specifying testpaths, markers, and asyncio mode (if used).
- Add a GitHub Actions workflow (`.github/workflows/test.yml`) to run tests on push/PR.
- Add `pytest-cov` and configure coverage reporting.

---

### CRIT-002: Single Flat Directory — No Organizational Structure
**Severity:** 🔴 Blocker  
**Files affected:** All 375 test files

Every test file lives in `tests/` with no subdirectories. There is no grouping by subsystem (wake, voice, vision, memory, etc.), no separation of unit/integration/e2e tests.

**Impact:** Hard to navigate, impossible to run targeted test subsets without filename glob patterns. No way to apply different configs or fixtures to different test tiers.

**Recommendation:**
- Create subdirectories: `tests/unit/`, `tests/integration/`, `tests/smoke/`.
- Further organize unit tests by subsystem: `tests/unit/wake/`, `tests/unit/voice/`, etc.
- Use `__init__.py` files in each directory for package-relative imports.

---

### CRIT-003: No Integration or End-to-End Tests
**Severity:** 🔴 Blocker  
**Files affected:** N/A

Only 1 file references "integration" in its patterns; no true end-to-end tests exist that verify the full wake→ASR→intent→TTS→sleep cycle or the forge engine→agent→output pipeline.

**Impact:** Component-level unit tests pass in isolation, but the system may fail when components interact. No regression protection for cross-cutting concerns (session lifecycle, state propagation, UI updates).

**Recommendation:**
- Create `tests/integration/` with at minimum:
  - Wake-to-command: simulated audio → pipeline → intent router → command bridge
  - Session lifecycle: wake → listen → ASR → command → TTS → sleep (all mocked)
  - Safety integration: intent router → action gate → permission manager

---

## 🟡 Significant Findings

### SIGN-001: Single conftest.py with Zero Fixtures
**Severity:** 🟡 Suggestion  
**File:** `tests/conftest.py` (41 lines)

The conftest provides excellent global safety patches (pyautogui, keyboard, subprocess taskkill) but exports **zero pytest fixtures**. Every test file that needs mocks creates them inline.

**Impact:** Massive code duplication. Mock patterns are repeated across 47+ files. Changing a mock signature requires editing dozens of files.

**Recommendation:**
- Add shared fixtures to conftest.py:
  - `mock_wake_pipeline()` — returns a configured `AudioWakePipeline` with scripted scorers
  - `mock_session_manager()` — returns a `WakeSessionManager` with known session ID
  - `mock_groq_client()` — returns a `MagicMock` with canned ASR/TTS responses
  - `mock_intent_router()` — returns a router with known intent mapping
- Also consider a `tests/conftest_factories.py` for factory functions that are too complex for fixtures.

---

### SIGN-002: Uneven Test Depth — Some Files Are Skeletal
**Severity:** 🟡 Suggestion  
**Examples:**
- `test_voice_first_smooth.py`: 46 lines, 6 tests (minimal)
- `test_desktop_control.py`: 58 lines, 9 tests
- `test_window_control.py`: 63 lines, 8 tests
- `test_chrome_control.py`: 74 lines, 12 tests

**Impact:** Critical control-surface features have minimal coverage. Desktop control, window management, and Chrome automation likely have many failure modes not tested.

**Recommendation:**
- Add parametrized tests for edge cases: empty window titles, non-existent windows, permission-denied scenarios, concurrent access.
- Use `@pytest.mark.parametrize` (already used by 24 files — good pattern to follow).

---

### SIGN-003: Mixed Test Styles (pytest + unittest.TestCase)
**Severity:** 🟡 Suggestion  
**Files affected:** ~30 files use `unittest.TestCase` (e.g., `test_action_gate.py`, `test_screen_vision_permission.py`, etc.)

Some files use `unittest.TestCase` with `self.assertEqual()`, others use bare `assert` with pytest. This creates inconsistency in:
- Fixture usage (`setUp()` vs `@pytest.fixture`)
- Assertion error messages (unittest has better defaults)
- Test discovery and reporting

**Recommendation:**
- Adopt a project-wide standard. Prefer pytest-style (bare `assert`, fixtures, parametrize) for new tests.
- Consider a migration plan for existing unittest-style tests if the team has capacity.

---

### SIGN-004: No Performance or Load Tests
**Severity:** 🟡 Suggestion  
**Files affected:** N/A

No tests measure:
- ASR/TTS latency
- Wake pipeline audio processing time
- Memory store query performance
- Model router inference time
- Concurrent session handling

**Impact:** Performance regressions can ship undetected. Memory leaks or audio processing bottlenecks will only be caught in production.

**Recommendation:**
- Add `pytest-benchmark` for critical paths:
  - Wake pipeline: 50 iterations of `process_audio_chunk()` with synthetic audio
  - Memory store: query with 100, 1000, 10000 embeddings
  - Model router: sequential 10-intent resolution
- Set baseline thresholds that fail if exceeded.

---

### SIGN-005: No `pytest.mark` Markers Registered
**Severity:** 🟡 Suggestion  
**Files affected:** Project-wide

Only 1 file uses `@pytest.mark.skip`. No `slow`, `integration`, `smoke`, `flaky`, `asyncio`, or custom markers are used anywhere.

**Impact:** Impossible to run targeted subsets: `pytest -m smoke` or `pytest -m "not slow"`. All 375 files run every time.

**Recommendation:**
- Add marker taxonomy to `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  markers = [
    "smoke: quick sanity checks for pre-commit",
    "integration: tests that cross component boundaries",
    "slow: tests that take >5s",
    "flaky: known-flaky tests that need reruns",
    "wake: wake/hotword pipeline tests",
    "voice: ASR/TTS pipeline tests",
  ]
  ```

---

## 💭 Nits / Nice-to-Have

### NIT-001: Subprocess import in conftest could conflict
**File:** `tests/conftest.py`  
The conftest imports `subprocess` then patches it. A test importing `subprocess` later will get the monkey-patched version, which silently skips kill commands. This is safe for CI but could mask bugs during development.

**Suggestion:** Add a comment or env-var guard so the patches only apply in CI/`PYTEST_RUNNING=1`.

### NIT-002: 375 flat files means high discovery cost
**Suggestion:** Beyond subdirectory grouping, consider `tests/unit/__init__.py` that re-exports key fixtures for discoverability.

### NIT-003: No `conftest.py` in subdirectories
**Suggestion:** If you create subdirectories later, place module-specific fixtures in sub-`conftest.py` files rather than bloating the root conftest.

### NIT-004: Some test names are very long (`test_clap_backend_no_training_required`)
**Suggestion:** No issue with descriptive names — keep this pattern. But ensure all test names start with `test_` (all do ✓).

---

## Coverage Breadth Map

| Subsystem | Files | Quality |
|-----------|-------|---------|
| **Wake/Hotword/Clap** | ~15 | ✅ Good — `test_audio_wake_pipeline.py` and `test_dsp_clap_backend.py` are excellent |
| **ASR/TTS/Voice** | ~20 | ✅ Good — Groq ASR, TTS pipeline, barge-in, silence trims well-covered |
| **Intent Routing** | ~25 | ✅ Good — parametrized regression tests, router v2, hybrid router |
| **Command Bus** | ~10 | ✅ Good — command bridge, dispatch, MCP tool bridge |
| **UI State** | ~5 | ⚠️ Moderate — contract test exists but no full UI rendering tests |
| **Forge/Agent** | ~10 | ✅ Good — `test_forge_engine.py` and `test_agent_runtime.py` are well-structured |
| **Memory** | ~15 | ⚠️ Moderate — `test_memory_store.py` is solid, `test_autonomous_memory.py` is thorough |
| **Safety/Action Gate** | ~10 | ✅ Good — safety scan, hallucination guard, secret redaction, screen trust, permission manager |
| **Vision** | ~5 | ⚠️ Moderate — screen capture with mock Gemini |
| **Brain/Cognitive** | ~10 | ⚠️ Moderate — provider priority, cognitive prompts exist |
| **Studio Supervisor** | 1 | ✅ Excellent — 1101 lines, 45 tests, 263 assertions, fixtures, parametrize |
| **Model Router** | ~5 | ✅ Good — comprehensive parametrized tests |
| **Infrastructure/Config** | ~10 | ⚠️ Minimal — import smoke tests, diagnostics |
| **Training** | ~5 | ❌ Unknown — training-related files not reviewed |

---

## What's Good

1. **Safety-first conftest** — globally patches pyautogui/keyboard/subprocess kill commands so no test can escape. Brilliant defensive design.
2. **Rich fixtures usage** — 47 files use `@pytest.fixture`, demonstrating mature test patterns.
3. **Parametrized tests** — 24 files use `@pytest.mark.parametrize` for combinatorial coverage, especially in intent routing and secret redaction.
4. **`test_studio_supervisor.py`** — A gold-standard test at 1101 lines with 263 assertions covering the full studio governance lifecycle.
5. **`test_forge_engine.py`** — Well-structured E2E forge loop tests with FakeGenerator, parametrized task types.
6. **`test_secret_redaction.py`** — Simple, elegant parametrized test for a critical security feature.
7. **Zero zero-assertion files** — Every test file has real assertions (either `assert` or `self.assert*`).
8. **Great coverage diversity** — Wake pipeline, vision pipeline, voice state machine, intent router, forge engine, agent runtime, memory store, safety, studio, model router, MCP bridge, Eel contract — all tested at the unit level.

---

## Recommended Action Items (Priority Order)

### P0 — Before First CI Run
1. **Create `pyproject.toml`** with pytest config (testpaths, markers, asyncio-mode).
2. **Add `.github/workflows/test.yml`** to run tests on push/PR.
3. **Verify all tests pass** in a clean environment.

### P1 — Structural
4. **Organize into subdirectories** (`tests/unit/{wake,voice,intent,bridge,...}`, `tests/integration/`).
5. **Add shared fixtures** to `conftest.py` for the most common mock patterns.
6. **Tag tests with markers** (`smoke`, `integration`, `slow`, `wake`, `voice`, etc.).

### P2 — Gaps
7. **Add integration tests** for the full wake→command→TTS→sleep cycle.
8. **Add performance benchmarks** for critical paths (wake processing, ASR, memory query).
9. **Flesh out skeletal tests** (`test_desktop_control.py`, `test_chrome_control.py`, etc.).

### P3 — Polish
10. **Add `pytest-cov`** and set a coverage floor (80%+).
11. **Consider pytest-only standard** (migrate from unittest.TestCase over time).
12. **Add `pytest-timeout`** to prevent hung tests.

---

## Appendix: Test File Size Distribution

| Size Range | Count | Examples |
|-----------|-------|---------|
| >500 lines | ~15 | `test_studio_supervisor.py` (1101), `test_audio_wake_pipeline.py` (573) |
| 200–500 lines | ~60 | `test_action_gate.py` (361), `test_agent_runtime.py` (302) |
| 100–199 lines | ~120 | Most subsystem tests |
| 50–99 lines | ~130 | `test_chrome_control.py` (74), `test_window_control.py` (63) |
| <50 lines | ~50 | `test_voice_first_smooth.py` (46), various smoke tests |

---

*Report generated by Code Reviewer Agent. All findings based on static analysis of test file structure, patterns, and content.*
