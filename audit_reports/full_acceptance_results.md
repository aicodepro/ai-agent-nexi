# Nexi Access Acceptance Results

Run date: 2026-07-23.

## Automated Contract Harness

Command: `.venv\Scripts\python.exe scripts\nexi_access_acceptance.py`

Result: PASS, six of six offline contracts.

| Contract | Result |
|---|---|
| Router V3 deterministic Spotify/live-search selection | PASS |
| Response duplicate and stale-generation suppression | PASS |
| Transcript short-command/follow-up/noise policy | PASS |
| Ordered UI states with non-visual cues | PASS |
| Temporal fact provenance and expiry | PASS |
| Spotify PKCE loopback/state contract | PASS |

## Requested Scenarios

| # | Scenario | Status | Evidence / Blocker |
|---|---|---|---|
| 1 | Blind user launches Nexi and understands status without seeing screen | BLOCKED | Canonical spoken labels and earcon payloads exist; requires real screen-reader/user walkthrough. |
| 2 | Wait 10 minutes in a quiet room with no false wake | BLOCKED | Requires physical microphone soak. |
| 3 | Wake, listen, ASR, think, speak, sleep | AUTOMATED PASS / LIVE BLOCKED | Lifecycle regression suites pass; physical mic/provider playback still required. |
| 4 | Complete Spotify PKCE and survive restart | BLOCKED | Offline PKCE/token-store contracts pass; requires Darsh's client ID, browser consent, Windows credential restart test. |
| 5 | Play the intended Spotify track | AUTOMATED PASS / LIVE BLOCKED | Search/device/start/readback flow passes with scripted Spotify API; Premium account/device required live. |
| 6 | Answer a current question from fresh web results with citations | PASS | Real DuckDuckGo smoke returned live=true and two citations. |
| 7 | Open app and create file with verified or explicit failure speech | PASS FOR EXISTING CONTRACTS | Tool verifier and safety suites pass; cross-app live UIA coverage remains partial. |
| 8 | Unclear speech asks a safe clarification | PASS | Transcript quality and command-bus tests pass. |
| 9 | Interrupt Nexi mid-speech without stale continuation | PASS | Session-epoch barge-in and watchdog suites pass. |
| 10 | Multi-step planner uses approval gates | PARTIAL | Existing compound router and approval suites pass; broad live desktop execution not exercised. |
| 11 | Restart and verify memory/token persistence | PARTIAL | Temporal file persistence is automated; Spotify Credential Manager restart is external. |
| 12 | Complete essential tasks with screen reader/no screen | BLOCKED | Requires assistive-technology acceptance session. |

## Supporting Results

- Consolidated changed-surface regression gate: 429 passed in 170.35 seconds.
- Lifecycle focused gate: 61 passed.
- Broader runtime/wake regression: 78 passed.
- Router/command-bus integration: 77 passed.
- Live intelligence/tool integration: 45 passed.
- Spotify integration/router contracts: 46 passed.
- Accessibility/transcript/browser/computer contracts: 44 passed.
- Safety/approval/security contracts: 55 passed.
- Safety verifier: 19 passed, 0 failed.
- `git diff --check`: passed; line-ending warnings only.

The focused groups overlap. The consolidated 429-test gate is the unique selected-surface result.

## Acceptance Verdict

Automated code-contract acceptance passes. Full end-to-end Nexi Access acceptance does not yet pass because four requested scenarios require credentials, a Spotify Premium playback device, a physical microphone/speaker environment, and a real blind-user screen-reader walkthrough. These remain explicitly blocked, not simulated.
