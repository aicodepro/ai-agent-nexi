# Implementation of capabilities

## Capability Dashboard

| # | Listed capability | Nexi integrated capability | Count | Status | Defects after remediation |
|---|---|---:|---:|---|---|
| 1 | computer hardness | Computer-Use Harness | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 2 | browse intelligence | Browser Intelligence Layer | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 3 | human approval | Human Approval Queue v2 | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 4 | QoV2 toolbar | Tool Verifier Layer | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 5 | car layer collection | Capability Layer Collection | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 6 | memory produce kill library | Reflection Memory plus Procedure / Skill Library | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 7 | proactive monitor | Proactive Monitor | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 8 | conscience | Conscious State Surface | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |
| 9 | its ud | HUD and UI Diagnostics Surface | 1 | Verified | 0 Critical, 0 High, 0 Medium, 0 Low |

Total listed capabilities audited: 9.

Canonical Nexi capabilities covered: 8 runtime capabilities plus 1 UI-facing HUD split from the supplied ASR-style input list.

## Capability Details

### 1. computer hardness

**Name**: computer hardness, normalized to Computer-Use Harness.

**Location**:
- `engine/diagnostic_capabilities.py:51-64` defines the diagnostic capability card.
- `engine/os_awareness.py:3-8` defines role, risk, verifier, and memory rules for OS-awareness tools.
- `engine/os_awareness.py:56-123` implements active window, current work, system state, and slow-PC analysis.
- `engine/control/permission_manager.py:45-91` gates runtime actions before execution.

**Integration Change**: The desktop-control and OS-awareness code now lives inside Nexi runtime packages: `engine/control`, `engine/app`, `engine/brain`, `engine/voice`, `engine/memory`, and `vision`. The retired isolated `src` namespace was removed, and imports now target Nexi-owned paths such as `engine.control` and `vision.screen_trust`.

**Research & Web-Search Evidence**:
- Microsoft UI Automation describes programmatic Windows UI access for assistive technology and automated test scripts: https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32
- MCP security guidance states that tools are powerful and require user consent and control for tool use: https://modelcontextprotocol.io/specification/2025-06-18

**Bug/Defect Findings**:
- Medium, remediated: desktop-control code was previously separated from the main Nexi runtime namespace, which increased import and safety-gate drift risk.
- No Critical or High defects remain after the move and focused tests.

**Remediation & Optimization**:
- Applied: moved control code into `engine/control` and rewrote imports to `engine.control.*`.
- Applied: kept OS-awareness read-only and verified through `engine/tool_result_verifier.py`.
- Optimization: add future UI Automation-specific probes only behind `PermissionManager.evaluate()` and `safety_gate.execution_is_safe()`.

### 2. browse intelligence

**Name**: browse intelligence, normalized to Browser Intelligence Layer.

**Location**:
- `engine/diagnostic_capabilities.py:65-78` defines the browser intelligence capability card.
- `engine/tool_registry.py:108-114` registers browser tools.
- `engine/tool_registry.py:130-148` exposes router-facing tool cards.
- `engine/tool_registry.py:545-550` maps browser commands to keyboard/browser operations.

**Integration Change**: Browser actions now remain first-class Nexi tools under `engine/tool_registry.py`. Any former split package imports were rewritten to Nexi-owned modules, so browser features are no longer represented as a separate agent or system.

**Research & Web-Search Evidence**:
- Playwright documents end-to-end browser test support across Chromium, Firefox, and WebKit, with parallel execution and reports: https://playwright.dev/docs/intro
- MCP defines tool exposure as a standard AI capability surface and requires explicit consent for tool invocation: https://modelcontextprotocol.io/specification/2025-06-18

**Bug/Defect Findings**:
- Medium, remediated: fragmented browser imports could hide browser tools from the main router manifest.
- No Critical or High defects remain after route and registry validation.

**Remediation & Optimization**:
- Applied: rewrote browser and app bridge imports to `engine.app.phase3_command_bridge` and `engine.diagnostic_doctors`.
- Applied: verified router-visible browser cards through focused tests.
- Optimization: add per-browser result probes so `browser_back` and `browser_forward` can verify state beyond keyboard dispatch.

