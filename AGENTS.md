# AGENTS.md

## Repo Facts

- JARVIS is a Windows-only Python desktop voice assistant: Eel web UI in `www/`, Edge app window, voice/hotword/control backends in Python. Do not treat it as a web app or container service.
- This is not a git repo in this workspace; do not rely on git status/diff or create commits unless the user first initializes/provides git context.
- There is no root README, package manifest, pytest config, or CI workflow. Prefer executable sources: `run.py`, `main.py`, `requirements.txt`, `.env.example`, `scripts/`, `tests/`, and `.opencode/skills/`.
- Many root `*_REPORT.md`, `DEEPSEEK_PHASE_*.md`, `run_*.txt`, `runtime_*.txt`, and `phase*.patch` files are old artifacts/logs. Use code/config/tests as source of truth.

## Setup And Commands

- Use the repo root as cwd for every command; imports assume the root is on `sys.path`.
- Local interpreter is `.venv\Scripts\python.exe` (verified Python 3.12.9). Commands below use it explicitly.
- Runtime env is loaded with `load_dotenv()` from `.env`; copy from `.env.example` when running locally. Never read, print, or cache `.env` values.
- Install/check deps: `.venv\Scripts\python.exe -m pip install -r requirements.txt`.
- Full app: `.venv\Scripts\python.exe run.py` starts the UI process, wake listener, and schedule/alarm watchers.
- UI/assistant only: `.venv\Scripts\python.exe main.py` starts Eel and opens Edge at `http://localhost:8000/index.html`.
- Object detection only: `.venv\Scripts\python.exe app.py`; this needs `torch`/YOLOv5 and `cv2`, which are not covered by `requirements.txt`.

## Verification

- Focused test: `.venv\Scripts\python.exe -m pytest tests/test_<module>.py -v`.
- Full suite: `.venv\Scripts\python.exe -m pytest tests/ -v`.
- Syntax gate for backend edits: `.venv\Scripts\python.exe -m compileall src engine`.
- Control/safety edits: `.venv\Scripts\python.exe scripts/verify_safety.py`.
- Dependency/control-layer edits: `.venv\Scripts\python.exe scripts/verify_dependencies.py`.
- Browser/control/Eel bridge edits: `.venv\Scripts\python.exe scripts/playwright_runtime_check.py`.
- Detailed module-to-test hints live in `.opencode/skills/jarvis-test-runner/SKILL.md`.

## Architecture Constraints

- `src/` and `engine/` are PEP 420 namespace packages; there is intentionally no `src/__init__.py`. Keep imports rooted at repo root, e.g. `from engine...` and `from engine...`.
- `engine/` is the legacy runtime. `engine/command.py::allCommands` is the Eel-exposed entry for mic/text commands. Treat it as sensitive and preserve `except ImportError:` fallbacks.
- Current `allCommands` routing order matters: command-bus reentry guard -> stop/emergency/wake/sleep/cognitive/clarification/workflow/memory/output/tool/local-skill/repeat handlers -> `Phase3CommandBridge.try_handle()` -> `route_intent()` -> greeting/identity/brain or `dispatch_intent()` -> `chatBot()` fallback.
- `engine/` contains newer subsystems: `brain/`, `control/`, `memory/`, `vision/`, `voice/`, `diagnostics/`. The bridge into legacy flow is `engine/app/phase3_command_bridge.py`.
- `engine/features.py` opens `jarvis.db` at import and owns app/contact lookup plus `chatBot()`. Do not delete or replace `jarvis.db`; it is ignored but runtime-critical.

## Env, Models, And Secrets

- `.env`, `engine/cookies.json`, `config/providers.local.json`, and `data/memory/*.json*` are ignored local state/secrets. Do not read or expose them unless the user explicitly asks and it is necessary.
- `engine.features.chatBot()` defaults to Gemini via `GEMINI_API_KEY` or `GOOGLE_API_KEY`. HugChat and Lightning are legacy opt-in providers gated by `JARVIS_ENABLE_LEGACY_BRAIN_PROVIDERS=true`; HugChat uses ignored `engine/cookies.json`.
- `engine/brain/provider_registry.py` has separate defaults for DeepSeek/GLM/Qwen/Kimi/MiniMax and can load `config/providers.local.json`, but that file is not auto-wired into `engine.features.chatBot()` startup.
- Wake pipeline is selected by `VOICE_WAKE_BACKEND` (`openwakeword` in `.env.example`). If `DISABLE_LEGACY_HOTWORD_FALLBACK=true`, failed openWakeWord startup stays fatal instead of falling back to SpeechRecognition.

