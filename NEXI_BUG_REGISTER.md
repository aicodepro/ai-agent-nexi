# Nexi AI Assistant — Unified Bug Register

**Generated:** 2026-07-24
**Source:** Synthesis of 5 parallel deep-dive audits + microphone-disconnect chain trace
**Severity Scale:** CRITICAL → HIGH → MEDIUM → LOW → INFO

---

## A. WAKE / HOTWORD / CLAP PIPELINE

### A-CR-01 — DSP Clap Speech-Rejection Accepts Short Speech as Clap
| | |
|---|---|
| **File** | `engine/dsp_clap_backend.py:201-218` |
| **Severity** | **CRITICAL** |
| **Root Cause** | The "speech rejection" gate at line 203 (`rms > rms_threshold*0.5 AND peak_ratio < peak_ratio_threshold*0.8`) **accepts short-duration speech-like events as claps** (lines 209-218), only rejecting them after 250ms of sustained energy (line 207). Short coughs, throat clears, and brief modulated sounds are classified as clap events — massive false positives. |
| **Fix** | Invert the logic: reject speech-like events unconditionally, or require a separate high-confidence clap classifier for borderline sounds. At minimum, increase the initial acceptance threshold for speech-like events. |

### A-CR-02 — Microphone Disconnect Never Detected (Silent Death)
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:1418-1430` |
| **Severity** | **CRITICAL** |
| **Root Cause** | The `sd.InputStream` callback at line 1418 **completely ignores the `status` parameter** from PortAudio. When the microphone is physically disconnected, PortAudio reports `input_overflow` or device errors via `status`, but this is discarded. No frames arrive → `_worker_loop` at line 1464 spins on `queue.Empty` forever → no error is logged → no recovery is attempted → UI is stuck on last state. The `_open_stream()` fallback at lines 1446-1451 only runs during initial `start()`, not mid-session. |
| **Fix** | Check `status` in callback; if device error detected, set `_stop_event` and signal a reconnection attempt. Add a watchdog thread that monitors queue staleness and triggers stream restart. |

### A-CR-03 — Interrupt Race Condition (Premature clear_interrupt)
| | |
|---|---|
| **File** | `engine/nexi_wake_controller.py:33-36`, `engine/interrupt_controller.py:37-41` |
| **Severity** | **CRITICAL** |
| **Root Cause** | `wake_nexi()` at `nexi_wake_controller.py:33-36` calls `request_interrupt()` then immediately `clear_interrupt()`. The TTS `engine.stop()` inside `request_interrupt()` is async — it signals stop but the speaking thread may not have finished by the time `clear_interrupt()` runs. This allows a new wake detection to proceed while the old TTS is still decaying, causing overlapping audio. |
| **Fix** | Remove the `clear_interrupt()` call from `wake_nexi()`; let the interrupt lifecycle be managed by the TTS system. Or poll `is_speaking()` in a brief retry loop before clearing. |

### A-H-01 — Threshold Mismatch: Pipeline vs HotwordEngineManager
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:99` vs `engine/hotword_engine_manager.py:54` |
| **Severity** | **HIGH** |
| **Root Cause** | Pipeline defaults to `threshold=0.35` while hotword engine manager defaults to `threshold=0.25`, even though both use env var `OPENWAKEWORD_SCORE_THRESHOLD`. If the env var is unset, the two subsystems disagree on what score counts as a detection — the manager may detect phrases the pipeline ignores. |
| **Fix** | Reconcile default value: both should default to the same number (recommend 0.35 per the pipeline comment). |

### A-H-02 — Consecutive Hits Counter Reset Before Arbitration
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:795,801,809,812-813` |
| **Severity** | **HIGH** |
| **Root Cause** | `_consecutive_hits` is reset to 0 at lines 795/801/809 when a frame fails RMS gate, voice gate, or is post-session suppressed. But the consecutive counter at line 812 is incremented BEFORE the arbitration decision at line 815. A frame that scores >= threshold but is then suppressed still gets `consecutive_hits += 1`, meaning the NEXT valid frame after suppression may fire with fewer hits than required. |
| **Fix** | Only increment `_consecutive_hits` after arbitration passes. Reset it at the same decision point. |

### A-H-03 — Orphaned Audio Stream on Error
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:1340-1343` |
| **Severity** | **HIGH** |
| **Root Cause** | If `_open_stream()` succeeds but noise calibration or scorer setup fails, `start()` returns without setting `_stop_event` or stopping the stream. The stream continues capturing audio in a zombie state with no worker consuming it. |
| **Fix** | Add a `try/finally` guard: if worker thread isn't started, close the stream. |