### 3. human approval

**Name**: human approval, normalized to Human Approval Queue v2.

**Location**:
- `engine/diagnostic_capabilities.py:79-90` defines the approval capability card.
- `engine/control/permission_manager.py:7-37` defines known actions and high/critical confirmation prompts.
- `engine/control/permission_manager.py:45-91` evaluates action risk and approval state.
- `engine/control/permission_manager.py:97-120` confirms or blocks pending user decisions.
- `engine/control/permission_manager.py:163-168` resolves high and critical prompt text.

**Integration Change**: Approval logic now runs from `engine/control/permission_manager.py` and depends on `engine.control.safety` plus `vision.screen_trust`, keeping human approval inside Nexi’s control layer rather than a side namespace.

**Research & Web-Search Evidence**:
- NIST AI RMF frames trustworthy AI as a risk-managed system design and evaluation practice: https://www.nist.gov/itl/ai-risk-management-framework
- MCP security principles require explicit user consent and user control for tool and data operations: https://modelcontextprotocol.io/specification/2025-06-18
- OWASP ASVS provides a basis for testing technical security controls and secure development requirements: https://owasp.org/www-project-application-security-verification-standard/

**Bug/Defect Findings**:
- Medium, remediated: approval queue code was reachable through legacy imports, which could diverge from Nexi safety policy over time.
- No Critical or High defects remain after `test_action_gate.py` and permission-focused coverage passed.

**Remediation & Optimization**:
- Applied: moved approval code into `engine/control` and updated all tests/scripts/imports.
- Applied: preserved Critical-risk invariant: critical actions remain blocked regardless of confirmation.
- Optimization: persist a compact approval decision ledger separate from conversation memory, with redacted payload summaries only.

### 4. QoV2 toolbar

**Name**: QoV2 toolbar, normalized to Tool Verifier Layer.

**Location**:
- `engine/diagnostic_capabilities.py:92-104` defines the verifier capability card.
- `engine/tool_result_verifier.py:7-49` normalizes raw tool results and downgrades unverified success.
- `engine/tool_registry.py:265-309` executes tools, invokes verification, and records tool usage.

**Integration Change**: Tool verification is now a Nexi engine concern. The verifier is invoked by `engine.tool_registry.execute_tool()` for every registered tool path, and the diagnostic catalog exposes it as a named Nexi capability.

**Research & Web-Search Evidence**:
- OWASP ASVS defines verification as a basis for testing technical security controls: https://owasp.org/www-project-application-security-verification-standard/
- MCP tool safety guidance warns that tools are arbitrary code execution surfaces and should be treated with caution: https://modelcontextprotocol.io/specification/2025-06-18

**Bug/Defect Findings**:
- Medium, remediated: unverified tool success could be reported if execution and verification were not centrally joined.
- No Critical or High defects remain after `tests/test_tool_result_verifier.py`-covered behavior and focused moved-module tests.

**Remediation & Optimization**:
- Applied: kept `raw_success` distinct from `verified` so Nexi does not claim completion without verification.
- Applied: diagnostic capability card now verifies the presence of `engine.tool_result_verifier`, `engine.tool_registry`, and `engine.tool_usage_intelligence`.
- Optimization: add tool-specific verifier plugins for browser state, app launch state, and clipboard state.

### 5. car layer collection

**Name**: car layer collection, normalized to Capability Layer Collection.

**Location**:
- `engine/diagnostic_capabilities.py:50-160` defines the complete capability collection.
- `engine/diagnostics.py:46-65` merges component checks with capability checks.
- `engine/diagnostics.py:165-194` converts capability cards into JSON-safe `ComponentStatus` records.
- `engine/diagnostic_doctors/runtime_doctor.py:214-242` emits runtime-doctor capability checks.

**Integration Change**: Capability layer data is centralized in Nexi’s engine diagnostics. The collection records role, safety policy, verifier, memory rule, diagnostic output, command, and remediation text for each capability.

