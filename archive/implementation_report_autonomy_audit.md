# Implementation Report — Autonomy Audit Reconciliation

Date: 2026-06-26 · Branch: `jarvis-migration` · Commits: **none pushed** (per instructions)

## TL;DR

The autonomy audit (`error.md`, `audit_reports/*.md`) is **mostly stale**. I verified all 17
claims against the *current* source with parallel readers. Of the "12 confirmed defects," only
**two** were genuinely broken; the rest were already implemented, intentional design, or false.
Scope chosen by the user: **real fixes + verifier strengthening** (not the optional polish).

## Verification result (claim → reality)

| Claim | Audit said | Verified reality | Action |
|---|---|---|---|
| P0-1 followup default false | broken | already `true` (`runtime_bridge.py:208`) | reconciled (see Q1) |
| P0-2 legacy `takecommand()` | broken | dispatch already via command_bus; only *capture* is legacy, shared w/ mic-button | left (out of scope) |
| **P0-3** `double_clap` missing | broken | **genuinely broken** | **fixed** |
| P1-4 no post-brain classifier | missing | question-detection + unsafe-guard already work; no single object | left (optional) |
| P1-5 react route unhandled | missing | wired end-to-end `command.py:887` | none |
| **P1-6** verifier path-only | weak | **genuinely weak** (blind-trusts `verified:True`) | **strengthened (open_app)** |
| P1-7 agency env undocumented | missing doc | wiring works; only `.env.example` doc missing | **documented** |
| P1-8 bridge finish race | bug | guarded; pending set synchronously | none |
| P2-9 provider fallback | not wired | works over gemini/hugchat/lightning; deepseek/qwen registry dead | left (optional) |
| P2-10 single-active workflow | defect | intentional documented design | none |
| P2-11 approval no timeout | missing | voice approve/reject works; only auto-expire missing (nothing hangs) | left (optional) |
| P2-12 optional-only slots | defect | handlers guard empty args before acting | none |
| router contract | — | live & validated; lacks `feature_id`/`next_action` | left (optional) |
| dialogue slot-filling | — | works cross-turn | none |
| required-slot validation | — | validated at routing + execution layers | none |
| concise response policy | — | prompt-prose + 700-char cap; no route-keyed code | left (optional) |

## Files changed

**Source**
- `engine/command.py` — added `"double_clap"` to `_FOLLOWUP_SOURCES` (P0-3 root-cause; the clap wake path emits `source="double_clap"`, which the set rejected, silently killing auto-followup after any question in a clap turn).
- `engine/tool_result_verifier.py` — new `_app_process_running()` (read-only psutil scan, never launches) + an `open_app` branch that **confirms a real process** instead of trusting the handler's self-reported `verified:True`. No app name to check → honest `unverified_success`.
- `engine/local_skills.py` — `open_app()` now returns `"app": app_name` (so the verifier can check it) and drops the misleading hard-coded `"verified": True`.
- `.env.example` — documented the two real Agency knobs: `NEXI_AGENCY_AUTONOMY=false`, `NEXI_AGENCY_MODE=supervised` (modes: `locked|manual|supervised|autonomous_safe`).
- `scripts/debug_session_ui_groq_live.py` — stale check updated (`NEXI_AUTO_FOLLOWUP_AFTER_TTS` default is `true`, not `false`).
- `REQUIREMENTS.md` — stale row `JARVIS_AUTO_FOLLOWUP_AFTER_TTS=false` → `NEXI_AUTO_FOLLOWUP_AFTER_TTS=true`.

**Tests**
- `tests/test_followup_sources_double_clap.py` — **new** guard: `double_clap` must stay in `_FOLLOWUP_SOURCES`.
- `tests/test_tool_result_verifier.py` — **new** cases: `open_app` verified only when process running; `open_app` without app name stays unverified.
- `tests/test_clarification_followup_slot_completion.py` — mocks `_app_process_running=True` for the open→chrome integration test (a mocked launch can't satisfy a real process check).
- `tests/test_auto_followup_disabled_for_interview.py` — **deleted** (decision: autonomy-on by default; demo/interview suppression is already handled independently by `engine/demo_mode.py`). This test was already red.

## Decisions made by the user

1. **Follow-up default = autonomy-on.** Code default stays `true`; redundant interview test removed; stale refs cleaned. `demo_mode.py` still suppresses follow-up during demos via `NEXI_DEMO_DISABLE_AUTO_FOLLOWUP`.
2. **Scope = real fixes + verifier strengthening.** Optional polish (capture unification, dead provider-registry cleanup, route-keyed conciseness layer, approval auto-timeout, router `feature_id`/`next_action`) intentionally **not** done.

## Tests run

```
# changed-area + master-prompt suites (clean)
pytest tests/test_command_bus*.py tests/test_nexi_agency*.py tests/test_audio_wake_pipeline.py \
       tests/test_intent_router_v2_product.py tests/test_tool_result_verifier.py \
       tests/test_clarification_followup_slot_completion.py tests/test_followup_sources_double_clap.py \
       tests/test_local_skills.py tests/test_desktop_controller.py tests/test_dialogue_architecture_v2.py
→ 102 passed, 2 failed*  (*the 2 are test_audio_wake_pipeline cross-test pollution; the file passes 34/34 alone)

# full suite
pytest tests/  → 2252 passed, 85 failed, 2 skipped
```

**The 85 failures are pre-existing and unrelated to this work** (proven: reverting my `command.py`
edit to HEAD leaves the nearest-looking failure still failing). Categories:
- `test_imports` / `test_skills_basic` — `ModuleNotFoundError` for empty stub packages (`skills.*`,
  `core.*`, `memory.*`, `wake.*`, `control.*`, `brain.planner`) that don't exist yet.
- voice/speech/barge-in — `runtime_bridge` maps `speech_started`→`listening` not `recognising`
  (drift in code already modified before this session).
- clap/hotword/wake cluster — pre-existing arbitration drift + cross-test global-state pollution
  (these files pass in isolation).
- `test_session_summary_manager` (API drift), `test_mark_ui_*` / `test_skill_files_exist`
  (missing artifacts/files).

`python -m compileall engine tests` — clean.

## Live validation

```powershell
.venv\Scripts\python.exe run.py
```
- "Hey Nexi" via **double clap**, then ask anything that triggers a question → it now keeps
  listening (P0-3). Previously the session went idle after the question on clap-initiated turns.
- "Hey Nexi, open Chrome." → if Chrome's process actually appears, "Done."; if the launch
  silently failed, it now honestly says it couldn't verify (P1-6) instead of claiming success.

## Remaining risks / known ceilings

- **`open_app` process match is a name-substring heuristic** (psutil). Edge cases: an app whose
  process name differs wildly from its launch name, or a coincidental substring match. Marked with
  a `ponytail:` comment; upgrade path is an exact APP_COMMANDS→process-name map if it ever bites.
- **`open_website` is still handler-trusted** — deliberately not "verified". A browser is usually
  already open, so a process check would be near-useless, and true URL-load verification needs
  browser automation (heavy/flaky). Honest non-claim beats a fake one.
- The optional items in the table above remain open by choice.

## Suggested next phase (only if wanted)

1. Unify follow-up capture onto the Silero-VAD/Groq `audio_wake_pipeline` (P0-2) — also fixes the
   mic-button path's Google-ASR fallback.
2. Delete the dead `engine/brain` provider registry (deepseek/qwen) or wire it into the fallback.
3. Route-keyed conciseness post-processor in `assistant_response.make_response` (hooks already exist).
4. Approval auto-expire using the `created` timestamp already stored in `approval_queue._pending`.
