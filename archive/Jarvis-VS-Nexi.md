# NEXI — Neural Executive Intelligence: Deep Root Analysis

> **Codebase:** `E:\ai-agnet-nexi`
> **Type:** Privacy-First Desktop AI Assistant (Windows)
> **Language:** Python 3.11+ / JavaScript / HTML/CSS
> **Architecture:** Dual-Process (multiprocessing.Queue IPC)
> **Lines of Code:** ~5,500 Python + ~585 JS + ~153 CSS
> **Tests:** 137 pytest tests (100% pass rate)

---

## 1. ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────┐
│                    run.py (Launcher)                     │
│   multiprocessing.Process spawns:                       │
│                                                         │
│  ┌── Process 1 (UI + Engine) ──┐  ┌── Process 2 (Wake) ─┐
│  │  main.py → Eel HTTP @:8000  │  │  wake/pipeline.py   │
│  │                             │  │  Mic → VAD → wake   │
│  │  ┌─ core/dispatcher.py    ─┐│  │  detection → ASR    │
│  │  │  Intent → Skill → Brain ││  │                     │
│  │  └─────────────────────────┘│  │  IPC: Queue         │
│  │  ┌─ www/ (HTML/JS/CSS)    ─┐│  │  post_command()     │
│  │  │  Eel JS ↔ Python bridge ││  │  post_status()      │
│  │  └─────────────────────────┘│  │  post_wake()        │
│  └─────────────────────────────┘  └─────────────────────┘
└─────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

| Decision | Implementation | Rationale |
|----------|---------------|-----------|
| **Modular packages** | 10 focused packages (core, brain, intent, memory, wake, skills, control, workflow, ui, vision) | Each package < 350 lines |
| **Dual-process IPC** | `multiprocessing.Queue` bridge | Wake never blocks UI |
| **Deterministic → LLM routing** | `intent/router.py` priority chain | Fast local + deep LLM |
| **Unified memory manager** | `memory/manager.py` — single JSON-backed store | No redundancy |
| **Single DSP clap** | `wake/clap.py` — 6-parameter DSP | One clean implementation |
| **Graceful degradation** | Every component has fallback | No single point of failure |
| **Dataclass config** | `core/config.py` — `NexiConfig` | Type-safe, env-driven |

---

## 2. FEATURES INVENTORY

### 2.1 Wake & Audio Pipeline

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| OpenWakeWord hotword ("Hey Nexi") | `wake/hotword.py` | ~100 | ✅ Custom ONNX model |
| DSP double-clap wake | `wake/clap.py` | ~120 | ✅ Single clean backend |
| Silero VAD + Energy VAD fallback | `wake/vad.py` | ~80 | ✅ Dual-backend VAD |
| Groq Whisper ASR | `core/asr.py` | ~60 | ✅ `whisper-large-v3-turbo` |
| Groq TTS + pyttsx3 fallback | `core/tts.py` | ~80 | ✅ Cloud + offline |
| Barge-in support | `core/ui_state.py` | ~80 | ✅ Speech interruption |
| Wake pipeline orchestration | `wake/pipeline.py` | ~200 | ✅ Full pipeline controller |

### 2.2 Brain / LLM

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Gemini 2.5 Flash brain | `brain/gemini.py` | 157 | ✅ With context injection |
| Gemini model chain | `brain/gemini.py` | inline | ✅ Flash → Flash-Lite fallback |
| Multi-step planner | `brain/planner.py` | 72 | ✅ Groq LLM plan decomposition |

### 2.3 Intent Routing

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Deterministic router | `intent/router.py` | ~120 | ✅ Pattern matching |
| Groq LLM fallback router | `intent/router.py` | inline | ✅ Schema-based routing |
| Complete taxonomy | `intent/taxonomy.py` | ~80 | ✅ All routes, intents, validation |
| Safety gate (local) | `intent/safety_gate.py` | ~60 | ✅ Keyword-based risk assessment |
| Hindi/Hinglish normalizer | `intent/bilingual.py` | ~60 | ✅ Verb-final reordering |