**Research & Web-Search Evidence**:
- Python `importlib` documents package import semantics and module discovery, supporting the move from a side namespace into stable packages: https://docs.python.org/3/library/importlib.html
- MCP standardizes capability exposure through tools, prompts, resources, capability negotiation, logging, and error reporting: https://modelcontextprotocol.io/specification/2025-06-18

**Bug/Defect Findings**:
- Low, remediated: after physical file moves, leftover package initializers and bytecode caches remained under the retired `src` namespace.
- Low, remediated: diagnostics memory-path root calculation walked one directory too far after relocation.

**Remediation & Optimization**:
- Applied: deleted the retired `src` namespace after all functional files were moved.
- Applied: fixed `engine/diagnostic_doctors/runtime_doctor.py:119-127` root resolution for `data/memory`.
- Optimization: add a CI check that fails on word-boundary retired namespace imports.

### 6. memory produce kill library

**Name**: memory produce kill library, normalized to Reflection Memory plus Procedure / Skill Library.

**Location**:
- `engine/diagnostic_capabilities.py:105-132` defines reflection memory and procedure/skill library cards.
- `engine/reflection_memory.py:69-206` implements persistent lessons and recall.
- `engine/reflection_engine.py:41-145` extracts and persists correction, low-confidence, and failed-tool lessons.
- `engine/memory/__init__.py:3-28` exports merged memory modules under Nexi.
- `engine/tool_manifest_loader.py:30-123` validates and exposes tool manifest entries.

**Integration Change**: Memory modules from the retired isolated namespace were merged into `engine/memory`. Existing session, semantic, and episodic memory exports were preserved while adding local memory, policy, redaction, preference, task, and conversation-buffer exports.

**Research & Web-Search Evidence**:
- Reflexion describes language agents that maintain reflective text in episodic memory to improve later decisions: https://arxiv.org/abs/2303.11366
- MCP defines prompts as templated workflows and tools as model-executable capabilities, which matches a procedure/skill library design: https://modelcontextprotocol.io/specification/2025-06-18
- OWASP ASVS highlights security verification controls, relevant to redaction and safe memory retention: https://owasp.org/www-project-application-security-verification-standard/

**Bug/Defect Findings**:
- Medium, remediated: memory policy and conversation-buffer modules were segregated from `engine.memory`, risking duplicate memory interfaces.
- No Critical or High defects remain after conversation-buffer and reflection-related focused tests.

**Remediation & Optimization**:
- Applied: moved memory modules into `engine/memory` and updated `engine/memory/__init__.py` exports.
- Applied: verified conversation buffer security behavior with focused tests.
- Optimization: add a memory-migration smoke test that imports every symbol exported by `engine.memory.__all__`.

### 7. proactive monitor

**Name**: proactive monitor, normalized to Proactive Monitor.

**Location**:
- `engine/diagnostic_capabilities.py:133-145` defines the proactive monitor card.
- `engine/world_monitor_dashboard.py:21-47` aggregates dashboard panels.
- `engine/world_monitor_dashboard.py:98-126` adds the capabilities panel.
- `engine/world_monitor_dashboard.py:160` exposes dashboard state.

**Integration Change**: Runtime status aggregation stays in `engine/world_monitor_dashboard.py` and now consumes the Nexi capability catalog directly. This avoids a separate status system while exposing capability readiness to UI consumers.

**Research & Web-Search Evidence**:
- OpenTelemetry’s observability primer states that systems should emit signals such as traces, metrics, and logs to support questions about system behavior: https://opentelemetry.io/docs/concepts/observability-primer/
- Nielsen Norman Group’s visibility-of-system-status heuristic states systems should keep users informed with appropriate feedback: https://www.nngroup.com/articles/visibility-system-status/

**Bug/Defect Findings**:
- Low, remediated: first dashboard integration attempt could recurse if capability diagnostics queried dashboard state while the dashboard queried capability diagnostics.
- No Critical or High defects remain after dashboard tests passed.

**Remediation & Optimization**:
- Applied: capability diagnostics now only verify that the dashboard class exists, avoiding recursive state collection.
- Applied: `tests/test_world_monitor_dashboard.py` verifies the `capabilities` panel and JSON-safe output.
- Optimization: add a sampling throttle if dashboard refresh starts polling expensive probes.

