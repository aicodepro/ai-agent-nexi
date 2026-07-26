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
| B2-1 | `DialogueContext` replacing 5 managers | `NOT_STARTED` | multi-day migration; see decision log |
| B2-2 | Typed missing-information schemas | `NOT_STARTED` | — |
| B2-3 | Session/workflow ownership binding | `NOT_STARTED` | stale workflow leaked into a new wake session |
| B2-4 | Durable follow-up capture states | `NOT_STARTED` | boolean auto-listen still the source of truth |
| B2-5 | Workflow switching and cancellation | `NOT_STARTED` | partial: command-as-name rejected |

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