### A-H-04 — Hot-Path Imports Inside 50 Hz Frame Loop
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:828-831` (clap manager import/instantiation every frame) |
| **Severity** | **HIGH** |
| **Root Cause** | `from engine.clap_backend_manager import ClapBackendManager` and instantiation run inside `process_frame()` at lines 828-830. Though Python caches imports, the `ClapBackendManager()` constructor runs env-read logic every time `_clap_manager` is None (and after any exception at line 859 resets it to None). |
| **Fix** | Move manager instantiation to `__init__()` or `start()`. |

### A-H-05 — Hardcoded cooldown=False in Clap Manager Path
| | |
|---|---|
| **File** | `engine/clap_backend_manager.py` (detected via cross-ref) |
| **Severity** | **HIGH** |
| **Root Cause** | Clap backend manager passes `cooldown=False` unconditionally in some code paths, overriding the configured cooldown. |
| **Fix** | Use the configured cooldown value instead of hardcoded `False`. |

### A-M-01 — VAD_MIN_RMS Default May Be Too High
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:145` |
| **Severity** | **MEDIUM** |
| **Root Cause** | `VAD_MIN_RMS = 0.015` may reject quiet speech on less sensitive microphones. |
| **Fix** | Make adaptive: auto-calibrate from noise floor or lower default to 0.008. |

### A-M-02 — POST_WAKE_DELAY_MS Blocks Audio Queue During Wait
| | |
|---|---|
| **File** | `engine/audio_wake_pipeline.py:1160-1168` |
| **Severity** | **MEDIUM** |
| **Root Cause** | The post-wake delay drains frames from the queue in a polling loop. If the delay is long (1s), the queue may accumulate stale frames that get processed after. |
| **Fix** | Use time-based skip rather than draining: mark frames timestamp and filter in `process_frame`. |

---

## B. BRAIN / MODEL / PROVIDER SYSTEM

### B-CR-01 — Three Disconnected Model Routing Systems, None Working
| | |
|---|---|
| **File** | `engine/brain/provider_factory.py`, `engine/brain/model_client.py`, `engine/model_registry.py`, `engine/providers/` |
| **Severity** | **CRITICAL** |
| **Root Cause** | Three separate model routing infrastructures exist and are completely disconnected: (1) `brain/provider_factory.py` always returns `MockModelClient` which never calls a real API; (2) `model_registry.py` defines real model configs but is never consumed by any router; (3) `engine/providers/groq_provider.py` and `openrouter_provider.py` have real provider logic but are orphaned — nobody calls them. The result is that EVERY brain response is simulated. |
| **Fix** | Delete two of the three systems. Route the surviving system through to the actual command dispatch (`engine/features.py:chatBot()`). Wire `provider_factory` to return real providers based on config. |

### B-H-01 — Provider Fallback Chain Never Exercised
| | |
|---|---|
| **File** | `engine/brain/provider_registry.py` |
| **Severity** | **HIGH** |
| **Root Cause** | Provider registry defines fallback order (DeepSeek → GLM → Qwen → etc.) but this chain is never invoked — the registry is not imported by any router. |
| **Fix** | Either wire registry into `chatBot()` or remove it as dead code. |

### B-H-02 — Token Counting Mismatch / Context Window Issues
| | |
|---|---|
| **File** | Various provider implementations |
| **Severity** | **HIGH** |
| **Root Cause** | Different providers use different tokenization (tiktoken vs huggingface vs provider-specific). The brain has no unified token counting, so context window management is unreliable — prompts may be silently truncated or exceed limits. |
| **Fix** | Implement `count_tokens(text, model)` using provider-appropriate tokenizer in a single module. |

### B-M-01 — Missing API Error Handling
| | |
|---|---|
| **File** | `engine/providers/groq_provider.py` |
| **Severity** | **MEDIUM** |
| **Root Cause** | No retry logic, no rate-limit handling, no timeout management for Groq/OpenRouter API calls. A 429 or 503 silently returns empty response. |
| **Fix** | Add exponential backoff retry, timeout config, and meaningful error propagation. |

---

## C. MEMORY / CONTEXT SYSTEM

