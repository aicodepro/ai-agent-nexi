# Nexi Autonomy — Verified Defect State (2026-06-26)

> This file previously summarized a 12-defect audit. **That audit was mostly stale.**
> All 17 claims were re-verified against the *current* source (parallel readers, ignoring
> the stale `audit_reports/*.md`). Below is the reconciled state. Full per-claim evidence is
> in `implementation_report_autonomy_audit.md`.

## Fixed in this pass

| Was | Fix |
|-----|-----|
| `_FOLLOWUP_SOURCES` missing `"double_clap"` (`command.py:482`) — clap wake silently dropped auto-followup after any question | added `"double_clap"` + guard test |
| Tool verifier blind-trusts handler `verified:True` for `open_app` | `tool_result_verifier.py` now confirms a real running process; honest `unverified_success` when it can't |
| `NEXI_AGENCY_AUTONOMY` / `NEXI_AGENCY_MODE` undocumented | added to `.env.example` with real defaults + mode list |
| Stale `NEXI_AUTO_FOLLOWUP_AFTER_TTS=false` references | `debug_session_ui_groq_live.py` + `REQUIREMENTS.md` corrected; red interview test removed (autonomy-on by default) |

## Audit claims that were already fixed / false (no action)

- P0-1 follow-up default — already `true` (`runtime_bridge.py:208`).
- P1-5 react route — wired end-to-end (`command.py:887`).
- P1-8 bridge finish race — guarded; pending set synchronously.
- P2-10 single-active workflow — intentional documented design.
- P2-12 optional-only slots — handlers guard empty args before acting.
- Structured v2 router, cross-turn slot-filling, two-layer required-slot validation — all live.

## Remaining gaps (open by choice — not done this pass)

| Gap | Severity | Note |
|-----|----------|------|
| Follow-up *capture* still uses `takecommand()` (P0-2) | low | dispatch already via command_bus; capture shared with mic-button path |
| `open_website` not truly verified | low | deliberately handler-trusted; real URL-load needs browser automation |
| No consolidated `PostBrainClassifier` object (P1-4) | low | behaviors (question-detect, unsafe-guard) already exist, scattered |
| Dead `engine/brain` deepseek/qwen provider registry (P2-9) | low | fallback works over gemini/hugchat/lightning; registry unused |
| Approval queue no auto-timeout (P2-11) | low | voice approve/reject works; nothing hangs — only stale entries linger |
| Router lacks `feature_id`/`next_action`; Groq uses json_object not json_schema | low | contract-shape, not a defect |
| No route-keyed conciseness layer in code | low | enforced by system prompt + 700-char spoken cap |

## Pre-existing, unrelated test failures (not introduced here)

Full suite: 2252 passed / 85 failed / 2 skipped. The 85 are pre-existing:
empty stub-package imports (`skills.*`, `core.*`, `wake.*`, `control.*`, `brain.planner`),
`runtime_bridge` `recognising` mapping drift, missing UI artifacts, and cross-test pollution
in the clap/hotword/wake cluster (those files pass in isolation). Proven independent of this
work by reverting the `command.py` edit and re-running.
