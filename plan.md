# NEXI-JARVIS Fusion: Complete Merge Plan

> **Goal:** Merge JARVIS's feature depth (40K+ lines, 131 modules, ReAct planner, training system, vision, 3-tier memory) into NEXI's clean architecture (5.5K lines, 10 packages, 137 tests, modular).
> **Foundation:** NEXI architecture with JARVIS features selectively ported in.
> **Total Duration:** 9 weeks (8 phases + 1 week final polish)
> **Total Tests:** 220+ (137 existing + ~85 new)
> **Model:** Claude Opus 4.8 (primary — via max plan subscription)

---

## 1. Core Decision: Why NEXI Is The Foundation

| Dimension | NEXI | JARVIS | Winner |
|-----------|------|--------|--------|
| Largest file | 331 lines (dispatcher.py) | 2146 lines (command.py) | **NEXI** |
| Test coverage | 137 tests, 100% pass | ~0 tests | **NEXI** |
| Security leaks | 0 (all fixed) | cookies.json, Base64 creds | **NEXI** |
| Dead code | 1 deprecated pkg | 4+ redundant systems | **NEXI** |
| Redundant systems | 1 (control/) | 4+ (clap, memory, router, wake) | **NEXI** |
| Silent except:pass | 0 | 10+ | **NEXI** |
| Feature breadth | 5.5K lines | 40K+ lines, 131 modules | **JARVIS** |
| ReAct planner | ❌ | ✅ | **JARVIS** |
| 3-tier memory | ❌ (unified) | ✅ (auto+semantic+episodic) | **JARVIS** |
| Training/learning | ❌ | ✅ 12 modules | **JARVIS** |
| Vision (eye/face) | ❌ | ✅ | **JARVIS** |

**Decision:** Build on NEXI's clean foundation. Port JARVIS features selectively. Do NOT import JARVIS's technical debt.

---

## 2. Model Strategy

### 2.1 Primary: Claude Opus 4.8

You have **max plan** access to Claude Opus 4.8 — the strongest model for this workload. Opus 4.8 is a refinement over 4.7 that fixes tool-calling regressions and improves SWE-bench Pro to 69.2%.

| Workload | Model | Rationale |
|----------|-------|-----------|
| **ReAct Planner** (tool calling) | **Claude Opus 4.8** | SWE-bench Pro 69.2%, MCPAtlas 77.3+, best tool orchestration, available via max plan |
| **Intent Router** (LLM fallback) | **Claude Opus 4.8** | Same model — fast enough for routing via max plan |
| **Brain Q&A** (general chat) | **Claude Opus 4.8** | Strongest general reasoning + code understanding |

If you ever want a **free/self-hosted fallback**, add DeepSeek V4 Flash ($0.15/$0.30 per MTok, MIT license) as a secondary router — but Opus 4.8 is strictly better on every dimension that matters for this project.

### 2.2 Why Claude Opus 4.8

| Factor | Detail |
|--------|--------|
| **SWE-bench Pro 69.2%** | Best at real-world repo-scale engineering — the tasks this merge will produce |
| **MCPAtlas 77.3+** | Best MCP tool orchestration score. Your MCP servers (ruflo, ruv-swarm, flow-nexus) work optimally. |
| **Tool-calling fixed** | Opus 4.8 fixes the comment-verbosity and tool-calling regressions that affected Opus 4.7 |
| **1M context** | Can process the entire NEXI + JARVIS codebase in one window |
| **Available via max plan** | No per-token cost anxiety. Use freely for all ReAct loops. |
| **Claude Code / CLI compatible** | Works with anthropic SDK, drop-in with any OpenAI-compatible client via proxy |
| **Best instruction following** | Stricter adherence to system prompts — critical for ReAct loop safety |
| **Adaptive thinking** | Automatically adjusts reasoning depth per task — no manual budget tuning |

### 2.3 No Limitations for This Use Case

Opus 4.8 has no practical limitations for the NEXI-JARVIS merge:
- ✅ Tool calling: reliable, fixed from 4.7 regressions
- ✅ Context: 1M window covers both codebases
- ✅ Cost: covered by max plan subscription
- ✅ Latency: adaptive thinking means fast simple queries, deep complex ones
- ✅ Function calling: native tool use API with JSON schema