## UI And Safety Boundaries

- Do not make visual UI changes unless explicitly requested. Avoid `www/index.html` and `www/style.css`; edit JS only for minimal Python/Eel bridge fixes.
- Eel JS bridge functions are mainly in `www/controller.js` and command submission is in `www/main.js`; keep Python `safe_eel_call()` names synchronized with exposed JS names.
- Runtime PC-control actions are guarded by `engine/control/safety.py` (`EmergencyStop`, `SandboxPolicy`). Never bypass these guards for deletes, installs, settings changes, or other critical actions.
- Keep changes small and verified. For task-specific rules, prefer the relevant repo skill under `.opencode/skills/`, especially `jarvis-safe-coding`, `jarvis-test-runner`, and feature-specific Jarvis skills.

## OpenCode Config

- `.opencode/opencode.json` loads `.opencode/plugins/graphify.js` and all MCPs (ruflo, ruv-swarm, headroom, context-optimizer, filesystem, sequential-thinking, memory, time, git, sqlite, playwright, puppeteer). All MCPs have `autoStart: true`.
- `.mcp.json` defines all MCPs in Claude Code format. All now have `autoStart: true`. `graphify-out/` is absent now; if `graphify-out/graph.json` appears, use `graphify query "<question>"`, `graphify path`, or `graphify explain` before broad greps.

<!-- ANCHORED_SUMMARY -->
## Goal
- Fix Jarvis end-to-end wake→listen→ASR→command→TTS→sleep flow with old legacy UI (www/), VAD timing, session lifecycle, clean canonical state propagation, and Groq connection.

## Constraints & Preferences
- No Win+J, no keyboard bridge, no browser focus dependency, no Tzur default, no Groq/Gemini/cloud before wake.
- CLAP_NN missing must not block runtime; if YAMNET missing, DSP clap must work.
- Python is source of truth for UI state; do not fake PASS.
- Old legacy UI (www/) must visibly update — NOT Mark UI (www_mark/).
- VAD must not reject valid recordings with short speech_ms (<250ms) if total recording ≥ 1200ms and speech_started=true.
- Session must finish and detectors resume on: ASR empty, no-speech timeout, command error, exception, TTS complete.
- Defaults: POST_WAKE_DELAY_MS=800, NO_SPEECH_TIMEOUT_MS=15000, END_SILENCE_MS=1800, VAD_MIN_SPEECH_MS=400, ASR_MIN_AUDIO_MS=1200, MAX_RECORD_SECONDS=25.
- Hotword threshold=0.25, consecutive_hits=1, min_rms=0.003, rising_delta=0.02, cooldown_ms=1500, phrases=hey jarvis,jarvis.
- Clap: primary=dsp_clap, order=dsp_clap,clap_nn, max_gap_ms=4500 (minimum), min_gap_ms=100, cooldown_ms=1500.
- Canonical UI order: SLEEPING → ONLINE → LISTENING → RECOGNISING → THINKING → SAYING → SLEEPING.
- `wake_detected` maps to ONLINE; `speech_started` maps to RECOGNISING (not LISTENING).
- Session lock pauses wake detection at pipeline level.
- Only one active wake session at a time; all bridge events carry `session_id`.
- Auto-followup disabled by default; 60s session timeout for emergency recovery.