### 2.4 Memory System

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Unified memory manager | `memory/manager.py` | ~150 | ✅ 10 categories, JSON-backed |
| Conversation context | `memory/context.py` | ~80 | ✅ Deque (30 turns), redaction |
| User model (learned preferences) | `memory/user_model.py` | ~80 | ✅ Auto-extraction of preferences |
| Learned rules ("when X do Y") | `memory/rules.py` | ~80 | ✅ Trigger→action mapping |
| Memory safety/redaction | `memory/safety.py` | ~60 | ✅ PII redaction, secret words |

### 2.5 Desktop Automation (Skills)

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| App launcher (18+ apps) | `skills/apps.py` | 46 | ✅ `subprocess.Popen` |
| Web navigator (22+ sites) | `skills/web.py` | 53 | ✅ `webbrowser.open` |
| Browser keyboard control | `skills/browser.py` | 88 | ✅ pyautogui hotkeys |
| File/folder/project creation | `skills/files.py` | 100 | ✅ With templates |
| System (time, weather, clipboard) | `skills/system.py` | 84 | ✅ Open-Meteo API |
| Email (SMTP Gmail) | `skills/communication.py` | 68 | ✅ SMTP + web scraping |
| Games (rock-paper-scissors) | `skills/games.py` | 32 | ✅ Multi-turn workflow |
| Reminders/alarms | `skills/scheduler.py` | 130 | ✅ JSON-backed, background thread |
| Music (Spotify search) | `skills/web.py` | inline | ✅ Web player |
| Skill dispatch map | `skills/dispatch.py` | 81 | ✅ Clean intent→handler mapping |

### 2.6 Vision / Camera

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Hand tracking cursor | `vision/hand.py` | ~100 | ✅ MediaPipe + pyautogui |
| Face tracking cursor | `vision/eye.py` | ~100 | ✅ MediaPipe FaceMesh |
| Camera subprocess runner | `vision/runner.py` | 16 | ✅ Isolated process |

### 2.7 UI (Mark-Style HUD)

| Feature | | Quality |
|---------|-|---------|
| Canvas-animated HUD orb | `www/hud_orb.js` (196 lines) | ✅ State-aware animation |
| System monitor (CPU/MEM/NET) | `www/main.js` | ✅ Live metrics |
| Activity log (color-coded) | `www/controller.js` | ✅ Right panel |
| Command bar + mic button | `www/index.html` | ✅ Text + voice input |
| Suggestion chips | `www/index.html` | ✅ Clickable commands |
| Tool categories | `www/index.html` | ✅ Visual tool badges |
| Settings overlay | `www/index.html` | ✅ Provider status, config |
| Output workspace actions | `www/controller.js` | ✅ Copy/Save/Shorten/Regenerate/Read Aloud |
| Debug console | `www/controller.js` | ✅ Level-filtered |
| Emergency stop | `www/main.js` | ✅ One-click kill switch |
| Drag-and-drop file upload | `www/index.html` | ✅ Upload zone |

### 2.8 Workflow / Multi-turn

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Multi-turn workflow manager | `workflow/manager.py` | 128 | ✅ File creation, project, RPS |
| Clarification slot-filling | `workflow/clarification.py` | 55 | ✅ Vague command handling |

### 2.9 MCP Integration

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Stdio JSON-RPC MCP client | `tools/mcp.py` | 115 | ✅ 60s cache |
| MCP server definitions | `config/mcp.json` | ~20 | ✅ ruflo, ruv-swarm, flow-nexus |

### 2.10 Infrastructure

| Feature | File | Lines | Quality |
|---------|------|-------|---------|
| Dual-process launcher | `run.py` | ~80 | ✅ Queue + Event IPC |
| Config dataclass | `core/config.py` | ~80 | ✅ Env-driven NexiConfig |
| State machine | `core/ui_state.py` | ~80 | ✅ 8 canonical states |
| UI adapter (Eel API) | `ui/adapter.py` | 154 | ✅ Clean JS→Python surface |
| Connectivity check | `core/online.py` | 11 | ✅ HTTP to google.com |
| Wake word training pipeline | `training/train_hey_nexi.py` | 800 | ✅ TTS synthesis + recording + augmentation + PyTorch |