---

## 3. Phase Breakdown

### Phase 1: Foundation (Week 1)
**Goal:** Extend NEXI's taxonomy, config, and routing for JARVIS features.

| Step | File | Change | Lines | New Tests |
|------|------|--------|-------|:---------:|
| 1.1 | `intent/taxonomy.py` | Add `"jarvis"` route, 12 JARVIS_INTENTS, extend validation | +30 | +4 |
| 1.2 | `core/config.py` | Add `NexiJarvisConfig`: 7 fields (jarvis_enabled, tool_calling, max_steps, memory_type, training, provider, provider_key) | +40 | +3 |
| 1.3 | `intent/router.py` | Add 15 deterministic patterns for Jarvis commands (tool calls, agent commands, training), extend LLM router prompt | +80 | +6 |
| 1.4 | `skills/dispatch.py` | Add Jarvis skill module import + 12 intent→handler mappings | +25 | +2 |
| 1.5 | `skills/jarvis.py` | **NEW:** Stub with 4 handlers: status, run_tool, train, reflect | +60 | +3 |
| 1.6 | `core/tts.py` | Switch from hardcoded Groq to config-based provider | +15 | +2 |
| 1.7 | `core/asr.py` | Switch from hardcoded Groq to config-based provider | +15 | +2 |
| 1.8 | `brain/gemini.py` | Make provider pluggable, check cfg.brain_provider, fallback chain | +30 | +2 |
| 1.9 | `tests/` | Phase 1 tests: taxonomy, config, router, dispatch, skill stub | +24 | — |

**Total Phase 1:** ~295 lines, ~24 new tests, ~3-4 days

**Exit gate:** All 137 existing NEXI tests pass. New 24 Phase 1 tests pass. Config loads with Jarvis fields. Router recognizes `"jarvis"` route.

---

### Phase 2: Tool Registry & Execution (Week 2)
**Goal:** Port 50+ ToolSpec definitions + LLM function calling.

| Step | Description | Lines | New Tests |
|------|-------------|-------|:---------:|
| 2.1 | Create `tools/jarvis_registry.py` — 50+ ToolSpec definitions with to_openai_schema() | 400 | 8 |
| 2.2 | Create `tools/jarvis_executor.py` — tool dispatch via NEXI's skills/ modules | 300 | 6 |
| 2.3 | Implement LLM function calling in `brain/gemini.py` — Claude Opus 4.8 tool use API | 200 | 4 |
| 2.4 | Wire tools into `core/dispatcher.py` priority 4.5 | 60 | 2 |
| **Total** | | **960** | **20** |

**Exit gate:** 50+ tools executable voice/text. LLM autonomously selects + calls tools. All Phase 1 tests still pass.

---

### Phase 3: ReAct Planning Loop (Week 3)
**Goal:** Port JARVIS's ReAct planner for autonomous multi-step reasoning.

| Step | Description | Lines | New Tests |
|------|-------------|-------|:---------:|
| 3.1 | Create `brain/react_planner.py` — ReActStep/ReActPlan dataclasses + loop. Replace Groq→NEXI's LLM, safety_gate, tool_executor | 350 | 8 |
| 3.2 | Wire into dispatcher for `route=="jarvis"``intent=="plan_reactive"` | 20 | 1 |
| 3.3 | Add interruption support via bridge → UI emergency stop | 40 | 1 |
| **Total** | | **410** | **10** |

**Exit gate:** ReAct planner runs 3+ step tool chains. Interruption works. All Phase 1-2 tests pass.

---

### Phase 4: Advanced Memory (Weeks 4-5)
**Goal:** Add JARVIS's episodic + semantic memory, reflection engine, rules engine.

| Step | Description | Lines | New Tests |
|------|-------------|-------|:---------:|
| 4.1 | Upgrade `memory/manager.py` — add EpisodicMemory + SemanticMemory layers, vector embeddings | 500 | 10 |
| 4.2 | Create `memory/reflection.py` — correction learning cascading events | 200 | 4 |
| 4.3 | Create `memory/rules_engine.py` — "when X do Y" training rules | 250 | 4 |
| 4.4 | Enhance `brain/gemini.py` context injection — 7-source cognitive context pipeline | 200 | 2 |
| **Total** | | **1150** | **20** |

