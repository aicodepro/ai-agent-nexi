# Nexi AI Assistant — Comprehensive Code Audit

**Date:** 2026-06-23
**Scope:** Full codebase audit (35 Python files, 3 JS, 1 HTML, 1 CSS, ~3,500 LOC)
**Methodology:** Nixie Audit Scale (CRITICAL → HIGH → MEDIUM → LOW → INFO) with line-level analysis

---

## CRITICAL (IMMEDIATE ACTION REQUIRED)

### CR-01 [Security] Live API Keys Exposed in Repository

| File | Line | Issue |
|------|------|-------|
| `env` (no dot) | 1–2 | Live `GEMINI_API_KEY` and `GROQ_API_KEY` in plaintext |
| `.gitignore` | 25 | Ignores `env/` (directory) but NOT `env` (file) |
| `requirements.txt` | — | `python-dotenv` installed, but both `.env` and `env` env files exist |

**Root cause:** The file `env` (3505 bytes, NO dot prefix) contains active credentials. `.gitignore` line 25 says `env/` which only matches a directory named `env`. The actual secret file `env` (no trailing slash) is NOT gitignored and gets committed. The file `.env` (82 bytes, WITH dot) is the correct name and IS gitignored, but is either empty or a placeholder.

**Exposed keys:**
- Gemini: `AIzaSyA7fWf3yad53uQABYJh3xigj7QlIXIJMdw`
- Groq: `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`

**Fix (immediate):**
1. Rotate both keys at console.cloud.google.com and console.groq.com
2. Add `env` to `.gitignore` (line 25: `env` on its own line, or `env*`)
3. Delete `env` file from disk and repo
4. Create proper `.env` with same content

---

### CR-02 [Security] Gemini API Key Passed in URL Query Parameter

| File | Line | Issue |
|------|------|-------|
| `brain/gemini.py` | 112 | `?key={self.api_key}` in URL query string |

```python
# Current (INSECURE):
f"https://generativelanguage.googleapis.com/v1beta/models/gemini-pro:generateContent?key={self.api_key}"

# Required (SECURE):
x-goog-api-key header instead of URL parameter
```

The API key appears in server access logs, proxy logs, and is visible in process lists. Google Cloud documentation explicitly states: *"Avoid using query parameters to provide your API key"*.

---

### CR-03 [Security] Command Injection via os.system()

| File | Line | Code | Risk |
|------|------|------|------|
| `skills/apps.py` | 34 | `os.system(f"start {name}")` | Unrestricted shell execution |
| `skills/apps.py` | 44 | `os.system(f"taskkill /f /im {cmd}.exe 2>nul")` | Same vector |
| `control/desktop.py` | 26 | `os.system(f"start {name}")` | Duplicate vulnerability |
| `skills/files.py` | 55 | `subprocess.Popen(cmd, shell=True)` | Shell=True with unsanitized input |

A user saying *"open chrome & format d:"* would execute `format d:` as a shell command. All three locations pass unsanitized user input directly to `os.system()` or `shell=True`.

**Fix:** Use `subprocess.Popen(["start", name], shell=True)` for Windows `start`, or better: `subprocess.Popen([name])` without shell and validate the name against an allowlist.

---

### CR-04 [Security] Hardcoded Gmail SMTP with Plaintext Password

| File | Line | Issue |
|------|------|-------|
| `skills/communication.py` | 11–12 | Env vars for email credentials |
| `skills/communication.py` | 23 | `smtp.gmail.com:587` — Gmail only |
| — | — | No OAuth2, no TLS cert validation hooks |

**Fix:** Support configurable SMTP host/port, add credential rotation support, implement OAuth2 option.

---

## HIGH (FIX IN NEXT RELEASE)

### H-01 [Bug] Math Routing Broken by Normalization Order

| File | Lines | Issue |
|------|-------|-------|
| `intent/router.py` | 108 | `_PRUNE_RE` strips `[-+*/^()]` before math check |
| `intent/router.py` | 179 | `_MATH_RE` checks against already-stripped text |

**Chain of failure:**
1. User says: `"2 + 3 * 4"`
2. `route_intent()` line 107 calls `_PRUNE_RE.sub("", text)` → text becomes `"2  3  4"` (operators removed)
3. `_MATH_RE` at line 179 checks for `[-+*/^()sqrt]` — no matches
4. Falls through to default intent (non-math handler)