### 2.11 Testing

| Feature | File | Quantity | Quality |
|---------|------|----------|---------|
| Import tests | `tests/test_imports.py` | 25 | ✅ |
| Intent router | `tests/test_intent_router.py` | 28 | ✅ |
| Taxonomy | `tests/test_taxonomy.py` | 10 | ✅ |
| Safety gate | `tests/test_safety_gate.py` | 12 | ✅ |
| Config | `tests/test_config.py` | 10 | ✅ |
| Skills basic | `tests/test_skills_basic.py` | 16 | ✅ |
| Memory context | `tests/test_memory_context.py` | 8 | ✅ |
| Memory rules | `tests/test_memory_rules.py` | 8 | ✅ |
| Control gate | `tests/test_control_gate.py` | 7 | ✅ |
| Dispatcher | `tests/test_dispatcher.py` | 4 | ✅ |
| MCP tools | `tests/test_tools_mcp.py` | 1 | ✅ |
| UI adapter | `tests/test_ui_adapter.py` | 5 | ✅ |
| **Total** | **14 files** | **137** | **✅ 100% pass rate** |

---

## 3. PROS (What It Does Well)

### 3.1 Strengths

| # | Strength | Details |
|---|----------|---------|
| 1 | **Privacy-First Design** | Wake detection is 100% LOCAL. No cloud until user initiates a command. Genuine differentiator. |
| 2 | **Excellent Modularity** | 10 clean packages, each with focused responsibility. No god files. Average function ~40 lines. |
| 3 | **High Code Quality** | Dataclasses, type hints, pathlib, proper exception handling, comprehensive logging. All `except: pass` eliminated. |
| 4 | **Comprehensive Wake System** | Hotword + double-clap + VAD with cooldown, rising edge detection, consecutive hit verification — industrial-grade. |
| 5 | **Multi-modal Input** | Voice, text, file drop, keyboard shortcuts, suggestion chips |
| 6 | **Gorgeous HUD UI** | Canvas-animated orb with state-aware animations, system monitor, dark terminal aesthetic |
| 7 | **Bilingual Support** | Hindi/Hinglish command normalization — rare and valuable |
| 8 | **Complete Audit Trail** | `error.md` — 39-page comprehensive audit documenting every issue & fix |
| 9 | **137 Tests at 100%** | Comprehensive coverage, all green |
| 10 | **Graceful Degradation** | Every component has fallbacks — TTS (Groq→pyttsx3), VAD (Silero→Energy), brain (model chain), wake (hotword+clap) |
| 11 | **Real Safety Systems** | Emergency stop, risk classification, memory redaction, safe path validation |
| 12 | **Multi-step Planning** | Can decompose complex requests into sequential steps |
| 13 | **Clean Config** | Single dataclass for all configuration, driven by `.env` |
| 14 | **Dual-Process IPC** | Clean multiprocessing.Queue bridge with typed events |

### 3.2 Architectural Strengths

- **No god files** — largest file is `dispatcher.py` at 331 lines
- **Clean separation of concerns** — core, brain, intent, memory, wake, skills all independent
- **Priority chain dispatch** — rules → workflow → clarification → memory → intent → brain
- **Strategy pattern** for backends (VAD, TTS, ASR)
- **Subprocess isolation** for vision (MediaPipe/OpenCV)
- **Thread safety** with `threading.Lock()` where needed
- **Security fixes applied** — 60+ silent `except: pass` eliminated, shell injection fixed, API key in header not URL

---

## 4. CONS (What's Wrong/Missing)

### 4.1 Critical Gaps