### C-CR-01 — Diverging redact_sensitive() Implementations
| | |
|---|---|
| **File** | `engine/memory_safety.py` vs `engine/memory/memory_redaction.py` |
| **Severity** | **CRITICAL** |
| **Root Cause** | Two independent `redact_sensitive()` functions will inevitably diverge as one is updated and the other is not. The memory system uses `memory_redaction.py` while the general safety module uses `memory_safety.py`. If patterns are updated in one but not the other, sensitive data may leak through the unpatched version. |
| **Fix** | Consolidate: delete one and have the other import the canonical implementation. |

### C-CR-02 — LocalMemoryStore Reads Entire JSON File on Every Operation
| | |
|---|---|
| **File** | `engine/memory/local_memory.py` |
| **Severity** | **CRITICAL** |
| **Root Cause** | Every read/write operation loads the entire JSON file into memory, modifies the dict in-place, and writes the entire file back. With a 5MB+ memory file (conversations, learned facts), each write takes O(n) serialization and disk I/O. Under concurrent access, this causes race conditions and data loss. |
| **Fix** | Use SQLite or an append-only log structure for persistence. At minimum, add a file lock and lazy write-back. |

### C-H-01 — No Thread Safety in Shared Memory Stores
| | |
|---|---|
| **File** | `engine/memory/` (multiple files) |
| **Severity** | **HIGH** |
| **Root Cause** | `LocalMemoryStore` and related classes are accessed from wake pipeline thread and UI thread simultaneously with no locks. Concurrent writes cause lost updates and inconsistent reads. |
| **Fix** | Add `threading.Lock` (or `RLock`) to all shared memory operations. |

### C-M-01 — Unbounded Storage Growth
| | |
|---|---|
| **File** | `engine/memory/` |
| **Severity** | **MEDIUM** |
| **Root Cause** | No size limit, TTL-based expiry, or pruning mechanism. Memory file grows indefinitely with every conversation. |
| **Fix** | Implement LRU eviction, TTL-based expiry, and size cap (configurable). |

### C-M-02 — Incorrect Expiry/Cleanup Logic
| | |
|---|---|
| **File** | `engine/memory/local_memory.py` |
| **Severity** | **MEDIUM** |
| **Root Cause** | Expiry check only runs on read, not on write; stale entries accumulate until accessed. |
| **Fix** | Run periodic cleanup in background thread or on every N writes. |

---

## D. CONTROL / UI / BRIDGE

### D-CR-01 — Runtime Bridge State Sync Race
| | |
|---|---|
| **File** | `engine/runtime_bridge.py` |
| **Severity** | **CRITICAL** |
| **Root Cause** | Status events (wake_detected, listening, recognizing, thinking, saying, sleeping) are sent asynchronously via `command_queue`. If the bridge process is slow (e.g., during TTS), events can arrive out of order — a `sleeping` may arrive before `listening_started`. |
| **Fix** | Sequence-number all state transitions; discard stale events by sequence comparison. |

### D-H-01 — Eel Bridge Function Vulnerabilities
| | |
|---|---|
| **File** | `ui/adapter.py` and related |
| **Severity** | **HIGH** |
| **Root Cause** | `eel.expose` functions accept arbitrary string input from JS without sanitization. A crafted JS call could inject commands or manipulate internal state. |
| **Fix** | Add input validation to all Eel-exposed functions (type checks, length limits, allowlists). |

### D-H-02 — Desktop Controller Permission Escalation
| | |
|---|---|
| **File** | `engine/control/desktop.py` |
| **Severity** | **HIGH** |
| **Root Cause** | Desktop controller commands bypass the safety gate for certain actions. `start` and `taskkill` operations proceed without risk assessment. |
| **Fix** | Route all desktop control through the safety verifier. |

### D-M-01 — Canonical UI State Order Enforced Server-Side Incorrectly
| | |
|---|---|
| **File** | `engine/ui_state_manager.py` |
| **Severity** | **MEDIUM** |
| **Root Cause** | The state machine maps backend events to canonical states (SLEEPING → ONLINE → LISTENING → RECOGNISING → THINKING → SAYING → SLEEPING), but `wake_detected` is mapped to `ONLINE` while the JS client expects `LISTENING` immediately. The brief `ONLINE` state causes a visual flicker. |
| **Fix** | Either collapse `ONLINE` into `LISTENING` on the client side, or add a smooth transition. |

---

## E. MICROPHONE DISCONNECT CHAIN (TRACED)

### Full Chain: Mic Disconnect → Hotword Stop → UI Death

