# Intent Router Audit

## Architecture: TWO Competing Routers

### Router V2 (Primary) — `engine/groq_intent_router_v2.py`

Called from `_handle_product_intelligence_v2()` in `command.py:801` when `NEXI_INTENT_V2_ENABLED=true` (default).

Entry: `route_intent_v2(text, source, context)` at line 587

Flow:
```
route_intent_v2()
├── build_intent_context() → context with session, semantic, episodic, reflection memory
├── pre_route() → checks for learned corrections
├── correction_learner.apply_correction() → apply learned rule
├── _deterministic_router() → regex/exact/alias matching (zero LLM cost)
│   └── if result confidence > threshold → return _finalize()
├── _route_with_llm() → Groq (or xAI Grok) LLM with full capability manifest
│   └── if valid result → return _finalize()
├── _enrich_slots_with_llm() → LLM extracts slots for deterministic result
└── _finalize() → validate, normalize, confidence score, clarification check
```

**Route types returned** (schema in `intent_taxonomy.py:25`):
- `tool` — Known feature with all slots
- `clarify` — Missing required slots → `missing_slots`, `clarification_question`
- `brain` — General Q&A → Gemini
- `system` — Greeting, identity, repeat, diagnostics
- `memory` — Store/recall facts
- `training` — Training commands
- `workflow` — Multi-step workflow (create_folder, etc.)
- `react` — Multi-step ReAct planning
- `followup` — Yes/no/confirmation
- `cancel` — Cancel current action
- `interrupt` — Stop speaking
- `reject` — Cannot help
- `sleep`/`wake` — Sleep/wake commands
- `feature_gap` — Feature request (matched by pattern but routed as `tool`->`request_feature`)

**Strengths**:
- Schema is rich: route, intent, domain, confidence, slots, missing_slots, clarification_question, risk_level, requires_confirmation
- Deterministic first for speed and reliability
- LLM fallback for fuzzy language
- Slot enrichment via LLM parameter extractor
- Confidence gating via `confidence_manager.py`
- Full capability manifest passed to LLM via `router_capability_manifest()`

**Weaknesses**:
- `_deterministic_is_confident()` at line 572 is conservative — many deterministic matches that could be confident are sent to LLM anyway (e.g., "open chrome" has confidence 0.95, no missing slots, but route is "tool" and it only returns True for "tool" when `not result.get("missing_slots")` — which it IS, so this works. But "what time is it" with route "tool", no missing slots, but what about confidence 0.93? This returns True because no missing slots and route == "tool". OK this seems fine actually.)
- **NO post-brain classifier**: When route="brain", the response is spoken directly. If Gemini asks a question, `_mark_question_response()` in `speak()` handles it via `response_asks_question()` which is purely text-based (checks `?` ending).

### Legacy Router — `engine/intent_router.py`

Called from `allCommands()` at line 1920 as final fallback after v2 router.

Entry: `route_intent(text, workflow_active)` at line 133

**Route types**: `local_action`, `brain`, `greeting`, `identity`, `workflow`, `unknown`

**Weaknesses**:
- Very basic: exact matches, prefix matches, regex patterns
- No slot extraction, no clarification
- Routes to "brain" on any Q&A prefix
- Used only after v2 router fails

### Pre-routing in `allCommands()` (command.py:1746)

The `allCommands()` function has a complex priority ladder that pre-routes BEFORE the intent router:

1. Emergency stop check (line 1774)
2. Stop speaking check (line 1783)
3. Wake/sleep commands (line 1797)
4. Voice diagnostics (line 1803)
5. Cognitive commands (line 1810)
6. Clarification (line 1817)
7. Workflow dialog (line 1825)
8. Memory commands (line 1842)
9. Output commands (line 1849)
10. **Router V2** — `_handle_product_intelligence_v2()` (line 1856)
11. `select_tool()` — Legacy tool selection (line 1863)
12. `handle_local_skill()` — Local skills (line 1882)
13. Repeat last (line 1894)
14. Phase 3 bridge (line 1907)
15. **Legacy router** — `route_intent()` (line 1920)
16. `dispatch_intent()` — Final attempt (line 1935/1938)

**Critical finding**: Each step that returns True stops the chain. The v2 router at step 10 covers most commands. If it handles correctly, steps 11-16 never execute. But steps 7-9 (workflow dialog, memory, output) run BEFORE the v2 router and can intercept commands.

### Does the Router Know All Features?

YES — `router_tool_manifest()` in `tool_registry.py:174` builds full capability cards with required_slots, optional_slots, risk_level, examples, aliases. This is passed to the LLM router via `_route_with_llm()` at line 445.

### Does the Router Validate Missing Parameters?

PARTIALLY YES — `execute_tool()` in `tool_registry.py:309` checks `missing_slots(name, values)` and returns `{"expects_user_reply": True, "message": clarification_for_missing_slot(name, slot)}`. The router_v2 also returns `route="clarify"` with `missing_slots` when it detects missing parameters at the deterministic stage (e.g., bare "open" → clarify with "Which app should I open?").

### Does the Router Distinguish All Required Route Types?

YES — The schema supports: `interrupt`, `sleep`, `wake`, `clarify`, `followup`, `workflow`, `tool`, `memory`, `training`, `output`, `brain`, `react`, `system`, `reject`, `cancel`, `feature_gap`

Most routes have handlers in `_handle_product_intelligence_v2()` (command.py:801-999).

### Known Weak Points

1. **No post-brain classifier** — Brain responses are spoken directly without classification into final_answer / needs_user_input / suggested_feature / unsafe / uncertain
2. **Feature gap is not a true route** — `feature_gap` exists in the taxonomy but `_deterministic_router()` routes it as `tool`->`request_feature`, not as a separate route
3. **Pre-routing intercepts router** — Workflow dialog, memory, output commands run before the v2 router in `allCommands()`, creating potential route conflicts
4. **`feature_gap` LLM detection is weak** — The LLM prompt could suggest `feature_gap` but the taxonomy includes it only as an allowed route, not as a prominently documented option
5. **Missing `approval_required` route in taxonomy** — The taxonomy doesn't have `approval_required` as a separate route; approval is handled via `requires_confirmation` flag on tool results