**Exit gate:** Episodic/semantic memory operational. Reflection extracts lessons. Rules engine parses rules. 7-source context injection. All Phase 1-3 tests pass.

---

### Phase 5: Training & Learning (Week 6)
**Goal:** Port JARVIS's 12 training modules.

| Step | Description | Lines | New Tests |
|------|-------------|-------|:---------:|
| 5.1 | Create `training/` package — feedback, correction, curriculum, policy | 500 | 10 |
| 5.2 | Wire training into dispatch priority 2.5 | 30 | 1 |
| 5.3 | Upgrade `memory/user_model.py` — auto-preference inference | 100 | 2 |
| **Total** | | **630** | **13** |

**Exit gate:** Full training loop: correction → reflection → rule update → behavior change. All Phase 1-4 tests pass.

---

### Phase 6: Vision & Camera (Week 7)
**Goal:** Port JARVIS's eye tracking + face recognition.

| Step | Description | Lines | New Tests |
|------|-------------|-------|:---------:|
| 6.1 | Create `vision/eye_tracking.py` (port from JARVIS) | 200 | 3 |
| 6.2 | Create `vision/face_auth.py` (port from JARVIS) | 100 | 2 |
| 6.3 | Wire vision control through `skills/vision_control.py` | 50 | 1 |
| **Total** | | **350** | **6** |

**Exit gate:** Eye tracking + face auth functional. All Phase 1-5 tests pass.

---

### Phase 7: Polish & Prompts (Week 8)
**Goal:** Port 12 JARVIS system prompts, add streaming.

| Step | Description | Lines | New Tests |
|------|-------------|-------|:---------:|
| 7.1 | Port 12 system prompts from JARVIS → NEXI format | — | 3 |
| 7.2 | Add Gemini streaming via SSE through bridge → UI | 150 | 2 |
| 7.3 | Delete dead code (NEXI `control/` package) | −250 | — |
| **Total** | | **−100** | **5** |

**Exit gate:** 12 prompts loaded. Streaming LLM + TTS works. Dead code removed. All Phase 1-6 tests pass.

---

### Phase 8: Final Polish (Week 9)
**Goal:** 220+ tests all green, documentation, performance profiling.

| Step | Description |
|------|-------------|
| 8.1 | Run full test suite — must pass (220+ tests) |
| 8.2 | Update README, create ARCHITECTURE.md |
| 8.3 | Performance profiling: ReAct latency, memory recall, wake startup |
| 8.4 | Model tuning: Opus 4.8 effort levels (adaptive vs max) |

---

## 4. Files Changed/Created/Deleted

| Action | Count | Examples |
|--------|-------|---------|
| **New files** | ~25 | `brain/react_planner.py`, `tools/jarvis_registry.py`, `tools/jarvis_executor.py`, `memory/reflection.py`, `memory/rules_engine.py`, `skills/jarvis.py`, `training/feedback.py`, `training/correction.py`, `training/curriculum.py`, `training/policy.py`, `vision/eye_tracking.py`, `vision/face_auth.py`, 8 new prompts, ~15 test files |
| **Modified files** | ~15 | `core/config.py`, `core/dispatcher.py`, `core/tts.py`, `core/asr.py`, `intent/taxonomy.py`, `intent/router.py`, `brain/gemini.py`, `memory/manager.py`, `memory/context.py`, `memory/user_model.py`, `skills/dispatch.py`, `skills/vision_control.py`, `www/controller.js`, `www/index.html`, `brain/planner.py` |
| **Deleted files** | ~6 | NEXI `control/` package (6 files) |
| **Total delta** | **~40 files** | +25 new, ~15 modified, ~6 deleted |

---

## 5. Architecture After Merge

