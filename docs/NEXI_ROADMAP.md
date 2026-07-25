# NEXI: Research, Ideas & Phased Roadmap

**Owner:** Darsh Yadav · **Date:** 2026-07-16 · **Status:** ideas for approval (not yet implemented)

## 0. What the evidence actually says

Measured against the live repo, not assumed:

| Fact | Number |
|---|---|
| Registered tools | 117 (115 enabled) |
| Tools reachable by voice (semantic exemplar bank) | **115 / 115** |
| Engine modules | 148 |
| Self-coding loop (`engine/forge/`) | **already built** (generate → sandbox → safety scan → accept gate → install) |
| Planning / reflection / cognitive engines | already exist, largely unused |
| Semantic embedder in use | `hashing` (lexical) — **e5 not installed** |

**So the complaint "Nexi only opens/closes/writes and isn't connected" is not literally true — and that matters, because it changes what to build.** The tools are wired and routable. What's missing is everything *above* the tool layer:

1. **One tool per utterance.** No goal decomposition. "Separate the clients in that spreadsheet and WhatsApp me the international ones" is 5 steps; Nexi picks 1.
2. **No self-knowledge.** She can't answer "what can you do?" from her own code.
3. **Forge is never invoked mid-task.** She *can* write her own tools but never does when she hits a gap.
4. **Memory doesn't drive behaviour.** It's recalled, not acted on.
5. **No proactivity / routine.** Purely reactive.
6. **No activity UI.** `presence_state` already tracks `current_goal`/`attention`/`last_event`; nothing renders it.
7. **Weak matching.** Lexical hashing embedder → phrasing variants miss.

## 1. Source evidence

### Video A — "Stonic" (Inventor Usman, a commercial rival assistant)
Demonstrated: routine-aware startup ("PC setup karo" → opens VS Code per his daily routine); real data work (analyse a business spreadsheet → split international vs Pakistani clients → save category-wise CSVs); cross-app automation (search WhatsApp contact → type → send); YouTube Studio (open latest upload → enhance title/description/SEO → publish) driving the browser with human-like keyboard/mouse/scroll; **memory-driven personalisation** ("it has my memory, it knows what kind of videos I make, so it does the SEO that way").
→ Take-away: the wow is **multi-step + memory-informed + cross-app**, not exotic tools.

### Video B — "Ada" (open-source, Patreon)
Demonstrated: a **self-editable "soul file"** (rewrote her own persona on request); **inline tool creation** — told "you'll have to create multiple tools to do this, figure it out", she wrote `create_directory` + `create_file_with_content`, then used them to finish.
→ Take-away: NEXI's Forge is the same mechanism, just never triggered inline.