## Progress
### Done
- **Old UI Wake Repair (Phases 0-8 completed)**:
  - **Phase 0**: Backed up to `E:\jarvis-main-backup-old-ui-wake-repair-20260620_124111`.
  - **Phase 1 - VAD fix** (`audio_wake_pipeline.py`): `_check_vad_gates()` now tolerates valid recordings — if `speech_started=true` AND `duration_ms >= ASR_MIN_AUDIO_MS` (1200ms), ASR proceeds even if `speech_ms < VAD_MIN_SPEECH_MS`. Fixes the root live bug: `[VAD] gate fail reason=speech_too_short speech_ms=240 min_ms=700`.
  - **Phase 2 - Session finish on all exit paths** (`audio_wake_pipeline.py`): `trigger_wake()` now calls `finish_session()` on: `no_speech_timeout`, `asr_empty`, `emit_command_failed`, `capture_command_failed`. Session no longer leaks after silent commands.
  - **Phase 3 - Old UI DOM states** (`www/controller.js`): Added `online`, `recognising`, `saying`, `waiting_for_speech` to `ALLOWED_STATES` and `STATE_LABELS`. Waveform bars activate for `online`, `listening`, `recognising`, `transcribing`. Speech capsule shown for `saying`.
  - **Phase 4 - CSS** (`www/style.css`): Added `.jarvis-state-online`, `.jarvis-state-recognising`, `.jarvis-state-saying` orb glow/pulse rules. Added status label colors.
  - **Phase 5 - Defaults updated**: POST_WAKE_DELAY_MS 500→800, VAD_SILENCE_END_MS 900→1800, VAD_MIN_SPEECH_MS 700→400, ASR_MIN_AUDIO_MS 1000→1200, ASR_MAX_RECORD_SECONDS 6.0→25.0, SESSION_TIMEOUT 180s→60s, NO_SPEECH_TIMEOUT_SECONDS=15s.
  - **Phase 6 - Tests**: **54/54 focused tests PASS** (session manager, pipeline, lock integration, Groq TTS).
  - **Final report**: `JARVIS_OLD_UI_WAKE_GROQ_FINAL_REPORT.md`.

### In Progress
- None currently.

### Blocked
- **DSP clap calibration**: Default thresholds (`rms=0.045`, `peak=0.14`, `peak_ratio=5.2`, `hf_ratio=0.43`) may need per-environment tuning.
- **Energy VAD sensitivity**: `VAD_MIN_RMS=0.015` may be too high for quiet microphones.
- **Live `python run.py` validation**: Requires physical mic/double-clap to confirm end-to-end flow.

## Key Decisions
- VAD tolerant gate: `speech_started && duration_ms >= ASR_MIN_AUDIO_MS` bypasses `speech_ms < VAD_MIN_SPEECH_MS` rejection.
- Session finish is triggered both in `trigger_wake()` (on errors/timeouts) and in `runtime_bridge` (on TTS complete).
- Old UI can use existing DOM elements (`#StatusLabel`, `#JarvisHood`, `#WaveformBars`, `#SourceBadge`, `#TranscriptPreview`) without redesign.
- Only canonical backend states are sent to old UI; mapping done server-side in `ui_state_manager.py`.
- DSP clap is primary (no tzur, no YAMNET dependency).
- Session timeout reduced to 60s for faster recovery.

## Next Steps
1. Live validation: `python run.py` with `$env:JARVIS_UI_MODE="legacy"`.
2. Tune `dsp_clap` thresholds per environment if double clap is not detected.
3. Tune `VAD_MIN_RMS` if commands are being cut off.

## Critical Context
- Old UI loads from `www/`, not `www_mark/`. All state DOM updates go through `eel.updateJarvisState()`.
- Default `.env` values are now `OPENWAKEWORD_SCORE_THRESHOLD=0.25`, `OPENWAKEWORD_CONSECUTIVE_HITS=1`, `JARVIS_CLAP_PRIMARY=dsp_clap`, `JARVIS_CLAP_BACKEND_ORDER=dsp_clap,clap_nn`.
- VAD `speech_too_short` bug was the root cause of ASR empty audio — now fixed with tolerant gate.
- Session finish call sites: `audio_wake_pipeline.trigger_wake()` (4 paths) + `runtime_bridge.handle_bridge_event()` (TTS complete).
- Clap backend manager uses dsp_clap by default; no tzur or YAMNET dependency required.
- **DoubleClapDetector** (`engine/dsp_clap_backend.py`) is the single source of truth for double-clap timing. Env overrides: `JARVIS_CLAP_MIN_GAP_MS` (default 100), `JARVIS_CLAP_MAX_GAP_MS` (default 3500, clamped to >=4500). The constructor sets `_max_gap_ms = max(4500, configured_value)`. After a too_late/too_soon reset, the _next_ clap becomes a new first; the clap that caused the reset does NOT become a first.
- **Critical: `check_timeout` must NOT be called in `process_audio_chunk`** or `_apply_double_clap_state` — `DoubleClapDetector.detect()` handles gap validation internally. Premature `check_timeout` causes the second clap to be treated as a new first clap instead of being checked against the gap window.
- Settings env vars are read at import/constructor time. Overriding `_min_gap_ms`/`_max_gap_ms` on the manager after construction works because `_init_double_clap()` reads the current values when lazily creating the detector.

