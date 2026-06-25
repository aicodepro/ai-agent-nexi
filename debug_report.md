# Debug Report — Nexi feature tools (roadmap #1–#15)

> **Scope:** the ~40 voice tools / 11 modules added this session (OS/net/storage/runtime/app/skill/browser/approval/computer-use). The unrelated in-progress `src/orin → engine` refactor in the working tree was **left untouched** per instruction.
> **Method:** static compile + import → live execution of every tool → programmatic wiring check → 42-agent adversarial review (one reviewer per module → adversarial verify) → manual evaluation of candidates the reviewer left unverified → fixes with TDD → full-suite regression.

## 1. Summary Table

| Severity | Found | Fixed | Reviewed → no fix |
|----------|-------|-------|-------------------|
| Critical | 0 | 0 | 0 |
| High | 0 | 0 | 0 |
| Medium | 2 | 2 | 0 |
| Low | 1 | 1 | 6 |
| **Total** | **3 fixed** | **3** | **6 low (documented)** |

Plus one **pre-existing** bug found earlier in the session and already fixed (`local_memory.py` `_PROJECT_ROOT`, see §2.4).

Empirical baselines (all green): `py_compile` + import — 13/13 files OK · live execution — **42/42** (read-only verify; gated tools queue, never act) · wiring consistency — **38/38 tools** present in registry + dispatch + both taxonomy sets · 0 routing regressions.

---

## 2. Issue Details (fixed)

### 2.1 [MEDIUM · bug] `_capture_console` ignored its `target`, sampled the wrong tab
- **Location:** `engine/browser_intelligence.py` `_capture_console` (was lines 77–97).
- **Problem:** the function declared `target` but used `pages[0]`. CDP `/json/list` ordering is not guaranteed to match Playwright's `contexts/pages` ordering, so with multiple tabs open `read_browser_console` could listen to the wrong tab's console. Inconsistent with `_page_text`, which matches by URL.
- **Fix:** extracted a pure, testable helper `_select_page(pages, target_url)` that matches the page by URL with a first-page fallback, and `_capture_console` now passes `target["url"]` into it.
- **Verification:** new unit tests `test_select_page_matches_target_url` / `test_select_page_falls_back_to_first` pass; `test_browser_intelligence.py` green.

### 2.2 [MEDIUM · security] `approved` flag could bypass the approval gate
- **Location:** `engine/approval_queue.py` `gate()` / `approve()`.
- **Problem:** the gate proceeded when `slots.get("approved")` was truthy. Router slots flow straight to `execute_tool` (`command.py:825`), so in principle an LLM-router-emitted `approved` slot could let a HIGH/CRITICAL action (click/type/browser write) execute without human approval.
- **Fix:** replaced the plain boolean with an **internal token** (`_approval_token == "__nexi_internal_approved__"`) that *only* `approve()` injects. The intent router cannot emit this key/value, so a user/router-supplied `approved` slot no longer bypasses the gate. (Implemented entirely within `approval_queue.py` + callers — `command.py` was **not** touched, per the leave-the-refactor-untouched constraint.)
- **Verification:** new tests `test_external_approved_flag_cannot_bypass_gate` (approval_queue) and `test_external_approved_flag_does_not_bypass` (computer_use) confirm a plain `approved:True` now **queues** instead of executing; the legitimate `approve_action` path still executes (`test_approve_action_tool_executes_oldest`, `test_click_direct_with_internal_token`).

### 2.3 [LOW · bug] `_local_ip()` fallback could report loopback (`127.*`)
- **Location:** `engine/net_awareness.py` `_local_ip()` fallback (was lines 56–59).
- **Problem:** the `gethostbyname(gethostname())` fallback (used only when the UDP routing trick fails, e.g. offline) can resolve to a `127.*` address on some hosts, so `get_ip_address` could announce "Your local IP address is 127.0.0.1" — wrong, and inconsistent with `_all_ipv4()` which filters loopback.
- **Fix:** guarded the fallback to reject `127.*` and return `""` (which `get_ip_address` already handles gracefully).
- **Verification:** new test `test_local_ip_never_returns_loopback` (forces the fallback + a loopback hostname) passes.