| # | Gap | Severity | Why It Matters |
|---|-----|----------|----------------|
| 1 | **No Vector Database / RAG** | 🔴 CRITICAL | Memory is keyword-overlap on JSON files. No semantic search, no embeddings, no true retrieval-augmented generation. |
| 2 | **No LLM Tool Calling** | 🔴 CRITICAL | MCP tools are discovered and displayed but the brain CAN'T call them autonomously. No function-calling loop. |
| 3 | **Cloud-Dependent Brain** | 🔴 HIGH | No offline LLM support (llama.cpp, etc.). Requires internet for all Q&A. |
| 4 | **No Streaming** | 🟡 MEDIUM | All communication is request-response. No progressive TTS, no streaming LLM responses. |

### 4.2 Minor Issues

| # | Issue | Severity | Details |
|---|-------|----------|---------|
| 1 | **Dead Control Module (~250 lines)** | 🟡 MEDIUM | `control/` package is deprecated but still loaded at startup. Complete duplicate of `skills/`. |
| 2 | **Dual LLM Unfinished** | 🟡 LOW | `brain/__init__.py` has commented-out `brain.groq.py` import — file doesn't exist. |
| 3 | **MCP Integration Limited** | 🟡 MEDIUM | Tools injected into Gemini context but no autonomous selection/calling loop |
| 4 | **JSON File Persistence** | 🟡 MEDIUM | All memory uses JSON files — no indexing, no concurrent access, no atomic writes |
| 5 | **Thread Safety Risks** | 🟡 LOW | Global mutable state `_pending` and `_active_workflow` could race under real barge-in |
| 6 | **Generic Error Messages** | 🟡 LOW | Many errors return "Sorry, something went wrong" instead of classified messages |
| 7 | **No Plugin System** | 🟡 LOW | Skills hardcoded in `skills/dispatch.py`. No hot-reloading. |
| 8 | **Single Wake Word** | 🟡 LOW | "Hey Nexi" requires full retraining pipeline for custom words |

### 4.3 Missing Features (Compared to JARVIS)

| Feature | Status | Why JARVIS Has It |
|---------|--------|-------------------|
| ReAct planning loop | ❌ Missing | JARVIS has `react_planner.py` with full tool-calling |
| 3-tier memory (auto+semantic+episodic) | ❌ Missing | JARVIS has 3 separate memory systems |
| Training/learning engine | ❌ Missing | JARVIS has 12 training modules |
| Face recognition | ❌ Missing | JARVIS has LBPH-based face auth |
| Eye tracking | ❌ Missing | JARVIS has full eye cursor control |
| Text-to-image generation | ❌ Missing | JARVIS has `text_to_image.py` |
| Multi-brain provider chain | ❌ Partial | JARVIS has Gemini→Lightning→HugChat |
| 12 system prompts | ❌ Partial | JARVIS has separate prompts per subsystem |
| 50+ tool registry | ❌ Partial | JARVIS has 50+ ToolSpec entries |
| 67 debug scripts | ❌ Missing | JARVIS has extensive debug tools |
| Multi-agent orchestration dirs | ❌ Missing | JARVIS has .claude, .octogent, etc. |
| MCP tool bridge | ❌ Partial | JARVIS has dedicated `mcp_tool_bridge.py` |
| Dockerfile | ❌ Missing | JARVIS has container support |
| HugChat integration | ❌ Missing | JARVIS has free-tier LLM |

---

## 5. WHAT IT HAS vs WHAT IT DOESN'T HAVE

### What NEXI HAS (Unique Strengths)