## Relevant Files
- `engine/audio_wake_pipeline.py`: VAD gate fix, session finish on all exit paths, no-speech timeout, updated defaults.
- `engine/wake_session_manager.py`: 60s auto-timeout.
- `www/controller.js`: ALLOWED_STATES + STATE_LABELS with online/recognising/saying.
- `www/style.css`: CSS for online/recognising/saying orb states and label colors.
- `engine/runtime_bridge.py`: finish_session on TTS complete (unchanged from prior).
- `engine/clap_backend_manager.py`: DSP clap primary, DoubleClapDetector integration, check_timeout removed from process_audio_chunk (2026-06-20 fix).
- `engine/dsp_clap_backend.py`: DoubleClapDetector — single source of truth for double-clap timing. detect() handles gap validation internally.
- `JARVIS_OLD_UI_WAKE_GROQ_FINAL_REPORT.md`: Full report.

---

## Master Skill / MCP / Plugin / Tool Architecture

### Skill Fitness Rules
- **Find Skill (`find-skills`) MUST be invoked at the start of every prompt** before any other action. Use `skill` tool with `name: "find-skills"` to discover relevant skills for the task.
- All skills are verified by fitness audit: valid frontmatter (name, description), clear purpose, actionable workflow, no duplicates.
- Skills may be removed, merged, or created as needed using `skill-create-skill` skill.
- New skills can be installed from web: `npx skills add <repo> --agent claude-code --yes --all`
- Web fetch and search can be used to discover new skills, MCPs, and plugins.

### Installed Skill Inventory (Global - C:\Users\marke\.config\opencode\skills)