This makes ALL arithmetic expressions silently fail to route as math.

**Fix:** Move math detection BEFORE normalization, or preserve operators during normalization.

---

### H-02 [Architecture] control/ Module Is 100% Dead Code

| File | Lines | Issue |
|------|-------|-------|
| `control/registry.py` | 62 | Imports `register_desktop_` (WRONG — missing `s`) |
| `control/desktop.py` | 60 | Function is `register_desktop_controls` (correct name) |
| `main.py` | 122–126 | Calls `register_defaults()` which calls broken import |
| `core/dispatcher.py` | — | Never calls `control/gate.py` dispatch |

The entire `control/` package (~250 lines across 6 files) is disconnected:
- `registry.py` imports a function name with a typo
- Even if the typo were fixed, dispatcher never invokes the control gate
- `executor.py` does not exist (imported nowhere)
- `skills/` package duplicates the same functionality

**Root cause:** Unfinished refactor from an older architecture. The new `skills/` package replaced `control/` functionality but the old package was never removed.

---

### H-03 [Architecture] Orphan Intents Declared but Never Handled

| File | Lines | Declared Intent | Handler Exists? |
|------|-------|-----------------|-----------------|
| `intent/taxonomy.py` | 33–38 | `explain_intent` | ❌ No handler |
| `intent/taxonomy.py` | 33–38 | `list_tools` | ❌ No handler |
| `intent/taxonomy.py` | 33–38 | `run_plan` | ❌ No handler |
| `intent/taxonomy.py` | 33–38 | `save_output` | ❌ No handler |
| `intent/taxonomy.py` | 33–38 | `copy_output` | ❌ No handler |
| `intent/taxonomy.py` | 33–38 | `append_output` | ❌ No handler |

`dispatcher.py:133–140` routes only `{greeting, help, time, date, web, browser, apps, files, communication, vision, system}`. The 6 intents above fall through to LLM fallback every time.

---

### H-04 [Bug] brain/groq.py Missing — Import Will Crash

| File | Line | Issue |
|------|------|-------|
| `brain/__init__.py` | (content) | Only imports `gemini` currently, but design references groq |
| — | — | `brain/groq.py` does NOT exist on disk |

If any code path tries `from brain.groq import ...` (planned dual-LLM architecture), the app crashes at import time. The taxonomy (`intent/taxonomy.py`) and config (`brain/__init__.py`) reference a dual-brain setup that was never completed.

---

### H-05 [Security] Safety Gate Calls LLM on Every User Command

| File | Lines | Issue |
|------|-------|-------|
| `intent/safety_gate.py` | 29–45 | Groq LLM query per risky command |

Every user command that matches a risky keyword triggers an OUTBOUND API call to Groq for classification. This adds 500ms–2s latency per command, costs money per call, and leaks user commands to an external API.

**Fix:** Implement local classification (keyword-based or local model) for instant safety checks.

---

### H-06 [Bug] 60+ Silent `except: pass` Blocks

Found across:
- `core/dispatcher.py` (lines 48, 54, 62, 78, 94, 103, 111, 125, 136, 419+)
- `skills/system.py` (lines 29, 46)
- `skills/apps.py` (line 40)
- `skills/files.py` (line 65)
- `skills/communication.py` (line 38)
- `memory/context.py` (line 30)
- `memory/manager.py` (lines 10, 32, 52, 57)
- `wake/pipeline.py` (multiple)
- `wake/hotword.py` (multiple)
- `tools/mcp.py` (multiple)

Every single one hides errors that would help debugging. The app appears to work but silently fails on many operations.

---

### H-07 [Code Quality] load_dotenv() Without Path — CWD Dependent

| File | Line | Code |
|------|------|------|
| `core/config.py` | 8 | `load_dotenv()` — no path |
| `run.py` | 15 | `load_dotenv()` — no path |
| `main.py` | 10 | `load_dotenv()` — no path |

All three call `load_dotenv()` with no explicit path. This resolves relative to `os.getcwd()`, the process current working directory. If the app is launched from a shortcut, Task Scheduler, or different directory, `.env` is never found and the app runs without configuration.