| Feature | Status | How It's Better Than JARVIS |
|---------|--------|----------------------------|
| **Clean modular architecture** | ✅ | 10 packages, no god files, max 331 lines per file vs JARVIS's 2146-line command.py |
| **137 passing tests** | ✅ | Full pytest suite at 100% vs JARVIS has no viable tests |
| **Bilingual Hindi/Hinglish** | ✅ | Verb-final reordering, word replacement — unique feature |
| **Comprehensive audit & fix cycle** | ✅ | 39-page error.md documenting every issue fixed |
| **Privacy-first wake** | ✅ | 100% local wake detection |
| **Beautiful HUD UI** | ✅ | Canvas orb, system monitor, activity log, suggestion chips |
| **Memory safety/redaction** | ✅ | PII redaction, secret word detection, safe file paths |
| **Emergency stop** | ✅ | One-click kill switch for all actions |
| **Dataclass configuration** | ✅ | Type-safe, env-driven, single source of truth |
| **Graceful degradation everywhere** | ✅ | Every component has fallback |
| **Dual-process IPC bridge** | ✅ | Clean typed event queue vs JARVIS's ad-hoc approach |
| **Wake word training pipeline** | ✅ | 800-line TTS synthesis + augmentation + PyTorch training |
| **Workflow manager** | ✅ | Multi-turn state machines for complex tasks |
| **Security fixes applied** | ✅ | Shell injection, API key header, path traversal all fixed |

### What NEXI DOESN'T HAVE (Compared to JARVIS)

| Feature | Status | Why It Matters |
|---------|--------|----------------|
| ReAct planning with tool calling | ❌ | JARVIS can autonomously invoke tools via ReAct loop |
| 3-tier memory (auto+semantic+episodic) | ❌ | NEXI has unified but basic memory; JARVIS has deeper layered memory |
| Training/learning engine (12 modules) | ❌ | JARVIS learns from corrections, has curriculum, policy, evaluation |
| Face recognition on startup | ❌ | JARVIS has LBPH-based biometric auth |
| Eye tracking / hand gesture cursor | ❌ | JARVIS has full camera-based cursor control |
| Text-to-image generation | ❌ | JARVIS can generate images |
| Multi-brain provider chain (3+ providers) | ❌ | JARVIS has Gemini→Lightning→HugChat chain |
| 12 specialized system prompts | ❌ | JARVIS has per-subsystem prompt engineering |
| 50+ tool registry | ❌ | JARVIS has comprehensive tool definitions |
| 67 debug/troubleshooting scripts | ❌ | JARVIS has per-subsystem debugging |
| Multi-agent orchestration directories | ❌ | JARVIS has Claude, Octogent, Qodo, Sixth, Hermes agent configs |
| Dedicated MCP tool bridge | ❌ | JARVIS has more sophisticated MCP integration |
| Docker container support | ❌ | JARVIS has Dockerfile |
| Music playback / YouTube | ❌ | JARVIS has pywhatkit YouTube integration |
| News headlines | ❌ | JARVIS has news module |
| Google Maps places search | ❌ | JARVIS has dedicated maps module |
| Automatic typing | ❌ | JARVIS has auto-type feature |
| HugChat free-tier LLM | ❌ | JARVIS has free cloud LLM fallback |
| Game module (in-assistant) | ❌ | JARVIS has built-in games |

---

## 6. TECHNICAL DEBT SUMMARY

| Category | Count | Details |
|----------|-------|---------|
| **God files** | 0 | Largest file: dispatcher.py (331 lines) |
| **Redundant implementations** | 1 | `control/` package (250 lines, deprecated) |
| **Dead code paths** | 1 | `control/` loaded at startup |
| **Missing tests** | 0 | 137 tests at 100% |
| **Wildcard imports** | 0 | All explicit imports |
| **sys.path hacks** | 0 | None |
| **Security leaks** | 0 | All fixed (per audit) |
| **Silent except:pass** | 0 | All eliminated |

---

## 7. HOW NEXI IS BETTER THAN JARVIS

### 7.1 Architectural Superiority

| Dimension | JARVIS | NEXI | Winner |
|-----------|--------|------|--------|
| **Largest file** | 2146 lines (command.py) | 331 lines (dispatcher.py) | **NEXI** |
| **Package count** | Monolithic + ~10 subdirs | 10 clean packages | **NEXI** |
| **Dead code** | 3+ redundant systems | 1 deprecated package | **NEXI** |
| **Test coverage** | ~0 tests | 137 tests at 100% | **NEXI** |
| **Config approach** | Ad-hoc env reads | Dataclass `NexiConfig` | **NEXI** |
| **Exception handling** | Mixed, some bare excepts | All logged, no silent failures | **NEXI** |
| **Security posture** | cookies.json, Base64 creds | All fixed, audit trail | **NEXI** |
| **Documentation** | No README | Full README + error.md | **NEXI** |
| **Import style** | Wildcard `*` imports | Explicit imports | **NEXI** |
| **Type hints** | Inconsistent | Consistent | **NEXI** |