| Skill | Description | Verdict |
|-------|-------------|---------|
| `accessibility` | WCAG 2.2 compliance audit | keep |
| `agent-orchestration` | Multi-agent coordination | keep |
| `ai-repo-maintainer` | AI-ready repo setup | keep |
| `ai-workflow-design` | AI pipeline design | keep |
| `api-design-review` | REST/GraphQL API review | keep |
| `api-security-hardening` | API security hardening | keep |
| `auth-rbac-review` | Auth/RBAC review | keep |
| `autoplan` | Full review pipeline (gstack) | keep |
| `backend-architecture-review` | Backend structure review | keep |
| `benchmark` | Performance regression detection (gstack) | keep |
| `benchmark-models` | Cross-model LLM benchmarks (gstack) | keep |
| `browse` | Headless browser QA (gstack) | keep |
| `browser-automation-planning` | Playwright/Puppeteer planning | keep |
| `bug-reproduction-skill` | Bug repro and root cause | keep |
| `canary` | Post-deploy monitoring (gstack) | keep |
| `careful` | Safety guardrails (gstack) | keep |
| `ci-cd-pipeline-review` | CI/CD config review | keep |
| `claude` | Claude Code wrapper (gstack) | keep |
| `component-design` | Production UI components | keep |
| `context-restore` | Resume saved context (gstack) | keep |
| `context-save` | Save working context (gstack) | keep |
| `cso` | Security audit (gstack) | keep |
| `customize-opencode` | OpenCode config editing | keep |
| `dashboard-ux-design` | Dashboard layout design | keep |
| `database-review` | Schema/query review | keep |
| `dependency-risk-review` | Third-party dep evaluation | keep |
| `design-consultation` | Design system creation (gstack) | keep |
| `design-html` | Production HTML generation (gstack) | keep |
| `design-review` | Visual QA and fix (gstack) | keep |
| `design-shotgun` | AI design variant exploration (gstack) | keep |
| `design-system` | Tailwind design tokens | keep |
| `devex-review` | Developer experience audit (gstack) | keep |
| `docker-containerization` | Docker/docker-compose | keep |
| `docker-devops-review` | Docker CI/CD review | keep |
| `document-generate` | Documentation generation (gstack) | keep |
| `document-release` | Post-ship docs update (gstack) | keep |
| `documentation-writing` | README/API docs | keep |
| `express-api-hardening` | Express.js security | keep |
| `fastify` | Fastify web framework | keep |
| `find-skills` | Discover and install skills | keep |
| `form-ux-optimization` | Form design/validation | keep |
| `freeze` | Directory-scoped edits (gstack) | keep |
| `frontend-architecture-review` | Frontend structure review | keep |
| `frontend-performance-optimization` | CWV optimization | keep |
| `git-safety` | Safe git operations | keep |
| `graphql-api-design` | GraphQL schema review | keep |
| `gstack` | Fast headless browser (gstack) | keep |
| `gstack-upgrade` | Upgrade gstack (gstack) | keep |
| `guard` | Full safety mode (gstack) | keep |
| `health` | Code quality dashboard (gstack) | keep |
| `investigate` | Systematic debugging (gstack) | keep |
| `ios-clean` | iOS debug bridge cleanup (gstack) | keep |
| `ios-design-review` | iOS visual design audit (gstack) | keep |
| `ios-fix` | Autonomous iOS bug fix (gstack) | keep |
| `ios-qa` | Live-device iOS QA (gstack) | keep |
| `ios-sync` | iOS debug bridge regen (gstack) | keep |
| `jest-vitest-testing` | Unit/integration tests | keep |
| `land-and-deploy` | Merge/deploy workflow (gstack) | keep |
| `landing-page-ux` | CRO-optimized landing pages | keep |
| `landing-report` | Queue dashboard (gstack) | keep |
| `learn` | Project learnings manager (gstack) | keep |
| `make-pdf` | Markdown to PDF (gstack) | keep |
| `mcp-architecture` | MCP server config management | keep |
| `nextjs-app-router-engineering` | Next.js App Router | keep |
| `nextjs-performance` | Next.js optimization | keep |
| `nginx-proxy-engineering` | Nginx reverse proxy | keep |
| `nodejs-api-engineering` | Node.js API routes | keep |
| `nodejs-debugging` | Node.js runtime errors | keep |
| `octogent-planning` | Octogent tentacle creation | keep |
| `office-hours` | YC Office Hours (gstack) | keep |
| `open-gstack-browser` | Launch GStack Browser (gstack) | keep |
| `openapi-spec-writer` | OpenAPI spec creation | keep |
| `opencode-repair` | OpenCode crash repair | keep |
| `opencode-workspace-safety` | Framework file boundary | keep |
| `pair-agent` | Remote agent pairing (gstack) | keep |
| `plan-ceo-review` | CEO plan review (gstack) | keep |
| `plan-design-review` | Design plan review (gstack) | keep |
| `plan-devex-review` | DX plan review (gstack) | keep |
| `plan-eng-review` | Engineering plan review (gstack) | keep |
| `plan-tune` | Self-tuning questions (gstack) | keep |
| `playwright-e2e-testing` | E2E test creation | keep |
| `postgres-engineering` | PostgreSQL schema/index | keep |
| `prompt-engineering` | AI prompt design | keep |
| `qa` | QA test + fix loop (gstack) | keep |
| `qa-only` | Report-only QA (gstack) | keep |
| `react-component-engineering` | React component best practices | keep |
| `release-readiness` | Release checklist | keep |
| `repo-analysis` | Repo structure analysis | keep |
| `responsive-design` | Multi-device CSS | keep |
| `retro` | Engineering retro (gstack) | keep |
| `review` | Pre-landing PR review (gstack) | keep |
| `ruflo-planning` | Ruflo swarm plan design | keep |
| `safe-refactoring` | Behavior-preserving refactor | keep |
| `scrape` | Web data extraction (gstack) | keep |
| `secrets-audit` | Secret scanning | keep |
| `security-review` | Vulnerability review | keep |
| `serverless` | AWS serverless | keep |
| `setup-browser-cookies` | Cookie import (gstack) | keep |
| `setup-deploy` | Deploy configuration (gstack) | keep |
| `setup-gbrain` | gbrain setup (gstack) | keep |
| `shadcn-ui` | shadcn/ui components | keep |
| `ship` | Ship workflow (gstack) | keep |
| `skill-creator` | Create/edit skills | keep |
| `skillify` | Codify scrape flows (gstack) | keep |
| `spec` | Vague-to-spec workflow (gstack) | keep |
| `sql-query-optimization` | SQL performance | keep |
| `sync-gbrain` | gbrain sync (gstack) | keep |
| `tailwind-css-expert` | Tailwind CSS best practices | keep |
| `test-strategy` | Test planning/coverage | keep |
| `typescript-debugging` | TS type errors | keep |
| `ui-polish` | UI/UX design intelligence | keep |
| `ui-ux-audit` | UI screen audit | keep |
| `unfreeze` | Clear edit freeze (gstack) | keep |
| `windows-debugging` | Windows-specific issues | keep |