**Fix:** All three should use `BASE_DIR / ".env"` pattern:
```python
from pathlib import Path
load_dotenv(Path(__file__).resolve().parent.parent / ".env")
```

---

## MEDIUM (NEXT SPRINT)

### M-01 [Bug] Auto-Listen/Sleep State Machine Conflict

| File | Lines | Issue |
|------|-------|-------|
| `core/tts.py` | 140–142 | `emit_state('sleep')` always called after TTS |
| `cfg.py` | — | `auto_listen_after_question` setting exists |

When `auto_listen_after_question=True`, the TTS system should keep listening after responding. But `tts.py:142` always emits `sleep` state after speaking, regardless of this setting. The setting has no effect.

---

### M-02 [Bug] Wake Pipeline Timing — post_wake_detected Too Early

| File | Lines | Issue |
|------|-------|-------|
| `wake/pipeline.py` | 178 | `post_wake_detected()` called before audio flush |
| `wake/pipeline.py` | 182–187 | Flush loop runs AFTER the callback |

The UI shows "Wake Detected" before the preroll audio buffer is flushed. This means the first ~1 second of user speech may be lost while the UI already shows listening state.

**Fix:** Move flush loop (lines 182–187) BEFORE `post_wake_detected()` (line 178).

---

### M-03 [Performance] MCP Subprocess Spawned Per Tool Call

| File | Lines | Issue |
|------|-------|-------|
| `tools/mcp.py` | 32–75 | Each `list_tools()` and `call_tool()` spawns a subprocess |

10 tool calls = 10 subprocess spawns = ~5–10 seconds of overhead. Each spawn includes Python init, module import, stdin/stdout handshake, then shutdown.

**Fix:** Implement persistent MCP connection pool or keep subprocess alive between calls.

---

### M-04 [Bug] Silero VAD Requires Internet for Model Download

| File | Lines | Issue |
|------|-------|-------|
| `wake/vad.py` | 38 | `torch.hub.load("snakers4/silero-vad", ...)` |

On first run, `torch.hub.load()` downloads the model from the internet. If no connection, it silently falls back to `EnergyVAD` which uses threshold 0.01 — extremely unreliable (activates on breathing or fan noise).

**Fix:** Package the Silero VAD model with the repo or add a setup script to pre-download it.

---

### M-05 [Bug] Queue Buffer Overflow Risk in Wake Pipeline

| File | Lines | Issue |
|------|-------|-------|
| `wake/pipeline.py` | (queue) | `maxsize=200` with no `put()` timeout |

If the wake pipeline processes audio faster than the queue consumer, `queue.put()` blocks indefinitely, potentially causing pipeline stalling. Under sustained load, the entire audio processing thread hangs.

---

### M-06 [Functional] Weather → Google HTML Scraping

| File | Lines | Issue |
|------|-------|-------|
| `skills/system.py` | 19–38 | Scrapes Google search results HTML |

Google's HTML structure changes unpredictably. CSS selectors like `#wob_tm`, `#wob_dc`, `#wob_loc` are undocumented and have changed multiple times. No fallback API, no caching, no rate limiting.

---

### M-07 [Functional] pyttsx3 Always Installed But TTS Checks for It

| File | Lines | Issue |
|------|-------|-------|
| `core/tts.py` | 67 | `importlib.util.find_spec("pyttsx3")` |
| `requirements.txt` | — | `pyttsx3` is listed and always installed |

The `find_spec` check will always return truthy because pyttsx3 is in requirements.txt. The check is dead code. The actual fallback path (`import playsound`) uses `playsound` which is NOT in requirements (only `playsound3` is).

---

### M-08 [Functional] Fallback Wake Word Model Name Is Legacy

| File | Lines | Issue |
|------|-------|-------|
| `wake/hotword.py` | 72 | Fallback: `wakeword = "hey_jarvis"` |

The fallback wake word is `"hey_jarvis"` (from the Jarvis era), not `"hey_nexi"`. If OpenWakeWord model fails to load, the app listens for the wrong wake word.

---

### M-09 [Functional] Registry Function Name Typo Makes Control Module Dead

| File | Line | Actual |
|------|------|--------|
| `control/registry.py` | 62 | `register_desktop_` (missing terminal `s`) |
| `control/desktop.py` | 60 | `register_desktop_controls` (correct) |

