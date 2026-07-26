# Stage 1 — Test Baseline

**Environment:** Windows 11, Python 3.11.15, project venv `.venv`
**Command:** `.venv\Scripts\python.exe -m pytest -q -rf --tb=line -p no:cacheprovider`

---

## Headline

| Metric | Before Stage 1 | After Stage 1 |
| --- | --- | --- |
| Bare `pytest` at repo root | **aborted** (collection error) | **3428 collected** |
| Tests passed | 3372 | **3422** |
| Tests failed | **38** | **0** |
| Collection errors | up to **286** (cascade) | **0** |
| Skipped | 6 | 6 |
| Duration | ~10 min | ~5 min 22 s |

Full run: `3422 passed, 6 skipped, 7 warnings, 2 subtests passed in 322.89s`.

## Why bare `pytest` used to abort

No pytest configuration existed, so collection started from the working
directory and reached `scripts/test_pipeline_startup.py` — a manual diagnostic
that performs runtime work at import and calls `sys.exit(1)` (line 23) when
openWakeWord cannot load. `sys.exit` during collection is an internal error, so
**the entire suite failed to run**, which is why "the repository has a passing
test suite" could not be reproduced by an outside auditor.

Fixed by `pytest.ini` (`testpaths = tests`, `norecursedirs`, markers).

## The 286-error cascade

Installing Chromium (needed for Crawl4AI) **un-skipped** three browser test
files that had been silently skipping. That exposed a pre-existing defect:
`test_chrome_controller` leaves a *running* asyncio loop on the main thread and
never stops it, so every later `sync_playwright()` raised
*"Sync API inside the asyncio loop"* — cascading into **286 errors** across 40+
unrelated files.

Fixed at one chokepoint: a session-scoped `shared_playwright` fixture in
`tests/conftest.py` that clears the leaked running-loop flag (thread-local, so
it only affects the main thread) and starts sync Playwright once for all UI
test files. Reproduction slice went **28 errors → 114 passed**.

## The 38 original failures — root causes

Grouped by cause, not by file:

| # | Cluster | Root cause | Type |
| --- | --- | --- | --- |
| 5 | memory secrets | Backends called `redact_sensitive()` **before** `is_safe_to_store()`. Redaction erased the very markers the gate looks for, so **every secret was stored**. Fixed in 4 backends (check-then-redact). | product bug |
| 3 | memory misc | `redact_sensitive(None)` returned `''`; JSONL `size()` counted corrupt lines instead of quarantining; secret gate missed natural language ("my api key **is** …"). | product bug |
| 5 | `ui_ack` | `wait_for_ack()` demanded an exact `sequence`; callers that don't track sequences could never confirm. Made optional. | product bug |
| 4 | `model_client` | Known + enabled provider with **no API key** hard-blocked instead of degrading to `MockModelClient`. | product bug |
| 3 | `browser_intelligence` | "No browser open" returned **failure**. It is a valid observation — and announcing a tool error to a blind user is worse than reporting the fact. | product bug |
| 2 | `computer_use` | Same for a blank screen; plus a test approving a *critical* action with a bare "approve", which the security policy intentionally refuses. | product + stale test |
| 2 | `runtime_bridge` | Stale assertions — code now passes a diagnostic `reason` kwarg. | stale test |
| 7 | hotword barge-in | Tests fed **320 bytes of silence** and asserted `wake == True`, and patched a removed API. Rewritten to the real contract: inject a scorer above threshold, assert the queued `post_barge_in_request`. | stale test |
| 6 | stragglers | URL-encoding bug in `handle_weather_search` (raw query in a Google URL); stale API assertions; 3 tests hitting the **live network**, taken offline. | product + stale test |
| 1 | `test_runtime_bridge` flake | `multiprocessing.Queue` writes via a feeder thread, so `get_nowait()` immediately after `put()` intermittently raised `Empty`. 3 occurrences fixed. | flaky test |

## No test was weakened to obtain a pass

Explicitly refused two "easy" green paths:

1. **Hotword barge-in (7 tests).** Making the originals pass would require
   waking on silence — reintroducing the TTS self-trigger bug the product is
   trying to eliminate. The *tests* were wrong; they were rewritten to assert
   the real contract, including a negative case proving silence does **not**
   barge in.

2. **Critical-action approval.** `click_ui_element` is `critical` risk and
   intentionally refuses a bare "approve" so a stray "yes" cannot fire an
   arbitrary UI click. The test was corrected to approve by explicit id; the
   guard was left intact.

Both are stricter after the change, not looser.

## Suite composition

- 383 test files, ~3428 collected tests
- Markers declared: `windows`, `audio`, `browser`, `integration`
- 6 skipped (environment-dependent)

## Known limitations of this baseline

- Verified **only** in the author's project venv on Windows. No clean-checkout
  or CI run — see `STAGE_1_BLOCKERS.md` B-02/B-03.
- Markers are declared but not yet applied per-test, so a headless lane would
  still attempt Windows/audio/browser tests.
- Bare `python` on this machine resolves to a **different venv**
  (`D:\hermes\hermes-agent\venv`) which lacks cv2/mediapipe. All results above
  use `.venv\Scripts\python.exe` explicitly. CI must pin the interpreter.
