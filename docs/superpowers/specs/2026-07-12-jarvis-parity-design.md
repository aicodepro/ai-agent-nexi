# JARVIS-parity + CrewAI — NEXI hardening (2026-07-12)

## Context
Reference repos studied as *architecture/learning*, **not** copied:
- **Mark-XLVIII** (FatihMakes) — Gemini-Live PyQt6 JARVIS, 11 polish features.
- **Ada-SI** (nazirlouis) — FastAPI/React runtime tool-forging assistant (the demo video).

NEXI is larger/more mature than both. Guardrail: **no shadowing existing features; targeted parity, not a literal port** (`nexi-jarvis-no-shadow`, `nexi-is-the-jarvis-rebuild`).

Audit result — NEXI already has: instant interrupt, echo guard, language awareness (partial),
face recognition, real-news links (stub), session reset (partial). Genuine gaps below.

## Workstreams

### 0. Chrome-safety guard — DONE ✅
Both force-kill paths (`process_controller.kill_process`, `features.py` close-branch) now refuse to
force-kill browsers unless `NEXI_ALLOW_BROWSER_KILL=1`. Covered by `tests/test_browser_kill_guard.py`.

### 1. Zero terminal windows
One global wrapper (`engine/no_window.py`) that injects `CREATE_NO_WINDOW` into every
`subprocess.Popen` on Windows, installed once at app startup. Opt out: `NEXI_SHOW_TERMINALS=1`.
Not installed at import (tests unaffected). Mirrors Mark-48's subprocess-suppression approach.

### 2. Parallel news + real articles
Rewrite `engine/news.py` (currently a stub with placeholder keys + `input()` loop) into a
callable `get_news(topic, limit)` that races two sources in threads (first valid wins), returns real
article URLs, no interactive input, graceful fallback. Wire as the news tool if a stub is registered.

### 3. Vision acknowledgement + cooldown — DONE ✅
In the screen-observation path (`engine/app/phase3_command_bridge.py::_try_screen_observation`):
speak an immediate non-blocking ack ("Looking at your screen now") before the synchronous
capture/analyze. Cooldown (`NEXI_VISION_COOLDOWN_MS`) dedupes rapid captures but is **OFF by
default** (0) — NEXI already has an echo guard, and an always-on cooldown changed the trusted-read
return contract (broke 11 existing tests when consecutive reads fell inside the window). Opt-in.

### 4. Two-phase startup + session-state reset
- Startup: fetch status/news concurrently with the greeting instead of sequentially (`main.py`).
- One `reset_session()` aggregator that calls the existing per-module resets atomically on a new session.

### 5. CrewAI (= "clue.ai") — OPTIONAL backend — DONE ✅
`engine/agency/crewai_adapter.py` plugs into the engine via a generic `set_model_override` hook
(`workflow_engine.py` stays literally CrewAI-free — the de-brand invariant test still passes).
Active only when `crewai` is installed AND `NEXI_AGENCY_BACKEND=crewai`; otherwise the clean-room
engine is the default. No dependency forced, no shadowing, reversible. Registered at agency load
(`engine/agency/__init__.py`). Covered by `tests/test_crewai_adapter.py` (fake-crewai, no real install).

## Testing — all green
Each workstream ships runnable checks under `tests/`. Consolidated run: **54 passed**
(30 new + 15 agency + 9 desktop). Safety invariant preserved: tests never drive real
keyboard/mouse or `taskkill` (`tests/conftest.py`). Pre-existing env note: ~42 unrelated tests fail
in this environment because the `keyboard` package (a runtime dep) isn't installed here.