### Installed Skill Inventory (Project - E:\jarvis-main\.opencode\skills)

| Skill | Description | Verdict |
|-------|-------------|---------|
| `algorithmic-art` | Canvas/SVG/CSS generative art | keep |
| `browser-agent` | Playwright browser automation | **merge** into jarvis-playwright-qa |
| `claude-flow-orchestration` | Ruflo swarm planning | keep |
| `claude-task-master` | Task decomposition/planning | keep |
| `deep-research` | Multi-source research | keep |
| `doctorg-deep-learning` | DL code review | keep |
| `ecc-superpower` | Execution checklist clarity | keep |
| `firecrawl-research` | Web crawl research | **merge** into deep-research |
| `frontend-design` | Eel/React UI improvements | keep |
| `humanizer` | AI text → natural writing | keep |
| `jarvis-actiongate` | Jarvis action safety | keep |
| `jarvis-architecture` | Jarvis architecture rules | keep |
| `jarvis-autonomous-wake-debug` | Wake/hotword debugging | keep |
| `jarvis-chrome-control` | Chrome automation | keep |
| `jarvis-class-ui` | Premium UI patch rules | keep |
| `jarvis-command-bridge` | Command bus safety | keep |
| `jarvis-deep-training-system` | Training system | keep |
| `jarvis-demo-critical-fix` | Demo mode fixes | keep |
| `jarvis-final-interview-fix` | Final interview fix | keep |
| `jarvis-gesture-eye-control` | Gesture/eye mouse | keep |
| `jarvis-git-checkpoint` | Git checkpointing | keep |
| `jarvis-gstack-review.skill.md` | GStack review (flat file) | keep |
| `jarvis-hotword-debug.skill.md` | Hotword debugging (flat) | keep |
| `jarvis-intelligent-product-features` | Intent routing/tools | keep |
| `jarvis-interview-wake-ui-groq-fix` | Wake UI fix | keep |
| `jarvis-live-test-checklist` | Live validation checklist | keep |
| `jarvis-local-skills` | Local skill routing | keep |
| `jarvis-mark-ui-product-upgrade` | Mark UI upgrade | keep |
| `jarvis-memory-engineer` | Memory engineering | keep |
| `jarvis-memory-growth` | Adaptive memory | keep |
| `jarvis-memory-system` | Short/long-term memory | keep |
| `jarvis-model-prompts` | Model prompt files | keep |
| `jarvis-model-router` | Model routing | keep |
| `jarvis-need-based-training` | Need-based training | keep |
| `jarvis-output-workspace` | Output workspace routing | keep |
| `jarvis-pass-only-wake-ui-debug` | PASS-gated wake debug | keep |
| `jarvis-pc-control` | PC control | keep |
| `jarvis-phase4-roadmap` | Phase 4 roadmap | keep |
| `jarvis-playwright-qa` | Playwright QA | keep |
| `jarvis-prompt-builder` | Prompt building | keep |
| `jarvis-realtime-cognitive-training` | Cognitive training | keep |
| `jarvis-repo-navigator` | Repo navigation | keep |
| `jarvis-reviewer` | Code review | keep |
| `jarvis-runtime-debug.skill.md` | Runtime debug (flat) | keep |
| `jarvis-runtime-doctor` | Runtime diagnostics | keep |
| `jarvis-safe-coding` | Safe coding rules | keep |
| `jarvis-safety-gate` | Safety gate rules | keep |
| `jarvis-screen-trust` | Screen trust | keep |
| `jarvis-screen-vision` | Screen vision | keep |
| `jarvis-security-review.skill.md` | Security review (flat) | keep |
| `jarvis-speech-overlay` | Speech capsule | keep |
| `jarvis-test-runner` | Test runner | keep |
| `jarvis-test-validation.skill.md` | Test validation (flat) | keep |
| `jarvis-token-efficient-debugging` | Low-token debugging | keep |
| `jarvis-tool-registry` | Tool registry | keep |
| `jarvis-tts-debug.skill.md` | TTS debug (flat) | keep |
| `jarvis-ui-debug` | UI debugging | keep |
| `jarvis-ui-fui` | UI without redesign | keep |
| `jarvis-ui-voice-first.skill.md` | Voice-first UI (flat) | keep |
| `jarvis-voice-bridge-runtime` | Voice bridge runtime | keep |
| `jarvis-voice-interrupt` | Voice interrupt | keep |
| `jarvis-wake-system-perfect` | Wake system fixes | keep |
| `jarvis-workflow-dialogue` | Workflow dialogue | keep |
| `karpathy-debugging` | Behavioral debugging | **remove** (no frontmatter, dup) |
| `karpathy-guidelines` | LLM coding guidelines | keep |
| `mcp-builder` | MCP server building | keep |
| `model-agnostic-cli-system` | OpenCode CLI workflow | keep |
| `repo-mix` | Multi-repo analysis | keep |
| `skill-codex` | Skill catalog/index | keep |
| `skill-create-skill` | Skill creation | keep |
| `trail-of-bits-audit` | Agent tool security audit | keep |
| `web-design-guidelines` | UI/UX design guidelines | keep |