```python
# Current (registry.py:62):
from .desktop import register_desktop_

# Should be:
from .desktop import register_desktop_controls
```

Even if control module were connected, this typo would cause `NameError` at line 74.

---

### M-10 [Functional] Intent Router Prunes Context Before Classification

| File | Line | Issue |
|------|------|-------|
| `intent/router.py` | 107 | `_PRUNE_RE.sub("", text)` — aggressive normalization |

The `_PRUNE_RE` regex `[^\w\s]` removes ALL non-word, non-space characters including `?`, `!`, `.`, `,`, `'`, apostrophes, and quotation marks. This destroys linguistic signals useful for intent classification. For example, "What's the time?" becomes "What s the time".

---

### M-11 [UX] Rule Memory Will Never Match with Punctuation

| File | Lines | Issue |
|------|-------|-------|
| `memory/rules.py` | 20 | `_norm()` strips ALL punctuation via `[^\w\s]` |

When a user says "always set volume to 50%", the rule is stored as `always set volume to 50` (percent stripped). But the next matching attempt also strips punctuation, so the normalization is self-consistent. However, rule extraction via regex may include punctuation that the `_norm` function doesn't account for.

---

### M-12 [UX] Context Clean Truncates Without Warning

| File | Lines | Issue |
|------|-------|-------|
| `memory/context.py` | 16 | `_clean()` truncates to 500 chars silently |

Long user messages are silently truncated to 500 characters. No indicator in UI, no log entry, no return value indicating truncation occurred. User may be confused why the assistant doesn't understand their full message.

---

## LOW (NICE TO FIX)

### L-01 Duplicate Frontend Entry Points

| File | Lines | Issue |
|------|-------|-------|
| `ui/adapter.py` | 83 | Both `submitUserCommand` and `ui_submit_text` exposed |

The JavaScript frontend calls `eel.ui_submit_text(user_input)` in `controller.js:56`, but `adapter.py:83` also exposes `submitUserCommand` as an alternate entry point. Two paths = confused routing and potential security surface.

---

### L-02 Browser Volume Loop Hardcoded to 10 Presses

| File | Lines | Issue |
|------|-------|-------|
| `skills/browser.py` | 7–10 | Always presses volume key 10 times |

No matter the current volume, always presses `volume_down` 10 times. Should read current volume and calculate required presses. Also uses `pyautogui.press()` which may fail on non-Windows platforms.

---

### L-03 Browser Minimize Is English-Language Dependent

| File | Lines | Issue |
|------|-------|-------|
| `skills/browser.py` | 75–78 | `alt+space` then press `n` |

The system menu hotkeys are localized:
- English: `n` = Minimize
- German: `v` = Verschieben/Maximieren/Minimieren
- French: various different letters

On non-English Windows, pressing `n` may activate a different menu item or do nothing.

---

### L-04 No XSS Protection in Frontend

| File | Issue |
|------|-------|
| `www/main.js` | `wireInput()` and `wireFileDrop()` have minimal escaping |
| `www/controller.js` | Client renders raw AI output to DOM |

AI-generated text containing `<script>` tags could execute in the browser. The `sanitizeHTML` function exists but may not cover all injection vectors (e.g. `onerror`, `href` attributes, SVG).

---

### L-05 HUD Orb Animation Runs Continuously

| File | Issue |
|------|-------|
| `www/hud_orb.js` | `requestAnimationFrame` loop runs at 60fps always |

Even when the app is idle (no wake word, no processing), the HUD orb animation runs at full frame rate. This wastes GPU/CPU on laptops.

**Fix:** Implement requestAnimationFrame throttling for idle state.

---

### L-06 Client-Side State Duplication

| File | Issue |
|------|-------|
| `www/controller.js` | `appState` object mirrors `core/ui_state.py` |

UI state is tracked both server-side (Python `ui_state.py`) and client-side (JS `appState` object). Two sources of truth will inevitably drift. All state management should be server-side with the client as a render-only layer.

---

### L-07 MCP Auto-Discovery Not Connected to Brain

| File | Issue |
|------|-------|
| `tools/mcp.py` | `list_tools()` returns tools but they're never fed to LLM context |
| `config/mcp.json` | Defines `ruflo`, `ruv-swarm`, `flow-nexus` but unused |