### 8. conscience

**Name**: conscience, normalized to Conscious State Surface.

**Location**:
- `engine/diagnostic_capabilities.py:146-159` defines the conscious HUD card.
- `engine/ui_state_manager.py:60` canonicalizes UI state names.
- `engine/ui_state_manager.py:130` owns UI state manager behavior.
- `engine/ui_state_manager.py:276` exposes `emit_state()`.
- `engine/runtime_bridge.py:371` routes backend state to the UI bridge.

**Integration Change**: The conscious state surface uses Nexi’s existing UI state manager and runtime bridge, not a separate agent. Python remains the source of truth, and the HUD is display-only.

**Research & Web-Search Evidence**:
- Nielsen Norman Group states that visible system status improves control and trust: https://www.nngroup.com/articles/visibility-system-status/
- OpenTelemetry describes observability as asking questions about system behavior from emitted signals: https://opentelemetry.io/docs/concepts/observability-primer/

**Bug/Defect Findings**:
- Medium, remediated: state-display code previously relied on split imports for screen trust and app bridge functionality.
- No Critical or High defects remain after bridge and UI-state focused tests.

**Remediation & Optimization**:
- Applied: rewrote bridge imports to `engine.app.phase3_command_bridge`, `engine.app.runtime_context`, and `vision.screen_trust`.
- Applied: preserved backend state source-of-truth rules.
- Optimization: expose the last capability diagnostic status as a compact HUD tooltip rather than a long text payload.

### 9. its ud

**Name**: its ud, normalized to HUD and UI Diagnostics Surface.

**Location**:
- `www/controller.js:3-29` defines UI labels and allowed states.
- `www/controller.js:129-147` applies state updates to the visible UI.
- `www/controller.js:246-253` exposes diagnostics results to the browser bridge.
- `www/hud_orb.js:2-6` initializes the HUD canvas.
- `www/hud_orb.js:146-176` responds to state changes.
- `engine/runtime_bridge.py:355-362` sends diagnostics results to Eel.

**Integration Change**: The HUD remains in the existing legacy `www/` UI and receives diagnostics/state from Nexi backend modules. No new UI package or separate frontend subsystem was created.

**Research & Web-Search Evidence**:
- Nielsen Norman Group recommends appropriate feedback so users know whether the system registered an action: https://www.nngroup.com/articles/visibility-system-status/
- Playwright supports browser automation and reports, useful for future HUD verification: https://playwright.dev/docs/intro

**Bug/Defect Findings**:
- Low, remediated: HUD/report diagnostics needed capability metadata to be visible through the existing dashboard path.
- No Critical or High defects remain after dashboard and diagnostics tests.

**Remediation & Optimization**:
- Applied: added `capabilities` to `WorldMonitorDashboard` without changing the UI visual design.
- Applied: retained old UI bridge names such as `diagnosticsResult`.
- Optimization: add a browser smoke test that calls `diagnoseNexi()` and asserts the `capabilities` panel appears in the returned payload.

## Audit Log

| Step | Result |
|---|---|
| Filename scan | No remaining retired namespace directory or exact package-name file exists. |
| Content scan | No word-boundary retired namespace references remain across Python, Markdown, JSON, JS, CSS, HTML, YAML, TOML, INI, PowerShell, or batch files. |
| False-positive filename scan | Remaining substring matches are unrelated words in `scoring` and `vendoring` filenames. |
| Physical consolidation | Runtime packages were moved under `engine`, memory modules under `engine/memory`, diagnostics doctors under `engine/diagnostic_doctors`, and screen modules under `vision`. |
| Cleanup | Retired `src` namespace tree was deleted after functional files were moved. |

## Web-Search Evidence