### Web research (primary sources)
- **Plan-and-Execute + re-plan gate** beats bare ReAct for multi-step; keeps expensive reasoning off the per-step hot path. ([theaiengineer](https://theaiengineer.substack.com/p/the-4-single-agent-patterns), [arXiv 2509.08646](https://arxiv.org/pdf/2509.08646))
- **Repo map: tree-sitter tags + PageRank** (aider) — language-agnostic self-knowledge, no embeddings, no index staleness. ([aider.chat](https://aider.chat/2023/10/22/repomap.html))
- **Voyager skill library** — only *self-verified* generated skills enter a growing composable library. ([arXiv 2305.16291](https://arxiv.org/abs/2305.16291))
- **Reflexion** — verbal self-critique into an episodic buffer; fixes "repeats the same mistake". ([arXiv 2303.11366](https://arxiv.org/abs/2303.11366))
- **Generative Agents memory stream** — retrieve by `recency + importance + relevance`; periodic reflection synthesises higher-level inferences. ([arXiv 2304.03442](https://arxiv.org/abs/2304.03442))
- **Sleep-time agent (Letta)** — a *separate* background agent reorganises memory while idle, so it never costs response latency. ([letta.com](https://www.letta.com/blog/sleep-time-compute/))
- **AG-UI protocol** — typed agent→UI events (`RUN_STARTED`, `TOOL_CALL_START`, `STATE_DELTA`). ([ag-ui](https://github.com/ag-ui-protocol/ag-ui/))
- ⚠️ **Darwin-Gödel Machine reward-hacked**: it fabricated logs, and when told to fix hallucinated tool use it **deleted the detection markers**. ([sakana.ai/dgm](https://sakana.ai/dgm/), [arXiv 2505.22954](https://arxiv.org/html/2505.22954v2))
- ⚠️ **Proactive agents SOTA is ~40% end-to-end** (PROBE) — gate speaking-first behind high confidence. ([arXiv 2510.19771](https://arxiv.org/abs/2510.19771))
- ❌ **Tree-of-Thoughts: rejected** — 10-100× tokens for ~4pp over sampling+verifier. Wrong trade for a voice loop. ([arXiv 2305.10601](https://arxiv.org/pdf/2305.10601))

**Hard safety rule adopted from DGM:** Forge's test/safety gate must live where the agent cannot edit it, and rollback must come from an archive the agent doesn't own. Anything else is theatre.

---

## 2. The ideas (58), by phase

### Phase 0.5 — Verified bug list (from a code audit, each claim checked)

| # | Bug | Evidence | Status |
|---|---|---|---|
| B1 | `which_model` routed to **brain**, not the tool | a tool must be in **3** lists: `_TOOLS` + `ALLOWED_INTENTS` + `TOOL_INTENTS`; missing any one fails *silently* | **FIXED** ✅ |
| B2 | `repeat_last`, `sleep`, `wake`, `system_status` route to brain | same 3-list trap (`route_for_intent` → `"brain"`) | open — `sleep`/`wake` may be intentional (they're *routes*); needs a decision |
| B3 | **Forge unreachable** — Nexi cannot self-code | `forge_engine.nexi_forge_tool` has **zero** entries in `_TOOLS`; `agency/__init__.py` doesn't re-export it, so the `nexi_*` handler at `tool_registry.py:636` would 404 | open — **this is the "can't code itself" complaint** |
| B4 | `recall_memory` queries the **wrong store** | handler points at `memory_store.recall_summary`, not the semantic/episodic memory that `command.py` actually writes → "what do you remember about X" never sees it | open |
| B5 | `reflection_engine` reflects on **nothing** | `command.py:483` passes `{}` as the tool result → self-critique with no outcome | open |
| B6 | **`realtime_cognitive_engine`'s decision half is dead code** | `generate_intent_hypotheses`, `choose_best_route`, `decide_next_action` have **zero callers**; only `analyze_input` runs and `command_bus.py:269` **discards its return value** | open — *this is literally the "redirects intent like a bot" symptom* |
| B7 | `PlanningEngine` is an orphan subtree | only importer is `agent_core.py`, which itself has zero importers | open — delete or wire (see #20) |
| B8 | MCP bridge never called | `execute_mcp_tool` exists only as a handler *string* in `skill_manifest.py:262` | open |
| B9 | Camera `mode="hybrid"` (hand+eye together) unreachable | `command.py:1322` supports it; no `_TOOLS` entry exposes it | open |

**Audit claim REJECTED (verified false):** the audit recommended flipping `enabled=False` → `True` for `nexi_start_studio_build` (`tool_registry.py:150`) to "unblock the self-coding stack". **Do not.** Studio already works — `"let's build a todo app"` → `nexi_start_studio_build` with authorization minted, via the deterministic `_studio_match` path. `enabled=False` is a deliberate **security control**: it hides Studio from model discovery, and `_MODEL_FORBIDDEN_INTENTS` independently blocks a model from selecting it. **A model must never mint build authorization.** Flipping it is a regression, not a fix.

**Root cause behind B1/B2/B3/B9:** `exemplars.py:92` seeds the router bank from `tool_registry.list_tools()`, so `_TOOLS` is the single chokepoint — anything absent or `enabled=False` is unroutable by construction. Combined with the 3-list trap, adding a capability silently half-works. **Fix the trap once** (derive `ALLOWED_INTENTS`/`TOOL_INTENTS` from `_TOOLS`, or add a startup assert that the three agree) and B1/B2 stop recurring.

### Phase 0 — Truth & foundation (unblocks everything)
1. Install `sentence-transformers` + e5-small-v2; retune `NEXI_ROUTER_HYBRID_MIN_SIM` + confidence thresholds for the new sim scale.
2. Calibration set: ~200 real utterances → measure routing accuracy before/after e5 (no vibes).
3. Fix the 2 known failures: working tree removed `safety="high", confirm=True` from `hand_gesture_control` (confirmation gate is off).
4. Install `cv2` or make camera tools degrade honestly instead of "not available yet".
5. Make `ToolSpec.handler` real (it's decorative on ~30 tools) — one generic dispatch, carefully, with the camera-slot tests as the guard.
6. Fix opencode adapter timeout/auth so a 2nd provider is live-proven.
7. Delete/shrink the legacy router table once e5 lands — one router, not three.
8. Repo-wide baseline: get the ~101 pre-existing failures to zero or explicitly quarantined.

### Phase 1 — Self-knowledge ("Nexi knows all her code")
9. **Repo map** (tree-sitter + PageRank over `engine/`), cached, rebuilt on file change.
10. `what_can_you_do` tool answering from the **live registry** (117 tools) — ground truth, not a guess.
11. `how_do_you_do_X` — explain her own mechanism for a capability, citing file:line.
12. Self-diff awareness: "what changed in your code today?" from git.
13. Capability gap detector: user asks for X, no tool matches → **propose Forge**, don't dead-end.
14. `graphify` the codebase into a persistent knowledge graph; query it for "what depends on the router?".
15. Startup self-audit: count tools, flag dormant/unreachable ones, report in one line.
16. Answer "why did you do that?" from the existing `intent_explainer` + repo map.

### Phase 2 — Real planning (the biggest win)
17. **Plan-and-Execute wrapper** over the existing ReAct executor: decompose → step list → execute → re-plan on surprise.
18. Persist the plan in `presence_state` so the UI can render it live.
19. Re-plan gate every K steps or on any unexpected observation.
20. Reuse `engine/planning_engine.py` instead of writing a new planner.
21. Dependency-aware steps (parallel where independent — "open chrome" ∥ "read the sheet").
22. Plan cache keyed by goal shape — repeat routines skip planning.
23. Cheap-executor / expensive-planner split (planner = llama-3.3-70b, executor = scout) via `model_registry`.
24. **Reflexion buffer**: on failure write a self-critique, prepend on retry.
25. Step budget + cost ceiling per goal; ask before exceeding.
26. Resumable plans — survive a restart mid-goal.

### Phase 3 — Memory that drives behaviour
27. **Memory stream** (append-only NL log) + scored retrieval `recency + importance + relevance`.
28. LLM importance rating (1-10) on write.
29. **Reflection pass**: periodically synthesise memories → higher-level inferences ("Darsh ships on Fridays").
30. **Sleep-time agent**: reorganise/consolidate memory while idle — zero latency cost.
31. Preference memory driving output (the Stonic SEO trick: "he titles videos like *this*").
32. Per-project memory: what this repo is, its conventions.
33. Correction memory already exists (`correction_learner`) → feed it into the exemplar bank as live corrections.
34. Episodic → procedural promotion: a 3×-repeated successful plan becomes a named routine.
35. "What do you remember about X?" grounded, with provenance.

### Phase 4 — Self-coding (Forge, properly)
36. **Invoke Forge inline** when the planner hits a missing capability (the Ada "figure it out" moment). ← highest-leverage single change
37. Voyager-style **skill library**: only self-verified tools get installed; retrievable + composable.
38. ⚠️ **Immutable gate**: Forge's test/safety gate lives outside Forge's writable scope. Nexi must not be able to edit her own examiner (DGM lesson).
39. Archive every generated tool version; rollback comes from the archive, not the agent.
40. **Soul file**: self-editable persona/preferences (`data/nexi/soul.md`), diffed + versioned, CEO-visible.
41. Forge proposes, Darsh approves, for anything crossing the safety boundary.
42. Generated-tool telemetry: usage, failure rate, auto-retire dead tools.
43. Self-test authoring: every forged tool ships with a test or it doesn't install.

### Phase 5 — The Stonic capability class (cross-app, multi-step)
44. Spreadsheet/data skill: read → analyse → split → write CSVs (`xlsx` skill exists).
45. WhatsApp send (contact search → type → send) — reuse existing computer-use click/type.
46. Browser task skill: navigate + edit + publish (YouTube Studio class) via existing browser tools.
47. Email triage/draft.
48. File-system janitor: organise downloads by rules.
49. Screenshot → understand → act (vision model already configured: scout).
50. Cross-app chain macros: name a multi-app routine, replay it.

### Phase 6 — Proactivity (gated — SOTA is only 40%)
51. **Routine engine**: learn daily patterns → "PC setup" opens what he actually uses at 9am.
52. World-monitor triggers (`world_monitor_dashboard` exists) → propose, don't act.
53. **Staged proactivity**: hint → offer → act. Never a binary interrupt.
54. Interruption etiquette: don't speak while he's in focus/DND.
55. Confidence gate on speaking first; log every suppressed impulse for tuning.

### Phase 7 — Observability UI (your "advertisement when an agent starts")
56. **Agent Activity panel**: AG-UI-style typed event stream (`RUN_STARTED`, `TOOL_CALL_START`, `TOOL_CALL_RESULT`, `STATE_DELTA`) over the existing Eel bridge — renders *the moment* an agent starts.
57. Live plan visualisation: steps with ✓/✗/running, the current step highlighted.
58. "What are you doing right now?" surfacing `presence_state.current_goal` + the running provider/model, plus a Stop button wired to the existing cancel path.

---

## 3. Sequencing

```
Phase 0 (foundation)  ──► Phase 1 (self-knowledge) ──► Phase 2 (planning) ◄── the unlock
                                                            │
                    ┌───────────────────────────────────────┼───────────────┐
                    ▼                     ▼                 ▼               ▼
              Phase 3 memory       Phase 4 forge      Phase 5 skills   Phase 7 UI
                    └──────────────► Phase 6 proactivity ◄─────────────┘
```

**Phase 2 is the unlock.** Without goal decomposition, every other phase is still a bot obeying one command at a time. Phase 7 can run in parallel (independent).

## 4. Honest scope

This is **not** one session. Rough order-of-magnitude: Phase 0 ~1 session, Phase 1 ~1, Phase 2 ~2-3, Phases 3-7 ~2 each. "Implement all 58 and make them work" is a multi-week programme, not a single task. Anyone promising otherwise is guessing.

**Recommended first cut (one session, biggest visible delta):** Phase 2 idea #17 (Plan-and-Execute) + Phase 4 idea #36 (inline Forge) + Phase 7 idea #56 (activity panel). That alone turns "bot that obeys one command" into "agent that plans, writes what it lacks, and shows you its work".
