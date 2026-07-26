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

---

## D-005 — Verify pre-fix behaviour by file copy, never `git stash`

**Date:** 2026-07-26

**Decision:** All "does this test actually catch the bug?" checks use
`git show HEAD:<path> > <path>`, run, then restore from a saved copy.

**Why:** a `git stash push <file>` during an earlier check silently failed to
apply. The test then "passed against the buggy code", and that was reported as
"the test does not catch the misroute" — a false conclusion drawn from a tool
that appeared to work. Re-checked by file copy, the same test failed 6 times
against the pre-fix registry.

**Also:** never run these swaps while a full suite is executing in the
background. Doing so swapped eight engine files out from under a live run and
invalidated it.

---

## D-006 — A green unit test is not evidence the feature works

**Date:** 2026-07-26

**Observation, recorded because it has now happened four times in this repo:**

| Case | Test was green while… |
| --- | --- |
| `test_hotword_barge_in_during_speaking` | barge-in was completely unreachable — it set `is_global_tts_active=False`, a state that never occurs in production |
| `test_react_provider_failures_are_errors` | NEXI spoke `provider_failed http_429` aloud — the test asserted the raw code reached the user |
| `_FOLLOWUP_SOURCES` gaining `"ui"` | the capture was still dropped one layer down on `not session_id` |
| first draft of `test_folder_flow_acceptance` | it "failed" pre-fix only because a fixture called a missing helper |

**Rule adopted:** a fix is not `PASS` until its test is observed to FAIL against
the pre-fix code for a *behavioural* reason. An `AttributeError`, import error
or fixture error proves the API changed, not that the defect is fixed.

**Consequence for acceptance tests:** they must be version-tolerant (use
`getattr` fallbacks for new helpers) so they can execute against the old runtime
and fail on assertions rather than on collection.

---

## D-007 — Schema validation is conservative, and bounded

**Date:** 2026-07-26 · **Commit:** `f6da8ad`

**Decision:** A reply is validated against the expected slot schema before it is
accepted. A wrong-kind answer is re-asked, at most twice, then the question is
abandoned.

**Why conservative:** rejecting a good answer costs the user one re-ask;
accepting a bad one silently creates a folder named "show me your diagnostics".
The asymmetry is the whole argument.

**Why bounded:** an unbounded reprompt loop is its own failure mode — NEXI would
sit asking the same question at a user who cannot phrase an answer it accepts.

**Why unknown schemas fall through:** a slot with no schema entry validates as
free text rather than failing closed. A missing entry should leave NEXI
unvalidated, never unusable.

**Precedence note:** cancel and workflow-switch are checked BEFORE schema
validation, so "open chrome" at a name prompt switches tasks rather than being
re-asked as an invalid name. Two of my own tests initially failed against this
correct behaviour because I picked a switch phrase as the example of an invalid
answer.

---

## D-008 — Two dialogue stores must never disagree

**Date:** 2026-07-26

**Decision:** Every path that clears the legacy follow-up store also closes the
`DialogueContext` — consume, cancel, switch, and schema-retry exhaustion.

**Why:** the migration deliberately runs both stores at once (the directive
forbids deleting the old systems in one commit). Two stores that can disagree
about whether a question is still open would recreate the exact ownership bug
this batch exists to fix, with the added difficulty that the two would blame
each other.

**Consequence:** `followup_manager` now calls into `dialogue_context` at every
terminal point, best-effort. Best-effort is deliberate — a failure in the new
layer must not be able to break an answer path that already worked.