### Web-Installed Skills (Claude Code - ~\.claude\skills and ~\.agents\skills)

| Skill | Source | Description |
|-------|--------|-------------|
| `emil-design-eng` | emilkowalski/skill | Emil Kowalski's design engineering philosophy — animation, motion, micro-interactions |
| `review-animations` | emilkowalski/skill | Animation review skill |
| `impeccable` | pbakaus/impeccable | Production-grade UI design: 23 commands, 44 anti-pattern detectors, 7 domain references |
| `taste` | VOIDXAI/taste | 5-dimension engineering taste: code, architecture, product, design, communication |
| `agentic-harness-patterns` | Jayl1n/agentic-harness-patterns | Context engineering, memory patterns, multi-agent coordination |
| `agentic-harness-patterns-zh` | Jayl1n/agentic-harness-patterns | Chinese version of harness patterns |
| `gstack` (40+ sub-skills) | garrytan/gstack | Full engineering team: CEO, designer, eng manager, QA, security, docs, deploy |
| `ui-ux-pro-max` | nextlevelbuilder/ui-ux-pro-max-skill | 50+ styles, 161 color palettes, 57 font pairs, 99 UX guidelines |
| `ckm-banner-design` | nextlevelbuilder/ui-ux-pro-max-skill | Banner design sub-skill |
| `ckm-brand` | nextlevelbuilder/ui-ux-pro-max-skill | Brand design sub-skill |
| `ckm-design` | nextlevelbuilder/ui-ux-pro-max-skill | General design sub-skill |
| `ckm-design-system` | nextlevelbuilder/ui-ux-pro-max-skill | Design system sub-skill |
| `ckm-slides` | nextlevelbuilder/ui-ux-pro-max-skill | Slides design sub-skill |
| `ckm-ui-styling` | nextlevelbuilder/ui-ux-pro-max-skill | UI styling sub-skill |
| `gpt55-master-execution` | project | GPT-5.5 master execution workflow |
| `model-agnostic-cli-workflow` | project | Model-agnostic CLI workflow |
| `graphify` | .claude/skills | Knowledge graph from any input |
| `find-skills` | .claude/skills | **MUST use in EVERY prompt — skill discovery** |
| `remotion-best-practices` | .claude/skills | Remotion video creation best practices |
| `skill-creator` | .claude/skills | Create/edit skills |
| `design-motion-principles` | kylezantos/design-motion-principles | Motion design from Emil Kowalski, Jakub Krehel, Jhey Tompkins |

