# Accessibility Report

## Implemented

- Canonical backend lifecycle labels for sleep, online, listening, waiting, recognising, thinking, saying, and error.
- Session-generation and monotonic sequence fields in every UI event.
- Exact frontend acknowledgement correlation.
- Distinct non-visual earcon identifiers in every lifecycle payload.
- Optional Windows earcon playback via `NEXI_EARCONS_ENABLED`.
- Reasoned transcript quality decisions that preserve short commands and short follow-up answers.
- Filler/noise rejection without dispatching an action.
- Safe clarification for uncertain short, non-lexical, noisy, or language-uncertain transcripts.
- UI Automation semantic value setting before raw keyboard injection.
- Semantic UIA element lookup for desktop clicks.
- Playwright text/label/placeholder lookup for browser operations.
- Explicit partial/unverified results when screen or browser content is unavailable.
- One-response acceptance per command request and session generation.
- Spoken long-answer shortening remains separate from full display content.

## Automated Evidence

- Accessibility/transcript/browser/computer/UI group: 44 passing tests.
- Offline Nexi Access acceptance harness: six of six contracts passing.
- Lifecycle focused gate: 61 passing tests.
- Broader wake/runtime regression: 78 passing tests.

## Not Yet Proven

- NVDA, JAWS, Narrator, or VoiceOver walkthrough by a blind user.
- Status comprehension with the monitor off.
- Earcon audibility and preference tuning with real users.
- High-contrast and low-vision visual review of `www_mark`.
- Keyboard-only traversal of all Eel UI controls.
- Ten-minute physical-microphone false-wake soak.
- Semantic automation coverage across every target application.

## Verdict

The code contracts are materially more accessibility-first and truth-preserving, but full accessibility acceptance remains blocked on assistive-technology and physical-device testing. It is not valid to claim end-to-end blind-user acceptance yet.
