# NEXI Master TODO

Status vocabulary: `NOT_STARTED` `RESEARCHING` `READY` `IN_PROGRESS` `VERIFYING`
`PASS` `FAIL` `BLOCKED_EXTERNAL` `DEFERRED_WITH_JUSTIFICATION`

**A task is never `PASS` because a file exists.** `PASS` requires a test that was
verified to FAIL against the pre-fix code — otherwise the test proves nothing.

Baseline at time of writing: branch `jarvis-migration`, HEAD == `origin/jarvis-migration`,
0 unpushed. Full suite 3489 passed / 0 failed (reproduced locally, not taken on trust).

---

## Requirements-source gap (read this first)

| File | State |
| --- | --- |
| `NEXI_BRAIN_TOOL_AUTONOMY_UPGRADE_2026-07-26.md` | **ABSENT from this repo** |
| `NEXI_AUTONOMOUS_RESEARCH_ENGINEERING_MASTER_PROMPT.md` | **ABSENT from this repo** |

Both were produced in an external sandbox and never landed here. The directive
instructs reading the 2,310-line upgrade document completely; that is not
possible. Work is driven from the directive text pasted into the conversation.
Anything depending on detail unique to those files is `BLOCKED_EXTERNAL` until
they are added to the repository.

---

## Batch 1 — runtime truth

| ID | Task | Status | Evidence |
| --- | --- | --- | --- |
| B1-A | Single barge-in transaction (no double interrupt) | `PASS` | `tests/test_barge_in_single_transaction.py` — 3 behavioural tests fail pre-fix · `07b201b` |
| B1-B | Async workflow start is not verified completion | `PASS` | `tests/test_workflow_start_is_not_completion.py` — 8/9 fail pre-fix · `07b201b` |
| B1-C | Precise voice events (no `LISTENING -> SPEECH_ENDED`) | `PASS` | `tests/test_no_speech_transition.py` — 4/6 fail pre-fix · `d3df48a` |
| B1-D | Folder-flow acceptance test | `PASS` | `tests/test_folder_flow_acceptance.py` — **9/10 fail against the original runtime** · `8e764f4` |
| B1-E | Session for typed input | `PASS` | `tests/test_typed_input_gets_a_session.py` — 3/5 fail pre-fix · `8e764f4` |

**Batch 1 complete.** Suite verified in two complementary chunks (844 + 2680 =
3524 passed, 0 real failures) because three consecutive full runs were killed by
the environment. The single `test_demo_check` failure is pre-existing
order-dependence: it passes in isolation and failed identically before this work.

## Batch 2 — conversation continuity

| ID | Task | Status | Evidence |
| --- | --- | --- | --- |
| B2-1 | `DialogueContext` introduced alongside the 5 managers | `PASS` | `tests/test_dialogue_context.py` (15) · `d33dfa7` |
| B2-2 | Typed missing-information schemas | `PASS` | `tests/test_response_schemas.py` (29) + wiring — pre-fix: *"a command was accepted as the folder name"* · `f6da8ad` |
| B2-3 | Session/workflow ownership binding | `PASS` | `tests/test_workflow_session_isolation.py` — pre-fix: *"a new conversation inherited the previous question"* · `d33dfa7` |
| B2-4 | Durable follow-up capture states | `PASS` | `tests/test_followup_schema_and_capture.py` — request survives until the audio process acks · `f6da8ad` |
| B2-5 | Workflow switching and cancellation | `PASS` | pre-fix: *"the dialogue survived a cancel"* / *"survived a workflow switch"* · `f6da8ad` |

**Batch 2 complete.** Suite 651 + 2933 = 3584 passed. The folder family is the
first migrated onto `DialogueContext`; the legacy `workflow_state` still drives
execution and the dialogue layer is additive, per the directive's instruction not
to delete the old systems in one commit.

**Not yet migrated onto DialogueContext** (the remaining families, in the
recommended order): browser navigation, form filling, application control,
Spotify, email/calendar, developer workflows. `turn_manager`,
`clarification_manager` and `workflow_state` still hold their own state and are
kept in step by adapters rather than replaced.

## Batches 3-7

`NOT_STARTED`. JobCoordinator, Goal Model, World Model, Gemini Live,
self-development, production evidence.

---

## Completed earlier in this branch (verified)