### Skill Usage Protocol (Every Prompt)
1. **ALWAYS** invoke `find-skills` first to check if relevant skills exist for the task
2. Load relevant skill(s) via `skill` tool
3. Execute task using skill guidance
4. If a new skill is needed, use `skill-create-skill` or `npx skills add <repo>`
5. If a skill is unfit, flag for removal

### Claude Code Plugins (Enabled in ~\.claude\settings.json)
- frontend-design, superpowers, context7, code-review
- code-simplifier, skill-creator, github, playwright
- claude-md-management, feature-dev, typescript-lsp
- ralph-loop, security-guidance, claude-code-setup
- pyright-lsp, chrome-devtools-mcp, agent-sdk-dev
- plugin-dev, playground, greptile, learning-output-style
- csharp-lsp, remember, huggingface-skills, mcp-server-dev

### MCP Server Inventory

| MCP | Status | Notes |
|-----|--------|-------|
| **ruflo** | Auto-start | 313+ MCP tools: memory, swarm, hooks, agents (v3.12.4 via pnpm) |
| **ruv-swarm** | Auto-start | Swarm coordination via WASM |
| **headroom** | Auto-start | Context compression (40-90% token reduction) via headroom mcp |
| **context-optimizer** | Auto-start | Token tracking, heatmaps, ROI reports via claude-context-optimizer |
| **filesystem** | Enabled | Read-write to E:/jarvis-main |
| **sequential-thinking** | Enabled | Structured thinking |
| **memory** | Enabled | Knowledge graph |
| **time** | Enabled | Timezone conversion |
| **git** | Enabled | Git operations |
| **sqlite** | Enabled | Local database |
| **playwright** | Enabled | Browser automation |
| **puppeteer** | Enabled | Browser automation |

### Recommended Future MCP Servers
- `@21st-dev/mcp` → 21st.dev Magic MCP for UI component generation (already installed as CLI)
- `@modelcontextprotocol/server-brave-search` → Web search via Brave API
- `@modelcontextprotocol/server-github` → GitHub API integration
- `@modelcontextprotocol/server-postgres` → PostgreSQL database access
- `@modelcontextprotocol/server-ollama` → Local LLM inference (if Ollama running)

### Tool Compatibility with Windows cmd/PowerShell

| Tool | Compatible | Install Method | Status |
|------|-----------|---------------|--------|
| **Ruflo** (v3.12.4) | FULLY | `pnpm ruflo mcp start` through cmd | INSTALLED & WORKING |
| **Octogent** | YES | `npm install -g octogent` (runs via `octogent.cmd`) | INSTALLED |
| **oh-my-pi (pi)** | MAYBE | `npm install -g @oh-my-pi/pi-cli` (package may be unavailable) | NOT INSTALLED |
| **headroom** (v0.20.15) | FULLY | `pip install headroom-ai` + `headroom mcp serve` | INSTALLED & WORKING |
| **claude-context-optimizer** | YES | `npx -y claude-context-optimizer mcp` | INSTALLED |
| **21st.dev** | YES | `npm install -g @21st-dev/cli` + API key configured | INSTALLED & CONFIGURED |

### Framer Motion / Motion for React
- **Current package**: `motion` (previously `framer-motion`) — installed globally as `npm install -g motion`
- **Install in project**: `npm install motion`
- **Import**: `import { motion } from "motion/react"`
- **For Cloudflare Workers**: Use `framer-motion` v12.23.24 instead
- **Available skills**: `design-motion-principles` (kylezantos), `emil-design-eng` (emilkowalski)

### 21st.dev Integration for UI/UX
- **CLI installed**: `npx @21st-dev/cli@latest install claude --api-key b1064f55...1d5`
- **Use**: Ask the agent to use 21st.dev Magic MCP for React+Tailwind component generation
- **Components**: React + Tailwind, MIT-licensed (free tier: 5/month, Pro: $20/mo for 50)
- **Skill available**: Use `impeccable` or `emil-design-eng` skill to guide 21st.dev output quality
