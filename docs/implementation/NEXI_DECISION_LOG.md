# NEXI Decision Log

Each entry records what was decided, what was rejected, and the evidence — so a
later session can re-open a decision on new evidence rather than on memory.

---

## D-001 — Do not add echo rejection or speaker verification for barge-in

**Date:** 2026-07-26 · **Commit at decision:** `288eddc`

**Decision:** Reject the requirement to add TTS echo-correlation rejection,
near-end VAD gating, and a speaker verifier to the barge-in path. Keep the plain
wake-score + threshold path.

**Claim being rejected:** "NEXI triggers itself while speaking — during TTS the
wake score reaches 0.997/0.996, so NEXI interprets its own output as barge-in."

**Evidence against the claim:**

| Measurement | Result |
| --- | --- |
| Wake model on 3s pure digital silence | peak `0.0037` |
| Wake model on quiet noise (rms ~0.0008) | peak `0.0038` |
| Wake model on room noise at the user's measured floor (rms ~0.0125) | peak `0.0038` |
| Idle baseline throughout the runtime log | `0.0036`–`0.0038` |
| `models/hey_nexi.onnx` | 857,282 bytes, byte-identical to HEAD |

The measured floor matches the log's idle baseline exactly, so the model is not
degenerate and does not fire on silence or noise. The high scores appeared in
exactly one voice session — the one in which the user had been instructed to say
"Hey Nexi" mid-answer to test barge-in. TTS segments the user did not interrupt
(`show_diagnostics`, 371 spoken chars; `what_did_you_learn`; the research answer)
produced no barge-in at all, which a self-trigger would not allow.

**Alternatives considered:** implement the full acceptance policy anyway as
defence-in-depth. Rejected: every added condition makes a genuine barge-in
harder to trigger, and barge-in had *just* been repaired from being completely
unreachable. Raising its bar on a false premise would regress the fix.

**Rollback:** if physical testing later demonstrates real TTS self-activation,
re-open this decision. The measurement script in this entry is the reproduction.

---

## D-002 — Renew the barge-in transaction instead of expiring it mid-stop

**Date:** 2026-07-26

**Decision:** `_expire_pending_barge_in()` renews its soft deadline while TTS is
still active or cooling down, bounded by a hard deadline. A closed transaction
starts a refractory window.

**Why:** the transaction was the only thing rejecting further candidates.
Clearing it on a fixed deadline while TTS was still stopping let the tail of the
same utterance open a second interrupt — the observed
`transaction_expired` → `hotword_during_speaking` sequence.

**Bounded:** the hard deadline still releases a stuck transaction, so a hung TTS
producer cannot pin the microphone. Covered by
`test_hard_deadline_still_releases_a_stuck_transaction`.

---

## D-003 — A started workflow is never `verified`

**Date:** 2026-07-26

**Decision:** Added `_accepted()` alongside `_ok()`. Background workflow starts
and non-terminal synchronous runs return `verified=False`; only a terminal
success status returns `verified=True`.

**Why:** `_ok()` hardcodes `verified=True` and the background branch used it for
a run whose agents had not executed. `verified` is what
`assistant_response.verified_action()` treats as evidence of a real outcome.

**Consequence handled:** with `verified=False`, the unverified-action guard
rewrites any message matching `ACTION_SUCCESS_RE` — which includes
"Started …". The start message was reworded to "I've begun …" so the guard
leaves a truthful progress message intact while still blocking completion
claims. Covered by `test_background_start_message_does_not_claim_completion`.

---

## D-004 — Defer the DialogueContext and JobCoordinator migrations

**Date:** 2026-07-26

**Decision:** Do not replace `turn_manager`, `followup_manager`,
`clarification_manager`, `workflow_state` and `workflow_manager` with a single
`DialogueContext` in this pass. Same for `JobCoordinator` and sole
`ResponseCoordinator` speech ownership.

**Why:** these are correct architecture and remain necessary. They are also a
multi-day migration through the hottest paths in the runtime. Landing them in
one pass behind a green suite is how a subtly broken assistant ships while
tests stay green — the exact failure mode already found twice in this repo,
where tests passed while mocking away the production condition.

**Interim:** the specific defects those migrations would have fixed were fixed
individually, each with a test verified to fail pre-fix. The orthogonal
voice-phase / dialogue-status split (`_awaiting_user`) is the smallest correct
piece of the DialogueContext design and is already in place.

**Migration order when resumed:** folder/file workflows → browser navigation →
form filling → application control → Spotify → email/calendar → developer
workflows, behind compatibility adapters, one family per commit.
