# NEXI Autonomy — 52 research-grounded ideas (ideas #59-110)

Extends `NEXI_ROADMAP.md` (ideas #1-58). Every mechanism below is from a
primary source, tagged **PROVEN** or **EXPERIMENTAL**. Ordered by ROI.

**Latency budget rule (voice): ~1s.** So: *think offline, cascade online.* Anthropic's
own numbers put multi-agent reasoning at ~15× the tokens of a chat turn — unaffordable
in the serve path. Deliberation belongs in sleep-time.

---

## A. Fix "you say one thing, it detects another" (highest ROI)

| # | Idea | Why | Source |
|---|---|---|---|
| 59 | ✅ **DONE** **Tool-RAG (RAG-MCP)**: retrieve a candidate tool subset via the existing e5 index *before* the LLM sees any tool list. **Shipped + measured: 35,380→4,092 chars (88% smaller), 12/12 recall.** `_rag_filter_capabilities`, `NEXI_TOOL_RAG_TOPK=12`, tests/test_tool_rag.py | **3.2× tool-selection accuracy (43.1%→13.6%)**, ~50% fewer prompt tokens. NEXI has 117 tools and already has the e5 index — this is hours of work | [RAG-MCP](https://arxiv.org/abs/2505.03275) **PROVEN** |
| 60 | **Negative exemplars from corrections**: when the user rephrases/corrects within N seconds, log `(utterance, wrong_route, right_route)` into the e5 index | Directly attacks misrouting; `correction_learner` already exists | derived **PROVEN-ish** |
| 61 | **Adaptive-RAG classifier**: route each utterance to no-retrieval / single-hop / multi-hop | "Know when to search vs answer" as a *classifier*, not an LLM call — protects the 1s budget | [Adaptive-RAG](https://arxiv.org/abs/2403.14403) **PROVEN** |
| 62 | Confidence-gated **model cascade** (small→large) wired into `model_registry.select_model` | Escalate only when confidence < threshold | [speculative cascades](https://research.google/blog/speculative-cascades-a-hybrid-approach-for-smarter-faster-llm-inference/) **PROVEN** |
| 63 | **Tool-description QA agent** — an agent that tests each tool and rewrites bad descriptions | Anthropic measured **40% task-time reduction**; NEXI's 117 descriptions were hand-written and drive the e5 bank | [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system) **PROVEN** |
| 64 | Calibration set of ~200 real utterances; measure routing accuracy before/after every router change | e5 sims are 0.84-0.95 — thresholds must be tuned on data, not vibes | — |

## B. Self-learning from its own use

| # | Idea | Why | Source |
|---|---|---|---|
| 65 | **Agent Workflow Memory**: induce reusable *workflow templates* from successful ReAct traces; retrieve to guide planning | The single highest-ROI autonomy build. NEXI already emits trajectories | [AWM](https://arxiv.org/abs/2409.07429) **PROVEN** |
| 66 | **Memp procedural memory** with Build/Retrieve/**Update** — including *deprecating* stale procedures | The Update phase is what stops memory rotting | [Memp](https://arxiv.org/abs/2508.06433) **PROVEN** |
| 67 | Distil with the **120b** tier, execute with the **20b/scout** tier | Memp: procedural memory from a strong model transfers to a weaker one | [Memp](https://arxiv.org/abs/2508.06433) **PROVEN** |
| 68 | **ExpeL insights**: store distilled *lessons*, not raw logs | Distilled heuristics transfer better than trajectories | [ExpeL](https://arxiv.org/abs/2308.10144) **PROVEN** |
| 69 | **ACE delta-updates** (ADD/UPDATE/REMOVE) to memory — never a full rewrite | Prevents **context collapse** + **brevity bias**; +10.6% on agents | [ACE](https://arxiv.org/abs/2510.04618) **PROVEN** |
| 70 | **Outcome-gating**: only admit traces the verifier passed into memory | Stops error propagation / misaligned replay | [ACE](https://arxiv.org/abs/2510.04618) **PROVEN** |
| 71 | **GEPA-style reflective prompt evolution** instead of RL | Sample-efficient; NEXI sees dozens of traces/day, not millions | [GEPA](https://arxiv.org/abs/2507.19457) **PROVEN** |
| 72 | Promote a 3×-repeated successful plan into a **named routine** | Procedural memory, cheaply | derived |
| 73 | Reflexion buffer on failure → prepend on retry | Cheap; fixes "repeats the same mistake" | [Reflexion](https://arxiv.org/abs/2303.11366) **PROVEN** |
| 74 | ❌ **Do NOT build RL/Search-R1** (needs GPU + reward signal) or **SEAL** weight-level self-edits (destroys auditability) | Ruled out deliberately | [Search-R1](https://arxiv.org/abs/2503.09516), [SEAL](https://arxiv.org/abs/2506.10943) **EXPERIMENTAL** |

## C. Sleep-time compute — think while idle (the key unlock)

| # | Idea | Why | Source |
|---|---|---|---|
| 75 | **Sleep-time agent**: a second agent that pre-reasons over raw context into learned context while the PC is idle | **~5× less serve-time compute, latency untouched.** The machine is idle 95% of the day | [sleep-time](https://arxiv.org/abs/2504.13171) **PROVEN** |
| 76 | Run AWM/Memp/ACE distillation **in the sleep job** | Zero user-facing latency cost | [Letta](https://www.letta.com/blog/sleep-time-compute/) **PROVEN** |
| 77 | Nightly: re-index e5 exemplars, retire dead tools, consolidate memory | Idle work that compounds | derived |
| 78 | Nightly self-audit: "which routes did I get wrong today?" → surface to CEO | Self-understanding, offline | derived |
| 79 | Pre-compute the morning routine (Stonic's "PC setup karo") during idle | Feels proactive, costs nothing at 9am | derived |

## D. Self-developing (Forge) — and its real failure mode

| # | Idea | Why | Source |
|---|---|---|---|
| 80 | **Forge curriculum**: Nexi proposes her own next capability | Voyager's automatic curriculum — the missing half of Forge | [Voyager](https://arxiv.org/abs/2305.16291) **PROVEN** |
| 81 | **Skill composition**: new forged tools build on already-installed ones | Capability compounds; skills are code, so no catastrophic forgetting | [Voyager](https://arxiv.org/abs/2305.16291) **PROVEN** |
| 82 | ⚠️ **Held-out eval the generator never sees** — the gate must NOT be the only judge | **73.8% of self-improving code experiments reward-hacked** (proxy gains, no real gain). Assume Forge will game its gate | [reward hacking](https://arxiv.org/abs/2510.04399) **PROVEN FAILURE** |
| 83 | ⚠️ **Archive + one-command rollback** (DGM pattern), not a single lineage | Every self-mod traceable/revertible | [DGM](https://arxiv.org/abs/2505.22954) |
| 84 | ⚠️ **Hard allowlist on paths Forge may write.** Never its own gate, never the router | Bounds capability drift | [survey](https://arxiv.org/abs/2507.21046) |
| 85 | Forge telemetry: usage + failure rate → auto-retire dead tools | Keeps the library honest | derived |
| 86 | Every forged tool ships a test or it doesn't install | Already true — keep it | — |
| 87 | Self-verification loop: execution feedback → iterative fix (already in Forge's retry) | Voyager's core loop | [Voyager](https://arxiv.org/abs/2305.16291) |

## E. Web search that actually works

| # | Idea | Why | Source |
|---|---|---|---|
| 88 | **CaMeL quarantine**: privileged LLM plans from the *trusted* utterance only; a quarantined LLM reads fetched pages with **NO tool access** | **Non-negotiable** — Nexi runs local code. 67% of AgentDojo tasks *provably* secure | [CaMeL](https://arxiv.org/abs/2503.18813) **PROVEN** |
| 89 | Accept that **prompt injection is not solvable** — design for containment, not prevention | OpenAI/Anthropic/DeepMind all conceded this in 2025 | [CaMeL](https://simonwillison.net/2025/Apr/11/camel/) |
| 90 | **Query decomposition + stateful multi-hop** (hop N sees hop N-1's reasoning) | Real research, not one-shot search | [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system) **PROVEN** |
| 91 | Teach **heuristics not rules**: decompose, judge source quality, shift depth-vs-breadth | Anthropic's production lesson | same **PROVEN** |
| 92 | Reflect/critique pass: relevance, citation support, hallucination check | — | same |
| 93 | `@lru_cache`/sqlite on (normalized_query → results) with TTL | Boring; nothing publishable needed | derived |
| 94 | Budget awareness: token use explains **80%** of performance variance (~15× a chat turn) — cap it | Don't let research runaway | [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system) |

## F. Using MCP / plugins / skills autonomously

| # | Idea | Why | Source |
|---|---|---|---|
| 95 | **Code execution with MCP**: expose each MCP tool as a *file*; agent lists the dir and reads only what it needs | **150k → 2k tokens (98.7%)**; state persists across calls | [Anthropic](https://www.anthropic.com/engineering/code-execution-with-mcp) **PROVEN** |
| 96 | **MCP-Zero**: the model *declares a capability gap* and requests a tool, instead of being handed a menu | This is literally "Nexi decides to use an MCP server" — accurate selection from ~3k candidates, 98% token cut | [MCP-Zero](https://arxiv.org/abs/2506.01056) **EXPERIMENTAL** |
| 97 | Hierarchical routing: server → tool | Scales past 100 tools | [MCP-Zero](https://arxiv.org/abs/2506.01056) |
| 98 | **Wire `mcp_tool_bridge.execute_mcp_tool`** — it exists but is only a handler *string*, never called | Dormant capability | audit |
| 99 | Capability-gap → **Forge** (write the tool) or **MCP** (find the tool): one decision point | Unifies self-coding with tool discovery | derived |
| 100 | Trust policy per MCP server (source, permissions, network, secrets) before use | Governance already specified in the Studio spec | — |

**Note:** >100 tools = RAG-MCP (retrieve) + progressive disclosure (load) + MCP-Zero (request). They **compose**; they are not alternatives.

## G. Voice latency (measured, not guessed)

| # | Idea | Why | Source |
|---|---|---|---|
| 101 | **Stream LLM → TTS at clause boundaries** — don't wait for the full generation | The single biggest voice-latency recovery | [ElevenLabs](https://elevenlabs.io/blog/voice-agent-latency-optimization) **PROVEN** |
| 102 | ✅ **DONE**: trim leading silence before ASR upload (362KB→68KB, 5.4×) | Upload dominated the ASR round-trip | measured |
| 103 | ✅ **DONE**: post-wake 1000→300ms, trailing silence 1500→800ms | ~1.4s/turn | measured |
| 104 | ❌ **Do NOT switch to whisper-turbo** — measured *slower* (1990ms vs 1050ms) | Upload-bound, not inference-bound | measured |
| 105 | **PredGen**: speculate on the utterance while the user is still speaking | Fits the wake/ASR pipeline; unproven outside the paper | [PredGen](https://arxiv.org/abs/2506.15556) **EXPERIMENTAL** |
| 106 | ✅ **DONE** Warm the e5 router in a background thread | It was **83s**, not 3s — and it ran INSIDE the voice turn in the UI process, freezing the UI and hanging on "thinking". Never build a model in the hot path | measured |

## H. Proactivity (gated — SOTA is only ~40%)

| # | Idea | Why | Source |
|---|---|---|---|
| 107 | **Staged proactivity**: hint → offer → act. Never a binary interrupt | Poorly-timed interruptions have real cognitive cost | [PROBE](https://arxiv.org/abs/2510.19771) |
| 108 | Confidence gate on speaking first; log every suppressed impulse for tuning | Ship it gated, not autonomous | [PROBE](https://arxiv.org/abs/2510.19771) |
| 109 | Routine learning from episodic memory → the "PC setup" moment | Stonic's headline demo | video |
| 110 | Don't speak during focus/DND | Etiquette > capability | derived |

---

## Build order (what I'd actually do)

1. **#59 Tool-RAG** over the existing e5 index — hours of work, 3.2× selection accuracy, fixes the #1 complaint.
2. **#61 Adaptive-RAG** search-vs-answer classifier — protects the latency budget.
3. **#75+#65 Sleep-time distillation** (AWM + ACE deltas) — reuses the trace store, zero serve latency.
4. **#88 CaMeL quarantine** — before any web text nears a tool-calling context.
5. **#82/#83 Forge held-out eval + rollback archive** — assume reward hacking.

**Deliberately skipped:** RL/SEAL (no GPU, kills auditability), Tree-of-Thoughts (10-100× tokens for ~4pp), full multi-agent orchestration in the serve path (15× tokens).

---

## I. Borrowed from Vivek Mishra's "Agentic OS" (video `tzAzfOW-ZsM` + repo `agentic-os-personal`), 2026-07-17

That project is a **server-hosted Node.js web dashboard**, not a desktop voice agent. NEXI is
**far ahead** of it on: wake-word, the real desktop voice loop, screen vision (now real),
Forge self-coding, the tiered intent router, Studio supervision, model_registry, and security
hardening. It has **no** wake-word, no real desktop control, no self-improvement, no local
models. But four things it does are genuinely worth borrowing — none shadow an existing NEXI
feature (see [[nexi-jarvis-no-shadow]]):

| # | Idea | Why it's worth taking | Status |
|---|---|---|---|
| 111 | **Content pipeline**: research → generate (text+image) → schedule → publish to Instagram/LinkedIn/X. Firecrawl+Perplexity for research (via OpenRouter), an image model for visuals, a social API (Zerno-style) for posting | A cohesive *product* NEXI lacks. NEXI has web-search IDEAS (#88-93) but no generate-and-publish loop. High user-visible value | NEW — not built |
| 112 | ✅ **DONE — free-first, self-healing, per-runtime model selection** (Darsh's corrected spec). NOT a paid OpenRouter default. Built: (a) `agent_runtime/model_policy.py` — each runtime switches within its OWN pool (claude-code: Sonnet/Opus/Fable/Haiku; opencode/Hermes/OpenRouter: FREE models), free-first, task-mapped, a task resolves to a CHAIN not one model, no gemini-2.5-flash default; (b) `agent_runtime/model_health.py` — a failed run benches the model (N failures → cooldown) so selection skips it and picks the next best, a success clears it (the "remove it, use another" rule); (c) `agent_runtime/model_discovery.py` — LIVE free-model discovery from OpenRouter's `/api/v1/models` (no hardcoding — providers add/remove free models), cached + non-blocking hot-path read + background warm; (d) `openrouter_provider.py` + `model_registry.endpoint_for()`. **26 tests** (model_policy/health/discovery/openrouter). OpenRouter key = FREE models only | EXACTLY "NEXI must change any model per task, free-only, self-heal on failure, no hardcoding". opencode takes an API key only (a Claude token is not an API key). Maps to #62 | ✅ DONE 2026-07-18 |
| 118 | ✅ **DONE — live model discovery** (no hardcoding): read what's free from the provider catalogue at runtime; static pool is offline fallback only | Providers remove free models; a hardcoded id 404s. Proven: OpenRouter's real free set is `cohere/north-mini-code:free`, `nvidia/nemotron-3-ultra:free`, `poolside/laguna:free` — none guessable | OpenRouter `/api/v1/models` |
| 119 | ✅ **DONE — self-healing model health**: bench a model on failure, auto-fall-back, recover after cooldown | "If a model fails, remove it and use another" — no manual edits | derived |
| 120 | **Benchmark-informed routing** (the "Sakana Fugu" idea): `model_discovery.research_task_models()` surfaces free candidates per task from live discovery + a benchmark note. FULL per-task web-benchmark research is kept OFF the voice hot path (too slow); it runs on-demand for hard tasks / in Studio | Route "code" work to a coding model, "orchestration" to a reasoning model, from what's actually free now | [Sakana AI](https://sakana.ai/) partial |
| 113 | **Scheduled background research feed** — a cron job ("every 6h") scrapes sources, ranks by niche relevance, builds a reviewable feed | Real autonomy that costs nothing at serve time — fits the sleep-time-compute thesis (#75). NEXI has no scheduler for self-directed research | NEW — not built |
| 114 | **Skills-file + AGENTS.md driven build** — the whole OS was built by prompting Cursor/Claude Code with a skills dir | NEXI already does this via its Claude Code integration ([[nexi-claude-code]]) — parity, not a gap. Confirms the approach | already have |

## J. Self-improving models (the "model that builds a better model" idea)

Darsh recalled a video about a neural network that self-develops / a model that creates a
better model. **That is NOT in the `tzAzfOW-ZsM` video** (checked: zero hits for neural/MLP/
self-improve/evolve). The real concept is:

| # | Idea | Why | Source |
|---|---|---|---|
| 115 | **Darwin Gödel Machine**: an agent rewrites its OWN code, keeps a change only if it beats a held-out benchmark; archives every version. SWE-bench 20%→50% | This is precisely what NEXI **Forge** already does (generate→sandbox-test→gate→install). The missing DGM pieces are the **archive + one-command rollback (#83)** and **curriculum (#80)** — already listed above | [DGM](https://arxiv.org/abs/2505.22954) **PROVEN** |
| 116 | **AlphaEvolve-style**: evolutionary search over code variants, judged by a real metric, to optimize a component | Applies to NEXI's own hot paths (router thresholds, wake tuning) — but needs a real metric harness first (#64 calibration set) | [AlphaEvolve](https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/) **PROVEN** |
| 117 | ⚠️ **Model-training-a-model (MLP/hypernetwork) is NOT worth it here** — needs a GPU, a reward signal, and destroys auditability (same reason SEAL #74 is ruled out). NEXI's self-improvement should stay at the CODE level (Forge/DGM), where every change is reviewable and revertible | Avoids the 73.8% reward-hack trap (#82) | [DGM](https://arxiv.org/abs/2505.22954) |

**Bottom line for Darsh:** NEXI already has the *self-improving* foundation (Forge = a
Darwin Gödel Machine at the code level). The highest-ROI borrow from the video is **#112
OpenRouter**, which directly delivers your "switch any model per task" across every model —
that's the one to build next.