### 2.4 [pre-existing · fixed earlier] `local_memory.py` `_PROJECT_ROOT` overshoot
- **Location:** `engine/memory/local_memory.py:8` — `"..","..",".."` → drive root. Fixed to `"..",".."`. `test_memory_brain.py` → 70 passed. (Detailed in `error.md`; not part of this session's new feature code — surfaced by the regression discipline.)

---

## 3. Reviewed candidates → no fix (low / by-design), with rationale

The adversarial reviewer raised 8 further candidates; 2 became the fixes above. The other 6 were
evaluated manually (their automated verify step was cut off by a session limit and re-judged here):

| Candidate | Location | Verdict | Rationale |
|-----------|----------|---------|-----------|
| Substring match in `_is_installed` | `app_intelligence.py` | LOW / keep | Install detection is a *confidence heuristic* only; a loose match (e.g. "code" in "qr code") at worst nudges confidence — the resolver still returns a valid candidate. |
| Substring match in `_match_category` | `app_intelligence.py` | LOW / keep | Longest-match wins; synonyms are deliberately permissive ("web" → browsing). Tightening risks regressing intended matches locked by tests. |
| `_TASK_APPS` key validation | `app_intelligence.py` | LOW / keep | Static curated dict; keys are covered by `_TASK_SYNONYMS`/tests. No runtime input path. |
| Window-focus race | `computer_use.py` | LOW / inherent | Inherent to any UI-automation tool; the **approval gate** means the user just confirmed, narrowing the window. Documented as a known limitation. |
| "Inconsistent slot naming" (click) | `computer_use.py` | NOT A BUG | `click_ui_element` intentionally accepts `target` **or** `text`; the router emits `target`. Verified consistent. |
| Broad `except Exception` in indirections | net/browser/computer_use | LOW / by-design | Intentional graceful degradation (missing optional libs / no debug browser → verified, honest message). Optional future enhancement: debug-level logging. |
| `resolve_app_name()` call "lacks" handling | `app_intelligence.py` `resolve_for_task` no-category branch | NOT A BUG | `resolve_app_name` is null-safe (`str(value or "")`) and always returns a dict with `app_name`; the branch coerces to a string and sets a sensible confidence. No defect. |

> Note: the reviewer's automated *verify* step for these 7 candidates was interrupted by a session limit; each was re-judged manually here against the actual code.

None are correctness defects in normal operation; all are read-only or approval-gated paths that degrade safely.

---

## 4. Verification Results

| Check | Result |
|-------|--------|
| `py_compile` (13 files) | ✅ OK |
| Module imports (10) | ✅ OK |
| Live execution (every tool) | ✅ **42/42** (read-only verify; gated queue) |
| Wiring consistency (registry/dispatch/taxonomy) | ✅ **38/38**, 0 problems |
| Fixed-area suites (net/browser/approval/computer/browser-write) | ✅ **63 passed** |
| Full suite (regression) | ✅ **2152 passed / 86 failed** — set-diff vs pre-session baseline is **empty** (0 net-new failures). The 86 are the pre-existing baseline (stale `src.orin`/`skills.apps` imports, API drift, flaky voice/clap), unrelated to this work. |

## 5. Cleanup

- No temporary test scripts/files were left in the repo: all verification ran via `python -c …` one-liners (no files written) and the permanent pytest suites. Scratch output (`/full_run*.txt`) lives outside the repo.
- The pre-existing working-tree noise (`datasets/`, `artifacts/*.wav`, the `src/orin→engine` refactor) was **deliberately not touched** — it is not part of this work and removing it could destroy in-progress changes.