| Task | Evidence |
| --- | --- |
| Provider 429 circuit breaker | `tests/test_provider_breaker.py` |
| Raw error codes no longer spoken | `tests/test_react_planner.py` (test previously asserted the defect) |
| Barge-in reachable during TTS | `tests/test_hotword_barge_in_during_speaking.py` — fails pre-fix |
| Follow-up slot no longer steals next command | `tests/test_provider_breaker.py` |
| Memory compound no longer stores the run-on | `tests/test_memory_commands.py` |
| Studio failure path no longer crashes in its own handler | `tests/test_intent_detect.py` |
| Session answer window (was 3s) | `tests/test_session_awaits_answer.py` — fails pre-fix |
| Typed requests can auto-listen | `tests/test_session_awaits_answer.py` |
| Speaking no longer cancels awaiting-user | `tests/test_turn_awaiting_user.py` — verified pre/post with old API |
| Public research no longer routes to codebase research | `tests/test_research_routing.py` — 6 fail pre-fix |

---

## Rejected requirements (evidence-based)

| Requirement | Decision | Evidence |
| --- | --- | --- |
| §8 echo-correlation rejection + speaker verifier for TTS self-trigger | `DEFERRED_WITH_JUSTIFICATION` | Wake model scores **0.0037 on silence**, **0.0038 on room noise** — matching the log's idle baseline exactly. Model is the correct 857,282-byte file. The 0.997 hits came from a user deliberately testing barge-in; TTS segments the user did not interrupt produced no barge-in. Building this would make barge-in harder to trigger and regress a working fix. |

---

## Owner-only blockers

| ID | Blocker | Owner action |
| --- | --- | --- |
| EXT-1 | Two API keys in public git history (Groq confirmed live) | Rotate at console.groq.com/keys and console.cloud.google.com/apis/credentials |
| EXT-2 | CI has never executed | `git mv ci/workflows/*.yml .github/workflows/` — needs `workflow` OAuth scope |
| EXT-3 | Requirements documents absent | Add the two `NEXI_*.md` files to the repo |
| EXT-4 | Blind/low-vision participant testing | Real participant required |

---

## Batch 3 — task autonomy

An audit preceded any building, because this repository's failure mode is
modules that exist and are never reached.

| ID | Task | Status | Evidence |
| --- | --- | --- | --- |
| B3-1 | Goal Model | `PASS` | `engine/job_coordinator.py` · `tests/test_job_coordinator.py` · `300858a` |
| B3-2 | JobCoordinator, 11 typed states | `PASS` | COMPLETED ≠ verified; a dependency counts only when VERIFIED · `300858a` |
| B3-3 | Undo journal | `PASS` | `tests/test_undo_journal.py` — wired into folder creation, refuses to delete a non-empty folder · `300858a` |
| B3-4 | ResponseCoordinator sole speech | `DEFERRED_WITH_JUSTIFICATION` | **13 modules still call `speak()` directly.** Not claimed as done. |

### Already live before Batch 3 (verified by import graph, not assumed)

`response_coordinator` · `tool_result_verifier` · `world_model` (intent context,
react planner, tool registry) · `browser_intelligence` · `live_intelligence`
(local_skills) · `forge` / `claude_code` (via `agent_runtime`).

---

## Batches 4–7 — assessment

Assessed rather than claimed. Nothing below is marked `PASS` on the strength of
a file existing.

| Item | Reality |
| --- | --- |
| B4 World Model / ScreenState | `world_model.py` live; `computer_use.py` provides screen_read + ImageGrab. **No dedicated recovery ladder module.** Partial. |
| B4 Browser / desktop control | `browser_intelligence.py` live; semantic-locator discipline unverified against the directive's contract. |
| B5 Gemini Live adapter | **ABSENT.** No bidi adapter, no websockets dependency. Buildable locally; real verification is `BLOCKED_EXTERNAL` (credentials). |
| B6 Self-development loop | `engine/claude_code/` has dispatcher, session, verifier, terminal_bridge, environment. `engine/forge/` is a thin `__init__`. Partial; the incident → worktree → patch → verify → rollback chain is not proven end to end. |
| B7 CI | Three workflow files exist under `ci/workflows/` and **have never executed** (`EXT-2`, needs `workflow` OAuth scope). |
| B7 Soak / 1000 replays / installer | Not run. |
| B7 NVDA / Narrator / blind participants | `BLOCKED_EXTERNAL` — requires a real screen-reader environment and real participants. |

**Honest classification: `INTERNAL_ALPHA`.** The 9/10 gate requires one lifecycle
authority, one route authority, one dialogue authority, one job authority and
one response authority. Dialogue and job authorities now exist. Route authority
is partial (Router V2 still handles a real share). Response authority is not
achieved — 13 direct `speak()` callers. CI has never run. No participant testing.