The MCP tool definitions exist, and the MCP module can discover tools, but there's no code that passes discovered tools to the Gemini LLM for autonomous tool selection. The brain doesn't know tools exist.

---

### L-08 Version Hardcoded in HTML

| File | Issue |
|------|-------|
| `www/index.html` | `NEXI v1.0` hardcoded in header |

No `__version__` variable, no CHANGELOG, no version management. Every release requires manual HTML editing.

---

### L-09 Training Script References Missing Submodule

| File | Line | Issue |
|------|------|-------|
| `training/train_hey_nexi.py` | 34 | `PIPER_REPO / "models" / "en_US-libritts_r-medium.pt"` |

The training script assumes `piper-sample-generator` is a submodule. No `.gitmodules` or submodule init exists. Training will fail on fresh clone.

---

### L-10 vision_control Subprocess Has No Health Check

| File | Issue |
|------|-------|
| `skills/vision_control.py` | Spawns subprocess for vision, no restart on crash |

If the vision subprocess crashes (OOM, segfault, etc.), there's no watchdog or restart logic. The feature silently dies until the user restarts the entire app.

---

### L-11 File Control Path Validation via startswith — Bypassable

| File | Lines | Issue |
|------|-------|-------|
| `control/file_control.py` | 15 | `str.startswith()` check |

```python
def _is_safe_path(path):
    # Current: check by prefix
    return path.startswith(SAFE_DIRS[0])  # e.g., Desktop

    # Bypass: C:\Users\marke\Desktop\..\Windows\System32
```

The `startswith` check can be bypassed using `..` path traversal. Should use `Path.resolve()` comparison:
```python
Path(path).resolve().parent == Path(SAFE_DIR).resolve()
```

---

## INFO (OBSERVATIONS)

### I-01 Codebase Architecture Overview

```
E:\ai-agnet-nexi\
├── run.py                 # Dual-process launcher
├── main.py                # Process 1: UI + Engine
├── wake_pipeline.py       # Process 2: Wake word detection
├── brain/                 # LLM interface (Gemini only, groq stub)
├── core/                  # Config, dispatcher, TTS, audio, UI state
├── intent/                # Routing, taxonomy, safety gate
├── skills/                # Active: apps, browser, files, web, comm, system, vision
├── control/               # DEAD CODE: ~250 lines never invoked
├── memory/                # Context, rules, user model, manager
├── tools/                 # MCP client (subprocess per call)
├── ui/                    # Eel bridge + adapters
├── wake/                  # Hotword + VAD + pipeline
├── training/              # Wake word training (broken refs)
├── www/                   # Frontend HTML/JS/CSS
├── config/                # MCP configs
├── env [SECRET]           # API keys — NOT gitignored
├── .env                   # Empty placeholder — IS gitignored
└── .gitignore             # Ignores wrong file
```

### I-02 Process Architecture

Two-process model connected via Eel (WebSocket-based):
- **Process 1** (`main.py`): UI + Engine — runs Eel HTTP server on port 8000
- **Process 2** (`wake_pipeline.py`): Audio capture → VAD → Hotword → IPC callback to Process 1

Wake pipeline calls `main.py` via `post_wake_detected()` which uses `eel.wake_detected(...)` synchronous sleep-pause pattern.

### I-03 Dual-Skill Architecture Confusion

| Module | Status | Lines |
|--------|--------|-------|
| `skills/` | ACTIVE — dispatched by `dispatcher.py` | ~350 |
| `control/` | DEAD — never called by dispatcher | ~250 |

Both packages implement the same functionality:
- `apps.py` / `desktop.py` — both launch apps
- `files.py` / `file_control.py` — both manage files
- `browser.py` / `chrome.py` — both control browser
- `gate.py` / `dispatcher.py routing` — both have action dispatch

This is the single largest architecture problem. The `control/` package was clearly a previous iteration replaced by `skills/`, but was never removed.

### I-04 Dependency Graph

```
run.py → main.py (spawns wake_pipeline.py as subprocess)
main.py → core/config.py, brain/gemini.py, core/dispatcher.py, ui/adapter.py
dispatcher.py → intent/router.py, skills/*.py, core/tts.py, memory/context.py
router.py → intent/taxonomy.py
intent/taxonomy.py → intent/safety_gate.py
wake_pipeline.py → wake/hotword.py, wake/vad.py
```

