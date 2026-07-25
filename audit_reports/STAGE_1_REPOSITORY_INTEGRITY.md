# Stage 1 — Repository Integrity

**Scope:** repair repository integrity and establish a trustworthy baseline
*before* activating the unified agent catalog. No new runtime agents were
implemented in this stage, per the Stage 1 directive.

**Environment:** Windows 11, Python 3.11.15, project venv `.venv`
**Branch:** `jarvis-migration`

---

## 1. Missing first-party source — ROOT CAUSE FOUND

Two modules imported by the runtime were absent from any fresh clone:

- `engine/agent_runtime/environment.py`
- `engine/claude_code/environment.py`

They existed on the developer machine but were **excluded by `.gitignore`**.

**Cause:** `.gitignore` contained a bare glob `env*`, added by an earlier
security audit to block the leaked secrets file `env`. That glob also matches
`environment.py`, so two real source modules were silently untracked. The
published repository was therefore broken for every cloner, while working
perfectly for the author — the classic "works on my machine" failure.

**Fix:** anchored the ignore rules so they match only the intended secrets:

```gitignore
/env
/env/
/.env
/.env.*
/env.*
```

**Verification:**

| Check | Result |
| --- | --- |
| `git check-ignore env` | still ignored (secret protected) |
| `git check-ignore .env` | still ignored (secret protected) |
| `git check-ignore engine/agent_runtime/environment.py` | no longer ignored |
| `git check-ignore engine/claude_code/environment.py` | no longer ignored |

Both modules are now tracked.

## 2. `.pyc`-only imports

Searched for first-party imports satisfied only by cached bytecode. The two
modules above were the only instances; both are now present as source. All
`__pycache__` directories were removed from the working tree and are ignored.

## 3. Test collection

`pytest` at the repository root previously **aborted collection entirely**.

**Cause:** no pytest configuration existed, so collection defaulted to the
current directory and reached `scripts/test_pipeline_startup.py`, a manual
diagnostic that runs work at import and calls `sys.exit(1)` (line 23) when
openWakeWord is unavailable. `sys.exit` during collection is an internal error,
not a skip or failure.

**Fix:** added `pytest.ini` with `testpaths = tests`, `norecursedirs` for
`scripts/`, `archive/`, `agent/`, `datasets/` and other non-test trees, plus
markers (`windows`, `audio`, `browser`, `integration`).

**Verification:** bare `pytest` now collects **3428 tests** with no error.

## 4. Headless safety

Pure unit tests previously could not import `engine.control` on a machine
without a display.

**Cause:** `engine/control/__init__.py` imported and registered all four
controllers at import time, and `chrome_controller` imports `pyautogui`. The
existing guard was `except ImportError`, but `pyautogui` raises **display
errors** on a headless box, not `ImportError` — so the guard never fired and
one missing display made the whole package unimportable, including pure policy
code such as `ActionGate`.

**Fix:** broadened the guards in `chrome_controller.py`,
`desktop_controller.py` and `window_controller.py`, and made registration
degrade per-controller instead of aborting the package import.

**Verification:** `engine.control` imports successfully and still registers
**23 controls**; `test_action_gate` + `test_chrome_controller` +
`test_file_controller` = **77 passed**.

## 5. Private and generated data removed from distribution

The repository was publishing personal data. Untracked (local copies kept):

| Path | Contents | Files |
| --- | --- | --- |
| `hey_nexi_clips/` | personal wake-word voice recordings | 270 |
| `datasets/` | generated clap/wake training audio | 701 |
| `artifacts/` | most recent ASR captures (private speech) | 18 |
| `trainingData.yml` | LBPH **face-recognition biometric model** (17 MB) | 1 |
| `jarvis.db`, `nexai.db`, `nexi.db` | local databases | 3 |
| `ai-team-agents-v2.zip` | nested archive | 1 |

Tracked file count: **3608 → 2612** (996 removed).

> **Unresolved:** `git rm --cached` stops future distribution but does **not**
> erase these files from existing git history. They remain retrievable from
> earlier commits. See `STAGE_1_BLOCKERS.md`.

## 6. Machine-specific configuration

`.mcp.json` was tracked containing absolute paths (`E:/ai-agnet-nexi`,
`D:\hermes\bin\uvx.exe`), so it could not work on another machine. It *is* read
at runtime by `engine/agent_runtime/mcp_preflight.py`, so it was not deleted:
it is now untracked and ignored, with a portable `.mcp.json.example` committed
that substitutes `${NEXI_ROOT}` and resolves `uvx` from `PATH`. Verified: zero
absolute paths and no secrets in the example.

## 7. Removed misleading packaging

`Dockerfile` and `.dockerignore` were removed. The Dockerfile was a LiveKit
agent-worker template invoking `python run.py download-files` and
`run.py start` — arguments this project's `run.py` does not accept — on a Linux
slim base that cannot provide pywin32, SAPI or UI Automation. It could never
have built a working image.

## 8. Documentation alignment

`README.md` described ten top-level packages (`core/`, `intent/`, `skills/`,
`wake/`, `workflow/`, `ui/`, `www/` …) that no longer exist. Replaced with the
real `engine/` + `www_mark/` layout.

---

## Changed files (this stage)

```
.gitignore                        anchored env rules; ignore private data
pytest.ini                        NEW - testpaths, norecursedirs, markers
pyproject.toml                    NEW - dependency groups
requirements.txt                  +7 undeclared runtime dependencies
.mcp.json.example                 NEW - portable MCP config
engine/agent_runtime/environment.py    RESTORED to git
engine/claude_code/environment.py      RESTORED to git
engine/control/__init__.py        per-controller degradation
engine/control/chrome_controller.py    widened import guard
engine/control/desktop_controller.py   widened import guard
engine/control/window_controller.py    widened import guard
engine/interrupt_controller.py    NEW interrupt_and_wait()
engine/nexi_wake_controller.py    interrupt race fixed (x2)
engine/command.py                 interrupt race fixed (x2)
engine/ui_adapter.py              real system metrics
main.py                           ui_get_metrics bridge
run.py                            face auth opt-in; finite timeout; ROI fix
www_mark/main.js                  real metrics; ordered state reducer
README.md                         structure corrected
Dockerfile, .dockerignore         REMOVED
```