```
Physical mic disconnect
        │
        ▼
sd.InputStream callback (line 1418) receives PortAudio error in `status` param
        │
        ▼
status is COMPLETELY IGNORED (line 1418: `def _callback(indata, frames, time_info, status):`)
        │
        ▼
No more frames arrive → `_frame_queue.get(timeout=0.2)` at line 1464 times out → `queue.Empty`
        │
        ▼
Worker loop spins forever on `queue.Empty` → `continue` (line 1466) — NO error, NO recovery
        │
        ▼
Hotword detection silently dead → no wake events → no status updates → UI frozen on last state
        │
        ▼
User sees no error, no indication anything is wrong — app appears to just "not respond"
```

**Fix required:**
1. **Line 1418**: Check `status` for `sounddevice.PortAudioError` or non-None status flags
2. **Lines 1464-1466**: Add frame-starvation watchdog — if no frames for N seconds, attempt stream restart
3. **New**: `_recover_stream()` method that closes old stream, re-runs `_open_stream()`, and re-attaches
4. **New**: UI notification on mic failure so user knows what happened

---

## F. CONFIGURATION / REPO CLEANUP

### F-CR-01 — .mcp.json Points Filesystem/SQLite to Wrong Repo
| | |
|---|---|
| **File** | `.mcp.json:13,90` |
| **Severity** | **CRITICAL** |
| **Root Cause** | `filesystem` MCP at line 13 uses path `E:/jarvis-main` and `sqlite` MCP at line 90 uses `E:/jarvis-main/jarvis.db`. Both should point to `E:/ai-agnet-nexi`. |
| **Fix** | Update paths to `E:/ai-agnet-nexi`. |

### F-CR-02 — `env` File with Live API Keys NOT Gitignored
| | |
|---|---|
| **File** | `env` (no dot), `.gitignore:25` |
| **Severity** | **CRITICAL** |
| **Root Cause** | Already identified and partially fixed (`.gitignore` updated per audit.md). Verify `env` file has been rotated/replaced. |
| **Fix** | Verify keys rotated, `env` file deleted, `.gitignore` covers `env*` pattern. |

### F-H-01 — AGENTS.md Contains Jarvis-Specific Instructions
| | |
|---|---|
| **File** | `AGENTS.md` |
| **Severity** | **HIGH** |
| **Root Cause** | References `E:\jarvis-main`, Jarvis wake pipeline, Jarvis test commands, Jarvis-specific architecture. This is the Nexi repo — AGENTS.md should describe Nexi. |
| **Fix** | Rewrite AGENTS.md for Nexi project context. |

### F-H-02 — CLAUDE.md Is Empty Skeleton
| | |
|---|---|
| **File** | `CLAUDE.md` |
| **Severity** | **HIGH** |
| **Root Cause** | 11-line auto-generated placeholder with no project context. |
| **Fix** | Populate with Nexi project facts, setup commands, and architecture notes. |

---

## G. TEST SUITE

### G-CR-01 — Brain/Provider Tests Are Testing Mock Responses, Not Reality
| | |
|---|---|
| **File** | `tests/` |
| **Severity** | **CRITICAL** |
| **Root Cause** | Tests pass against `MockModelClient` which returns canned responses. Real providers (Groq, OpenRouter) are never integration-tested. The test suite passing is meaningless for actual functionality. |
| **Fix** | Add integration tests (opt-in with env var) that call real providers, and rework unit tests to validate failure handling. |

### G-H-01 — Wake Pipeline Tests Don't Test Stream Disconnect
| | |
|---|---|
| **File** | `tests/` |
| **Severity** | **HIGH** |
| **Root Cause** | No test verifies behavior when microphone stream stops producing data. The disconnect scenario (A-CR-02) has zero coverage. |
| **Fix** | Add test that simulates stream stoppage and verifies watchdog/recovery logic. |

---

## Summary by Severity

| Severity | Count | Key Areas |
|----------|-------|-----------|
| **CRITICAL** | 12 | DSP false positives, mic silent death, interrupt race, disconnected brain routing, diverging redact, JSON file per-op, .mcp.json wrong repo, API keys, state sync race, test coverage gap |
| **HIGH** | 13 | Threshold mismatch, consecutive hits reset, orphaned stream, hot-path imports, Eel vulnerabilities, desktop escalation, provider fallback, token counting, thread safety, AGENTS.md, CLAUDE.md, mic disconnect test |
| **MEDIUM** | 7 | VAD RMS default, post-wake delay blocking, API error handling, unbounded memory, expiry logic, UI state flicker |
| **LOW** | 0 | (All deferred to existing audit.md) |