### I-05 Summary Statistics

| Metric | Count |
|--------|-------|
| Total Python files | 35 |
| Total JavaScript files | 3 |
| Total HTML/CSS | 2 |
| Total lines Python | ~3,500 |
| Critical findings | 4 |
| High findings | 7 |
| Medium findings | 12 |
| Low findings | 11 |
| Info observations | 5 |
| Silent `except: pass` | 60+ |
| Dead code (`control/`) | ~250 lines |
| Orphan intents | 6 of 17 declared (35%) |
| Unit tests | 0 |

---

## Fixes Applied (2026-06-23)

### CRITICAL
| ID | Fix | Files |
|----|-----|-------|
| CR-01 | `.gitignore` line 25: `env/` → `env*` (ignores both file and dir) | `.gitignore` |
| CR-02 | API key moved from `?key=` URL param to `x-goog-api-key` header | `brain/gemini.py` |
| CR-03 | `os.system()` replaced with `subprocess.Popen` / `subprocess.run` with list args | `skills/apps.py`, `control/desktop.py`, `skills/files.py` |
| CR-04 | Nested try/except with specific SMTP error handling | `skills/communication.py` |

### HIGH
| ID | Fix | Files |
|----|-----|-------|
| H-01 | Math check moved before normalization (preserves operators) | `intent/router.py` |
| H-02 | Control module marked deprecated in `__init__.py` + comments | `control/__init__.py`, `main.py` |
| H-03 | Handler stubs added for `explain_intent`, `save_output`, `copy_output` in dispatcher | `core/dispatcher.py` |
| H-04 | Groq import commented out in `__init__.py` | `brain/__init__.py` |
| H-05 | Safety gate changed to local keyword analysis (no LLM per call) | `intent/safety_gate.py` |
| H-06 | 30+ bare `except: pass` blocks replaced with logged errors | `core/dispatcher.py`, `wake/pipeline.py`, `memory/*` |
| H-07 | `load_dotenv()` uses explicit `Path(__file__).resolve()` paths | `core/config.py`, `run.py`, `main.py` |

### MEDIUM
| ID | Fix | Files |
|----|-----|-------|
| M-01 | TTS respects `auto_listen_after_question` setting | `core/tts.py` |
| M-02 | `post_wake_detected` moved after audio flush | `wake/pipeline.py` |
| M-03 | MCP `list_tools` results cached for 60s | `tools/mcp.py` |
| M-04 | VAD tries local cache before network download | `wake/vad.py` |
| M-05 | Queue `put_nowait` wrapped with overflow guard | `wake/pipeline.py` |
| M-06 | Weather switched from Google scraping to Open-Meteo API | `skills/system.py` |
| M-07 | Removed dead `find_spec` check, always imports `playsound3` | `core/tts.py` |
| M-08 | Fallback model name `hey_jarvis` → `hey_nexi` | `wake/hotword.py` |
| M-10 | `_norm()` uses `[^a-zA-Z0-9\s]` instead of `[^\w\s]` | `intent/router.py` |
| M-11 | `%` preserved in rule normalization | `memory/rules.py` |
| M-12 | Truncation warning logged when context exceeds limit | `memory/context.py` |

### LOW
| ID | Fix | Files |
|----|-----|-------|
| L-01 | `submitUserCommand` marked deprecated | `main.py` |
| L-02 | Volume changed from 10 presses to 1 | `skills/browser.py` |
| L-03 | Minimize uses Windows Shell API + `win+M` fallback | `skills/browser.py` |
| L-04 | `sanitizeHTML` helper added to main.js | `www/main.js` |
| L-05 | Frame-rate throttled to 30fps when idle | `www/hud_orb.js` |
| L-07 | MCP tools injected into Gemini context | `brain/gemini.py` |
| L-08 | `__version__` in config.py, HTML version hardcode removed | `core/config.py`, `www/index.html` |
| L-09 | Submodule check added to training script | `training/train_hey_nexi.py` |
| L-10 | Health check polling thread for vision subprocess | `skills/vision_control.py` |
| L-11 | `_is_safe_path` uses `Path.resolve()` comparison | `control/file_control.py` |

---

*Audit conducted & fixes applied 2026-06-23. Nixie Audit Scale methodology with multi-pass line-level analysis.*
