# Master Intent Router — Design Spec

**Date:** 2026-07-13
**Status:** Approved for planning (owner said "just build this")
**Owner goal, verbatim:** *"understand anything I say, in any style, instantly… feel like a real Jarvis, not a trashed board."*
**Why it matters:** this router is the front door to the whole "Jarvis writes/updates code on its own" system (Nexi Studio). If the engine is weak, nothing downstream succeeds.

---

## 0. Plain-language summary (read this first)

Today NEXI decides *what you meant* by throwing your words at one cloud model and hoping. It's actually **four half-finished routers fighting each other**, with **three different pieces of code disagreeing about how sure it is** — so the same sentence lands differently depending on timing. That's why "you say one thing, it detects another."

The fix is a **tiered brain**, cheapest-first:

- A **fast local layer** (runs on your machine, ~20ms, no internet) recognises the everyday stuff instantly by *meaning*, not keywords — so it doesn't matter how you phrase it.
- A **medium model** (gpt-oss-20b) handles the ambiguous middle in ~1 second.
- A **strong model** (gpt-oss-120b) is pulled in *only* for genuinely hard requests.

Two decisions that are currently mashed into one get **split apart**: first *"are you telling me to DO something, or just talking?"* (this alone kills "it acted when I was chatting"), then *"which tool does this go to?"*. It **asks instead of guessing** when unsure, **confirms** before anything destructive, and **learns your phrasing every time you correct it**. And we **measure** how often it's wrong against a list of real phrasings, so tuning is numbers, not vibes.

---

## 1. The problem (grounded in the current code)

Source: full code map of `engine/groq_intent_router_v2.py`, `engine/command.py`, `engine/tool_registry.py`, `engine/intent_taxonomy.py`, and siblings.