### 7.2 Where JARVIS Is Better

| Dimension | JARVIS | NEXI | Winner |
|-----------|--------|------|--------|
| **Feature breadth** | 40K+ lines, 131 modules | 5.5K lines, 44 modules | **JARVIS** |
| **Memory depth** | 3-tier (auto+semantic+episodic) | Unified JSON manager | **JARVIS** |
| **Training system** | 12 training modules | None | **JARVIS** |
| **Vision system** | Eye + hand + face recognition | Hand + face only | **JARVIS** |
| **Brain providers** | Gemini→Lightning→HugChat (3) | Gemini only (Groq stubbed) | **JARVIS** |
| **Tool calling** | ReAct planner + tool registry | Display only, no calling | **JARVIS** |
| **Debug scripts** | 67 scripts | None | **JARVIS** |
| **Agent integration** | 5 agent directories | None | **JARVIS** |
| **Text-to-image** | Yes | No | **JARVIS** |
| **Container support** | Dockerfile | No | **JARVIS** |

---

## 8. FINAL VERDICT

### NEXI's Core Identity: **Clean, Secure, Maintainable**

NEXI is a **privacy-first, well-architected** desktop AI assistant that prioritizes **code quality, security, and maintainability** over raw feature count. It's the result of a deliberate refactoring effort that took the bloated JARVIS codebase and transformed it into a lean, modular, test-covered system.

- **Code Quality:** ⭐⭐⭐⭐⭐ (Cleanest AI assistant codebase reviewed)
- **Security:** ⭐⭐⭐⭐⭐ (Comprehensive audit completed, all issues fixed)
- **Testing:** ⭐⭐⭐⭐⭐ (137 tests, 100% pass rate)
- **Maintainability:** ⭐⭐⭐⭐⭐ (Max 331 lines per file, clean separation)
- **Feature Breadth:** ⭐⭐⭐ (5.5K lines, focused feature set)
- **UI Polish:** ⭐⭐⭐⭐⭐ (Gorgeous HUD orb, system monitor, multi-modal input)
- **Wake Detection:** ⭐⭐⭐⭐⭐ (Industrial-grade, local, private)
- **Documentation:** ⭐⭐⭐⭐⭐ (README + 39-page error.md audit trail)

### JARVIS's Core Identity: **Ambitious, Feature-Rich, Technical Debt Heavy**

JARVIS is a **massively ambitious** AI assistant that tries to do everything — wake detection, ASR, TTS, multi-model brain, 3-tier memory, training system, face recognition, eye tracking, hand gestures, text-to-image, MCP, games, news, maps, and more. But this ambition comes at a cost: god files, redundancy, dead code, no tests, and security issues.

- **Code Quality:** ⭐⭐ (God files, redundancy, dead code)
- **Security:** ⭐⭐ (cookies.json, Base64 creds, no tests)
- **Testing:** ⭐ (No viable test suite)
- **Maintainability:** ⭐⭐ (Monolithic core, 2146-line file)
- **Feature Breadth:** ⭐⭐⭐⭐⭐ (40K+ lines, 131 modules)
- **UI Polish:** ⭐⭐⭐⭐ (SiriWave, Canvas, Bootstrap)
- **Wake Detection:** ⭐⭐⭐⭐⭐ (Industrial-grade pipeline)
- **Documentation:** ⭐ (No README)

### Bottom Line

**NEXI is the clean, professional, production-ready version.** It's what you get when you take the JARVIS concept and apply proper software engineering — modularity, testing, security, documentation, and graceful degradation.

**JARVIS is the ambitious prototype.** It has more features, more depth in some areas (memory, training, vision, multi-provider brain), but it's held back by technical debt that makes it difficult to maintain, extend, or deploy safely.

