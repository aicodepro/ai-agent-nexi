# Stage 1 — Unresolved Blockers

Recorded honestly. Nothing below is marked PASS. Items that cannot be verified
in this environment are marked **BLOCKED**, never converted into a pass.

---

## B-01 — Secrets and private data remain in git history — CRITICAL

`git rm --cached` stops *future* distribution but does not rewrite history.
Still retrievable from earlier commits on the public remote
`github.com/aicodepro/ai-agnet-nexi`:

| Item | Where | Status |
| --- | --- | --- |
| Gemini API key | `archive/audit.md` (redacted in HEAD) | in history |
| Groq API key | `archive/audit.md` (redacted in HEAD) | in history |
| Personal wake-word recordings (270 `.wav`) | `hey_nexi_clips/` | in history |
| Recent ASR captures | `artifacts/*.wav` | in history |
| LBPH face biometric model (17 MB) | `trainingData.yml` | in history |

The Groq key was verified **live** during this session (chat + models endpoints
returned HTTP 200).

**Required owner action (cannot be done for you):**
1. Rotate both keys — console.cloud.google.com and console.groq.com.
2. Decide whether to rewrite history (`git filter-repo` / BFG) or accept the
   exposure. Rewriting rewrites all downstream SHAs.

Biometric and voice data of an identifiable person in a public repository is a
privacy issue independent of the API keys.

## B-02 — No CI pipeline — HIGH

Stage 1 item 7 (clean-checkout CI with headless + Windows lanes) is **not
done**. The suite is currently verified only on the author's machine, in the
project venv. A clean-clone install has not been executed end to end.

Missing: `.github/workflows/` with headless unit lane, Windows integration
lane, secret scan, dependency audit, generated-file drift check.

Until this exists, "reproducible" is asserted, not proven.

## B-03 — Clean-checkout install not executed — HIGH

Dependency groups now exist (`pyproject.toml`), and 7 previously undeclared
runtime imports were added to `requirements.txt`. But no fresh clone into an
empty venv has been installed and run. Version pins/lockfile are absent —
dependencies are unpinned, so two installs can differ.

## B-04 — External integrations unverified — BLOCKED (no credentials/hardware)

| Integration | Status | Reason |
| --- | --- | --- |
| Gemini Live | BLOCKED | not implemented (P0-4); no Live session exists |
| Spotify | BLOCKED | no live account authorised in this environment |
| Gmail / Calendar | BLOCKED | connectors not implemented |
| NVDA / Narrator | BLOCKED | no screen reader available to this process |
| Physical microphone | BLOCKED | no verified human speech round-trip run |
| Groq Orpheus TTS | BLOCKED | model requires org terms acceptance in Groq console |

## B-05 — Architectural consolidation not started — HIGH

Deliberately out of Stage 1 scope, and unchanged:

- **P0-4** Not Gemini Live — REST `generateContent` + separate ASR/TTS.
- **P0-5** Router V3 is a compatibility facade delegating to `route_intent_v2`
  (`router_v3.py:63-69`, authority recorded as `v2_compatibility`).
- **P0-6** Multiple owners of routing, session state, memory and responses.
- **P1-1** `ResponseCoordinator` is not the sole speaker; direct `speak()`
  calls remain in `command_bus`, `runtime_bridge`, `audio_wake_pipeline`,
  `features`, `news`, `file_operations` and others.
- **P1-12** God functions remain (`dispatch_intent` ~562 lines,
  `_execute_handler` ~366, `submit_user_command` ~256).

These are the audit's Phases 1–5 — multi-week work. Attempting them inside a
bug-fix pass would add a fourth parallel system, which is the exact failure
mode the audit diagnoses.

## B-06 — Accessibility not user-validated — HIGH

Face auth no longer blocks startup (was default-ON with an infinite wait), and
fake telemetry is gone. But **no blind or low-vision participant has evaluated
Nexi**. Per W3C guidance, conformance checks do not substitute for user
evaluation. Remaining UI issues from the audit are unfixed: clickable
non-semantic `<div>` controls, missing input labels, removed focus outlines,
6–10 px text.

`BLIND_USER_ACCEPTANCE_REPORT.md` must not be marked PASS without real
participants.

## B-07 — Verification coverage incomplete — MEDIUM

`tool_result_verifier` independently verifies only process existence and
created paths; most tools are trusted via their own `raw["verified"]`. Browser
and desktop actions still report success without postcondition evidence
(P1-3/P1-4).

---

## Stage 1 exit criteria — honest status

| Criterion | Status |
| --- | --- |
| No required first-party source file missing | **PASS** |
| Test collection completes without error | **PASS** (3428 collected) |
| Headless tests pass | **PASS** in project venv; **BLOCKED** on clean CI (B-02) |
| Windows-only tests correctly marked | **PARTIAL** — markers declared, not yet applied per-test |
| External tests report BLOCKED when unavailable | **PARTIAL** — documented here, not automated |
| Fresh checkout installs without manual package installation | **NOT VERIFIED** (B-03) |
| No private runtime artifact required from the repo | **PASS** for HEAD; **FAIL** for history (B-01) |
| No valid test weakened or deleted to achieve a pass | **PASS** — see `STAGE_1_TEST_BASELINE.md` |

**Stage 1 is therefore NOT fully passed.** Blocking items: B-01, B-02, B-03.
Per the directive, SessionController consolidation, Router V3 replacement and
catalog generation should not begin until those clear.