| Evidence | URL | Applies to |
|---|---|---|
| Microsoft UI Automation - Win32 apps | https://learn.microsoft.com/en-us/windows/win32/winauto/entry-uiauto-win32 | Computer-use harness |
| Playwright Installation / Introduction | https://playwright.dev/docs/intro | Browser intelligence and future HUD browser checks |
| OWASP Application Security Verification Standard | https://owasp.org/www-project-application-security-verification-standard/ | Human approval, tool verifier, memory safety |
| Model Context Protocol Specification 2025-06-18 | https://modelcontextprotocol.io/specification/2025-06-18 | Tool consent, capability exposure, procedure library |
| NIST AI Risk Management Framework | https://www.nist.gov/itl/ai-risk-management-framework | Human approval and AI risk governance |
| Reflexion: Language Agents with Verbal Reinforcement Learning | https://arxiv.org/abs/2303.11366 | Reflection memory |
| OpenTelemetry Observability Primer | https://opentelemetry.io/docs/concepts/observability-primer/ | Proactive monitor and diagnostics signals |
| Visibility of System Status, Nielsen Norman Group | https://www.nngroup.com/articles/visibility-system-status/ | Conscious state surface and HUD feedback |
| Python importlib documentation | https://docs.python.org/3/library/importlib.html | Package consolidation and import validation |

## Sub-Agent Reports

| Sub-agent | Scope | Result | Residual risk |
|---|---|---|---|
| repo-analyst | Read-only retired namespace scan and new package location check | Passed: no retired namespace references; confirmed `engine/app`, `engine/brain`, `engine/control`, `engine/diagnostic_doctors`, `engine/voice`, `engine/memory`, and `vision` exist. | Did not inspect `.env`, `.git`, `.venv`, binary DB/model files, or local secret/state areas. |
| test-engineer | Focused moved-package validation across diagnostics, control approval/action gate, screen trust/vision, memory, intent brain, autonomy loop, and phase bridges | Passed: 460 tests passed, 0 failed, 5 dependency deprecation warnings. | Live mic, browser, and desktop-control flows still require a user-approved Windows session. |

## Verification Results

| Check | Command | Result |
|---|---|---|
| Import/reference scan | Retired namespace regex with source/doc file filters | Passed: no matches. |
| Retired tree scan | `glob src/**` | Passed: no files found. |
| Compile gate | `.venv\Scripts\python.exe -m compileall engine vision scripts tests` | Passed. |
| Focused moved-module tests | `.venv\Scripts\python.exe -m pytest tests/test_diagnostic_capabilities.py tests/test_engine_diagnostics.py tests/test_diagnostics.py tests/test_world_monitor_dashboard.py tests/test_conversation_buffer.py tests/test_screen_trust.py tests/test_screen_vision_permission.py tests/test_action_gate.py tests/test_intent_brain.py tests/test_autonomy_loop.py tests/test_command_regressions_phase4a2.py -v` | Passed: 312 passed, 6 warnings. |
| Independent sub-agent test batch | `.venv\Scripts\python.exe -m pytest tests/test_diagnostics.py tests/test_diagnostic_capabilities.py tests/test_engine_diagnostics.py tests/test_permission_manager.py tests/test_action_gate.py tests/test_screen_vision_permission.py tests/test_screen_trust.py tests/test_owner_trusted_mode.py tests/test_conversation_buffer.py tests/test_intent_brain.py tests/test_autonomy_loop.py tests/test_phase3_bridge_integration.py tests/test_phase4a1b_bridge.py -v --tb=short -ra` | Passed: 460 passed, 5 warnings. |

## Remediation Summary

Critical defects: none found.

High defects: none found.

Medium defects remediated:
- Split runtime package boundary across the legacy isolated `src` namespace was removed by moving files into Nexi-owned packages.
- Tool and memory interfaces were consolidated so the router, verifier, and memory systems use Nexi paths.

Low defects remediated:
- Stale package initializer and bytecode remnants under the retired namespace were deleted.
- Moved diagnostics doctor root path was corrected so `data/memory` is resolved from the repository root.
- Dashboard capability diagnostics were changed to avoid recursive dashboard reads.

Residual risk:
- Full live microphone, browser, and desktop-control validation still requires a Windows desktop session with user-approved physical interaction. Static imports and isolated runtime tests passed.