**If you want to build on one:** Start with NEXI's architecture and selectively port JARVIS's best features (ReAct planner, deeper memory, training system) into NEXI's clean foundation.

---

## 9. COMPLETE COMPARISON MATRIX

| Category | NEXI | JARVIS |
|----------|------|--------|
| **Total Python LOC** | ~5,500 | ~35,000+ |
| **Largest file** | 331 lines (dispatcher.py) | 2,146 lines (command.py) |
| **Number of packages** | 10 | ~15 (including subdirs) |
| **Test count** | 137 | ~0 |
| **Test pass rate** | 100% | N/A |
| **Redundant systems** | 1 (control/) | 4+ (clap, memory, router, wake) |
| **Security leaks found** | 0 (all fixed) | 2+ (cookies, Base64) |
| **Silent except:pass** | 0 | 10+ |
| **God files** | 0 | 2 |
| **Wildcard imports** | 0 | 2 |
| **sys.path manipulation** | 0 | 5+ |
| **Bilingual support** | ✅ Hindi/Hinglish | ❌ |
| **Offline wake** | ✅ 100% local | ✅ 100% local |
| **Offline LLM** | ❌ | ❌ |
| **Vector database** | ❌ | ❌ |
| **LLM function calling** | ❌ (display only) | ⚠️ (ReAct planner exists) |
| **Streaming** | ❌ | ❌ |
| **Plugin system** | ❌ | ❌ |
| **Wake word training** | ✅ Custom pipeline | ❌ |
| **Face recognition** | ❌ | ✅ LBPH-based |
| **Eye tracking** | ❌ | ✅ MediaPipe |
| **Hand gestures** | ✅ | ✅ |
| **Text-to-image** | ❌ | ✅ |
| **Training/learning engine** | ❌ | ✅ 12 modules |
| **3-tier memory** | ❌ (unified) | ✅ (autonomous+semantic+episodic) |
| **Multi-brain providers** | ❌ (Gemini only) | ✅ (3 providers) |
| **Docker support** | ❌ | ✅ |
| **MCP integration** | ✅ (limited) | ✅ (dedicated bridge) |
| **Multi-agent configs** | ❌ | ✅ (5 agent dirs) |
| **Game module** | ✅ (RPS) | ✅ (RPS) |
| **Email** | ✅ (SMTP) | ✅ (SMTP) |
| **Weather** | ✅ (Open-Meteo) | ❌ (not found) |
| **Music** | ✅ (Spotify web) | ✅ (YouTube) |
| **System monitor UI** | ✅ CPU/MEM/NET | ❌ |
| **Emergency stop** | ✅ | ❌ |
| **Settings overlay** | ✅ | ❌ |
| **Debug console** | ✅ | ❌ |
| **File drag-drop** | ✅ | ❌ |
| **Suggestion chips** | ✅ | ❌ |
| **Audit trail (error.md)** | ✅ 39 pages | ❌ |
| **README documentation** | ✅ Full | ❌ |
| **Docker** | ❌ | ✅ |

---

## 10. RECOMMENDED ROADMAP FOR NEXI

### Priority 1 (Critical for 2026 AI Assistant)

1. **Add vector database (SQLite + embeddings)** for semantic memory instead of JSON keyword-overlap
2. **Implement LLM function calling** — expose MCP tools as Gemini function declarations, add tool-calling loop
3. **Add offline LLM support** — integrate llama.cpp or similar for local inference fallback

### Priority 2 (High Value)

4. **Implement streaming** — progressive TTS output, streaming LLM responses via Eel
5. **Remove dead `control/` package** — complete the deprecation
6. **Add plugin system** — dynamic skill discovery with hot-reload
7. **Add persistent file logging** — debug without console dependency

### Priority 3 (Nice to Have)

8. **Multi-wake-word support** — allow users to train custom wake words
9. **Better error classification** — categorized user-facing messages
10. **SQLite migration** — replace JSON files with proper database