1. **Four parallel router generations coexist**, with open/search/camera logic copy-pasted in 3 places: `groq_intent_router_v2._deterministic_router` (active), `groq_intent_planner._deterministic_classify` (legacy, still used by `workflow_dialog_manager`), `tool_registry.select_tool` (a second deterministic picker), plus legacy `intent_router.route_intent` and `intents.REGISTRY` (a *different* name space). Most is dead on the happy path but reachable on error — can't be deleted blindly.
2. **Three disagreeing confidence authorities**: the prompt (`<0.65 → clarify`), `route_intent_v2` (`>=0.6` accept), and `confidence_manager.should_clarify` in `_finalize`. Same phrase can route differently depending on which fires.
3. **Nondeterminism**: `GROQ_INTENT_COOLDOWN_SECONDS=0.5` silently skips the LLM on quick repeats → identical utterance routes two different ways.
4. **No WHEN/WHERE split.** There is no "act vs talk" gate. A confident LLM tool guess executes with **no cross-check** (only Studio is protected) → *acts when you're talking*. Any unmatched 2+ word phrase falls through to Gemini chat → *a misheard command gets answered instead of clarified*.
5. **Keyword-brittle routing** → poor tolerance to varied phrasing, ASR slips, and Hinglish.
6. **Maintainability**: a **49-branch `if name == …` dispatch** in `_execute_handler`; `ToolSpec.handler` ("module.func") is declared but **never used to execute**; adding one tool touches ~4–5 files (`_TOOLS`, `_execute_handler`, both `ALLOWED_INTENTS` and `TOOL_INTENTS`, plus a deterministic matcher).
7. **Safety gaps**: `type_text`, `click_ui_element`, `browser_click`, `browser_fill` are `safety="high"` but have no confirmation gate unless a `RISKY_WORDS` regex happens to match (it doesn't for "click"/"type").

---

## 2. Goals & non-goals

**Goals**
- Understand any phrasing/style/user, robustly (paraphrase, ASR noise, Hinglish/code-switch).
- Feel instant: the common case resolves locally in tens of ms; every path fires an immediate ack.
- Offline-resilient: everything below the LLM tier works with no network.
- Well-calibrated: knows when it's unsure; asks or confirms instead of misfiring; measured against a real-utterance set.
- Learns the owner's style from corrections, with no retraining.
- **One** router — a single front door — replacing the four.
- Jarvis feel: human, responsive, confident when sure, gracious when not.

**Non-goals (this spec)**
- No agent framework dependency (LangGraph/Rasa/DSPy) — patterns yes, deps no.
- No big-bang rewrite — strangler migration only.
- Not replacing the ASR, the TTS, or the Gemini answer-brain.
- NEXI-orchestrated multi-agent parallelism is a *separate* track (Studio), not this router.

---

## 3. Design principles

1. **Cheapest-first layering, fail-open downward.** Deterministic → local semantic → 20b → 120b. Each layer handles what it's sure about and passes the rest down.
2. **Separate WHEN from WHERE.** Dialogue-act gate (act/talk/unsure) is a distinct decision from tool selection. (Rasa's NLU-vs-policy split.)
3. **Confidence = agreement, not self-report.** Trust the embedding margin (top-1 − top-2) cross-checked against the LLM's answer. Do **not** threshold on a model's verbalized 0–100 or raw logprobs — research shows both are badly calibrated.
4. **Confidence × stakes, two axes.** A cheap reversible action fires at a low bar; a destructive one confirms even at high confidence.
5. **Measure, then tune.** A labeled calibration set of real utterances is the source of truth for every threshold. "3% wrong, down from 22%" — not "feels better."
6. **Learn from corrections.** Every "no, I meant X" appends that phrasing to the correct intent's exemplar bank. Personalizes immediately, no retraining.
7. **Registry is the single source of truth.** Tools, enums, exemplar seeds, and the LLM schema all derive from `tool_registry._TOOLS`. Add a tool in one place.
8. **Strangler migration, keep what works.** Preserve the Studio auth handshake, `tool_result_verifier`, `safety_gate`, and 429→offline fallback. Retire the four routers behind the new front door one route at a time, gated by the calibration set.

---

## 4. Architecture — the tiered brain

| Tier | Engine | Where | Latency | ~Traffic | Job |
|---|---|---|---|---|---|
| **0a Guards** | regex/exact rules | local | <1ms | — | stop/cancel/wake/sleep, Studio auth, "answer to my pending question", active workflow/training reply. Never sent to an LLM. |
| **0b Semantic** | `e5-small-v2` embeddings + in-RAM matrix | local | ~15–30ms | ~70–80% | match utterance by *meaning* to exemplar bank → act-vs-talk bucket + candidate intent/domain. Offline. |
| **1 Adjudicate** | **gpt-oss-20b** (Groq, low effort, JSON-schema-constrained) | cloud (local fallback) | ~1s | ~15% | resolve the ambiguous middle + conversation; fill/confirm the tool call from the **top-k retrieved tools** only. Emits `confidence`. |
| **2 Escalate** | **gpt-oss-120b** (Groq, medium effort) | cloud | ~3–5s | ~5% | genuinely hard: multi-clause, coreference ("do that again but for the other window"), tied tools, `unknown`. |
| **Offline** | local `20b` (Q4, ≤52k ctx, Ollama/llama.cpp) | local | ~2–4s | fallback | when Groq is unreachable (429-fail-fast already exists). Degrades gracefully. |

Escalation Tier 1→2 fires **only** on: low `20b` `confidence`, an `unknown`/out-of-taxonomy route, or multiple tools tie. Target ≤10–15% escalation (past ~30–40% the cascade stops paying off).

---

## 5. The A-to-Z pipeline (the flow)

```
   user speaks / types
          │
   ┌──────▼───────┐
   │ 0. NORMALIZE │  light: lowercase, strip fillers/punct, expand contractions,
   └──────┬───────┘  map common ASR/Hinglish slips. (Light only — heavy stemming loses signal.)
          │
   ┌──────▼───────┐
   │ 1. GUARDS    │  deterministic, NEVER an LLM: stop/cancel/wake/sleep, Studio build auth,
   └──────┬───────┘  reply-to-pending-question, active workflow/training answer.
     hit? │─────yes──▶ act immediately. done.
          │ no
   ┌──────▼───────┐
   │ 2. CONTEXT   │  resolve "it/that/again" & "the second one" against memory;
   │   RESOLVE    │  split "X and then Y" into ordered steps.
   └──────┬───────┘
          │
   ╔══════▼═══════════════════════╗
   ║ 3. WHEN GATE                 ║  dialogue-act: ACT? · TALK? · UNSURE?
   ╚══╦════════════╦═══════════╦══╝  (= is anything above the semantic threshold, or is this chat)
   ACT║        TALK║     UNSURE║
      │            ▼           ▼
      │        chat/brain   ask ONE clarifying question (name top-2), don't guess
      │
   ┌──▼───────────┐
   │ 4. WHERE     │  Tier-0 semantic → top-k tools within domain (tool-RAG) →
   │   ROUTE      │  Tier-1/2 LLM adjudicates, constrained to the k real tool names.
   └──┬───────────┘  → ONE confidence (embedding margin × LLM agreement)
      │
   ┌──▼───────────┐
   │ 5. SLOTS     │  fill args from utterance; a missing required slot → ask exactly for it.
   └──┬───────────┘
      │
   ┌──▼───────────┐
   │ 6. DECIDE    │  BAND POLICY (confidence × stakes):
   │ (act/confirm │   high+low-stakes → ACT · high+destructive → CONFIRM ·
   │  /ask/chat)  │   medium/ambiguous → ASK top-2 · low/OOS → CHAT
   └──┬───────────┘
      │
   ┌──▼───────────┐
   │ 7. DISPATCH  │  run via registry `handler` pointer — no 49-branch if/elif.
   └──┬───────────┘  (+ instant local ack/earcon fired back at stage 0b/1 so it feels immediate)
      │
   ┌──▼───────────┐
   │ 8. VERIFY +  │  tool_result_verifier proves it happened; guard against false-success;
   │   RESPOND    │  then speak. Stream the ANSWER, not the route.
   └──────────────┘

  cross-cutting: ▸ ONE confidence policy  ▸ calibration set → measured misroute rate → tuned knobs
                 ▸ corrections append to exemplar bank (learns your style)
```

### Stage details

**0. Normalize** — in: raw text. out: canonical text + language tag. Light normalization only; keep an untouched copy for the LLM. Absorbs ASR/Hinglish noise before matching.

**1. Guards** — deterministic hard rules that must never be reinterpreted. Reuses today's `pre_route`/`_studio_match`/`resolve_followup`. On hit, short-circuits. This is where safety-critical determinism lives.

**2. Context resolve** — the "hold a conversation" fix. Resolves anaphora/ordinals from session + episodic memory (`engine/memory/`), and splits compound commands into an ordered step list (each step re-enters the pipeline at stage 3). Replaces the brittle `_react_like(" and then ")` string check.

**3. WHEN gate** — dialogue-act classification: ACT / TALK / UNSURE. Implemented cheaply: if the semantic layer's best score clears the threshold → ACT; if it matches the "conversation" bucket or nothing clears threshold → TALK; borderline → UNSURE → ask. This single gate removes the "acted when I was talking" and "answered when I wanted an action" error classes.

**4. WHERE route** — only for ACT. Semantic layer proposes a domain + candidate intents; **tool-RAG** retrieves the top-k (~5) tools within that domain from the same embedding index (never dump all 115 into the prompt — research shows top-k ~3×'s selection accuracy). Tier-1 (or Tier-2) LLM picks among the k, **schema-constrained to those exact names + an `unknown` escape**. Confidence = embedding margin cross-checked with the LLM's pick.

**5. Slots** — extract args; validate/normalize (reuse `slot_normalizer`, `intent_validator`). Missing required slot → targeted single question (reuse `clarification_for_missing_slot`).

**6. Decide (band policy)** — the calibrated go/confirm/ask/chat decision. Confidence **and** stakes (tool `risk_level`) together choose the band. Closes the current gap where high-risk `type_text`/`click_ui_element` reach the handler ungated.

**7. Dispatch** — data-driven: resolve and call `ToolSpec.handler` ("module.func"). Retire the 49-branch chain incrementally. `safety_gate.execution_is_safe` still runs first; `tool_result_verifier` still runs after.

**8. Verify + respond** — unchanged in spirit: prove the action happened, never claim unverified success (`assistant_response.guard_unverified_action_message`), then speak; stream the answer for perceived speed.

---

## 6. Confidence & calibration policy (the heart of the fix)

**One authority.** A single `ConfidencePolicy` object is the *only* code that decides go/confirm/ask/chat. The three current disagreeing checks are deleted.

**The signal (agreement, not self-report):**
- Primary: **embedding margin** = `sim(top1) − sim(top2)` from the semantic layer.
- Cross-check: does the LLM's pick equal the semantic layer's pick? **Agree → high; disagree → low**, regardless of any verbalized score.
- Reserve N-sample self-consistency for the genuinely ambiguous middle band only (it costs N calls).

**The band policy (confidence × stakes):**

| | low stakes (open app, mute) | high stakes (delete, send, buy, shell, click/type) |
|---|---|---|
| **high confidence** | ACT silently | **CONFIRM** ("Deleting X — yes?") |
| **medium / top-2 tie** | ASK one clarifying question, naming the top-2 | ASK + confirm |
| **low / out-of-scope** | CHAT fallback (don't force a command) | CHAT fallback |

**Tuning knobs (external, workload-specific, will drift — leave them adjustable):**
- semantic accept threshold (cos ≥ ~0.75) and margin (≥ ~0.1)
- Tier-1→Tier-2 escalation confidence threshold
- per-risk-level confidence bars for the band policy

**Calibration harness:** `engine/router/calibration/utterances.jsonl` — ~100–200 real phrasings (seed from the owner's own transcripts) each tagged with the expected route/tool/band. `score.py` runs the router over the set and reports misroute rate, over-ask rate, and over-act rate. **Every threshold is tuned against this, and every migration phase must not regress it.** Baseline: measure the *current* router on this set first, so we can prove the improvement.

---

## 7. Model topology & perceived latency

- **Tier 0:** `intfloat/e5-small-v2` (33M, 384-dim, ~16ms) on CPU via `sentence-transformers`/ONNX; intent+tool vectors held in a RAM NumPy matrix (no vector DB for a few hundred entries); `@lru_cache` on the normalized utterance caches the final route, and a separate cache on the embedding avoids re-encoding seen phrases.
- **Tier 1:** gpt-oss-20b on Groq, **low reasoning effort + minimal verbosity + capped `max_tokens`** (the single biggest latency lever — CoT length, not TTFT, is what's slow), `response_format` = JSON Schema with `tool` as an **enum** of the retrieved names + `confidence` + `unknown`. Keep the schema minimal (avoid the "constraint tax" that can suppress tool-calling).
- **Tier 2:** gpt-oss-120b on Groq, medium effort, only on escalation.
- **Offline:** local 20b Q4 (≤52k context to avoid the throughput collapse) when Groq is down.
- **Perceived-latency:** fire an **instant local ack/earcon** the moment Tier 0 fires or Tier 1 is dispatched — this masks the whole route latency. Optionally speculative-execute high-confidence Tier-0 hits while 20b confirms in parallel, roll back on disagreement. Stream the *answer* TTS, never the route.

---

## 8. Data model

**Decision object** — extend the existing 14-field schema (`intent_taxonomy.empty_result()` / `SCHEMA_FIELDS`) rather than invent a new one, so `command.py` dispatch keeps working during migration. Add: `tier` (0/1/2), `stakes`, `candidates` (top-k with scores), `margin`. Keep `route/intent/domain/confidence/slots/…`.

**Intent/exemplar registry** — each routable intent carries a bank of 10–30 example phrasings. **Seeded automatically** from `ToolSpec.aliases` + `examples` in `_TOOLS`, then **grown from corrections**. Retrieved with MMR (relevance + diversity) so the bank covers paraphrase space without redundancy. Include Hinglish/mis-transcribed variants for the owner's common commands.

**Tool-RAG index** — same embedding space; tools embedded from their description+examples; top-k retrieval within a domain.

---

## 9. Learning loop (corrections → exemplars)

When the owner corrects a route ("no, I meant X"), capture `(utterance, wrong_intent, corrected_intent)` (reuse `correction_learner`) and **append `utterance` to `corrected_intent`'s exemplar bank**. No retraining — the retrieval pool grows and the router personalizes to the owner's style immediately. Highest-ROI item in the whole design and a direct, compounding attack on "you say one thing, it detects another."

---

## 10. Module structure (new `engine/router/` package)

Built incrementally (strangler), not all at once:

- `engine/router/__init__.py` — the ONE public entry: `route(text, ctx) -> Decision`.
- `engine/router/pipeline.py` — stage orchestration (0→8).
- `engine/router/normalize.py` — stage 0.
- `engine/router/guards.py` — stage 1 (wraps existing `pre_route`/`_studio_match`).
- `engine/router/semantic.py` — Tier-0 embeddings, exemplar bank, tool-RAG.
- `engine/router/llm_router.py` — Tier-1/2 cascade, schema-constrained, escalation.
- `engine/router/confidence.py` — the single `ConfidencePolicy` + band policy.
- `engine/router/exemplars.py` — bank build (seed from `_TOOLS`) + corrections growth.
- `engine/router/calibration/` — `utterances.jsonl` + `score.py`.

**Reuse (do not rebuild):** `tool_registry` (source of truth), `tool_result_verifier`, `safety_gate`, `intent_taxonomy` (schema), `engine/memory/*` (context), `correction_learner`, `providers/groq_provider`.
**Retire behind the front door:** `intent_router.py`, `groq_intent_planner._deterministic_classify`, `tool_registry.select_tool`, `intents.REGISTRY`, the `groq_intent_router_v2` deterministic tangle, the 3 confidence checks, the `GROQ_INTENT_COOLDOWN_SECONDS` skip, hand-mirrored `ALLOWED_INTENTS`/`TOOL_INTENTS` (auto-derive from `_TOOLS`).

---

## 11. Migration plan (strangler, measure-first)

Each phase ships behind a flag, runs in **shadow mode** first (log its decision next to the live router, don't act), and must not regress the calibration score.

- **Phase A — Measure.** Build the Decision schema extension + `ConfidencePolicy` skeleton + calibration set + scorer. Record the **current** router's baseline misroute/over-act/over-ask numbers.
- **Phase B — Tier 0.** Semantic router + exemplar bank (auto-seeded from `_TOOLS`). Run in shadow beside v2; measure agreement. No behavior change yet.
- **Phase C — WHEN gate + band policy.** Wire the new pipeline as the single front door with v2 as fallback. Now the act/talk/confirm/ask logic is live.
- **Phase D — LLM cascade.** 20b (schema-constrained, tool-RAG) replaces v2's LLM call; 120b escalation. Offline local-20b fallback.
- **Phase E — Corrections loop + retire legacy routers** one route at a time (the copy-pasted deterministic logic dies as the semantic layer proves out).
- **Phase F — Data-driven dispatch.** Use `handler` string; delete the 49-branch chain; auto-derive the taxonomy allow-lists.

---

## 12. Risks & mitigations

- **Latency creep** → hard latency budget per tier; low reasoning effort; instant ack masks the rest; measured, not assumed.
- **Embedding quality on the owner's phrasing** → rich exemplar banks + corrections growth; margin threshold tuned on his transcripts.
- **Constraint tax** (schema suppressing tool-calls) → minimal schema (`tool`, `args`, `confidence`) + explicit `unknown` escape.
- **Offline model footprint** (local 20b needs ~16GB) → offline tier is best-effort; Tier 0 alone still serves the common case with zero model.
- **Migration regression** → shadow mode + calibration gate on every phase; v2 stays as fallback until a route is proven.

---

## 13. Success criteria

- Measured misroute rate on the calibration set **materially below** the recorded v2 baseline (target set after baseline is known).
- Common commands resolve locally in **tens of ms**; every path fires an instant ack.
- Works with **no network** for the Tier-0 majority.
- **Asks/confirms** instead of misfiring on ambiguous/destructive input; over-act and over-ask rates both measured and low.
- **Learns** the owner's phrasing from corrections (exemplar bank grows).
- **One** front door; the four legacy routers retired; adding a tool touches one place.

---

## References (load-bearing)

- Semantic router — Aurelio Labs `semantic-router` (github.com/aurelio-labs/semantic-router)
- Model cascades — RouteLLM (arXiv:2406.18665), FrugalGPT (arXiv:2305.05176)
- Tool-RAG — RAG-MCP (arXiv:2505.03275)
- Calibration — verbalized-confidence miscalibration (arXiv:2606.17234); self-consistency vs entropy (arXiv:2607.08065)
- Selective prediction / abstention (arXiv:2607.04430, arXiv:2607.08456); clarify-beats-abstain (arXiv:2402.15610)
- Dialogue-act false tool-triggering — CONFETTI (arXiv:2506.01859)
- gpt-oss models & latency — Groq day-zero; Artificial Analysis gpt-oss provider benchmarks
- Embeddings — `intfloat/e5-small-v2`, `BAAI/bge-small-en-v1.5`, `all-MiniLM-L6-v2`
- Constrained decoding & the "constraint tax" (arXiv:2606.25605)