```
E:\ai-agnet-nexi\
├── run.py                      # Launcher (unchanged)
├── main.py                     # Entry (unchanged)
├── core/                       # UNCHANGED pattern
│   ├── config.py               # + Jarvis config fields
│   ├── dispatcher.py           # + Jarvis route + tool execution + ReAct
│   ├── bridge.py               # UNCHANGED
│   ├── tts.py                  # + provider selection
│   ├── asr.py                  # + provider selection
│   ├── ui_state.py             # UNCHANGED
│   └── online.py               # UNCHANGED
├── brain/                      # ENHANCED
│   ├── gemini.py               # + function calling + 7-source context
│   ├── react_planner.py        # NEW: ReAct tool-calling loop
│   └── planner.py              # UNCHANGED
├── intent/                     # ENHANCED
│   ├── router.py               # + Jarvis deterministic patterns
│   ├── taxonomy.py             # + "jarvis" route + JARVIS_INTENTS
│   ├── bilingual.py            # UNCHANGED
│   └── safety_gate.py          # UNCHANGED
├── memory/                     # MAJOR UPGRADE
│   ├── manager.py              # + Episodic + Semantic layers
│   ├── context.py              # + agent metadata in turns
│   ├── user_model.py           # + auto-preference inference
│   ├── reflection.py           # NEW: correction learning
│   ├── rules_engine.py         # NEW: "when X do Y" rules
│   └── safety.py               # UNCHANGED
├── skills/                     # ENHANCED
│   ├── dispatch.py             # + Jarvis intents
│   ├── jarvis.py               # NEW: agent orchestration stubs
│   ├── apps.py, web.py, etc.   # UNCHANGED (10 modules)
│   └── ...
├── tools/                      # MAJOR UPGRADE
│   ├── mcp.py                  # UNCHANGED
│   ├── jarvis_registry.py      # NEW: 50+ ToolSpec definitions
│   └── jarvis_executor.py      # NEW: tool dispatch (refactored)
├── training/                   # NEW PACKAGE
│   ├── feedback.py             # User rating loop
│   ├── correction.py           # Learn from corrections
│   ├── curriculum.py           # Structured learning
│   └── policy.py               # Behavior policy
├── vision/                     # ENHANCED
│   ├── runner.py               # UNCHANGED
│   ├── hand.py                 # UNCHANGED
│   ├── eye.py                  # + eye tracking
│   └── face_auth.py            # NEW: face recognition
├── prompts/                    # ENHANCED (8+ new from JARVIS)
├── www/                        # UNCHANGED (HUD orb, system monitor, etc.)
├── tests/                      # EXPANDED: 220+ tests
├── control/                    # DELETED
└── (other dirs)                # UNCHANGED
```

---

## 6. Risk Register

| Risk | Prob | Impact | Mitigation |
|------|:----:|:------:|------------|
| Claude Opus 4.8 API breaking changes (sampling params deprecated) | Low | High | Use `thinking={"type": "adaptive"}` + `output_config={"effort": ...}`. Opus 4.8 docs are stable. |
| ReAct planner latency >10s per step | Med | Med | Timeout per step (30s), max steps (10), interruption. |
| Vector memory search slow | Med | Low | sentence-transformers on-demand, cache results. |
| Semantic/episodic memory overlap | Med | Low | NEXI unified manager deduplicates at entry. |
| Test regression from modified files | High | Med | CI gate: all 137 original tests must pass FIRST. |
| Scope creep (adding more JARVIS features) | High | High | Strict phase gates: no Phase 3 until Phase 2 tests all green. |
| Anthropic SDK changes between versions | Low | Medium | Pin `anthropic>=0.70.0` in requirements. Abstract behind BrainProvider interface. |

---

## 7. Complete Timeline

```
Week 1:   Phase 1 — Foundation (taxonomy, config, router)
Week 2:   Phase 2 — Tools (registry, executor, function calling)
Week 3:   Phase 3 — ReAct Planner
Weeks 4-5: Phase 4 — Advanced Memory + Reflection + Rules
Week 6:   Phase 5 — Training & Learning
Week 7:   Phase 6 — Vision (eye tracking, face auth)
Week 8:   Phase 7 — Prompts + Streaming + Dead Code Removal
Week 9:   Phase 8 — Final Polish (220+ tests, docs, perf)
```

**Total: 9 weeks, ~40 files changed, ~220 tests, ~4500 new lines of code.**

---

## 8. Getting Started

To begin Phase 1 implementation, see `phase-1-plan.md` for detailed step-by-step with exact file changes, line counts, and test specifications.

The first command to run after Phase 1:
```powershell
python -m pytest tests/ -v --tb=short
```
All 161 tests must pass (137 existing + 24 Phase 1 new).
