# Phase 1 Implementation — Claude Prompt

Copy and paste this into a new Claude Code session (or any Claude chat) to execute Phase 1. Claude must read the plan files first, then implement every step.

---

```
You are implementing Phase 1 of the NEXI-JARVIS Fusion project.

## Context
NEXI is a privacy-first desktop AI assistant at E:\ai-agnet-nexi. We are merging JARVIS features (ReAct planner, training, vision, 3-tier memory) into NEXI's clean architecture. Phase 1 extends the foundation: taxonomy, config, router, and skill stubs.

## Files to Read First

Read these plan files in full:
- E:\ai-agnet-nexi\plan.md — Full 8-phase merge plan
- E:\ai-agnet-nexi\phase-1-plan.md — Detailed Phase 1 steps

Also read these existing files to understand the codebase:
- E:\ai-agnet-nexi\intent\taxonomy.py — Current route/intent definitions
- E:\ai-agnet-nexi\core\config.py — Current config dataclass
- E:\ai-agnet-nexi\intent\router.py — Current intent router
- E:\ai-agnet-nexi\skills\dispatch.py — Current skill dispatch map
- E:\ai-agnet-nexi\core\dispatcher.py — Command dispatch hub
- E:\ai-agnet-nexi\core\tts.py — TTS module
- E:\ai-agnet-nexi\core\asr.py — ASR module
- E:\ai-agnet-nexi\brain\gemini.py — Brain module
- E:\ai-agnet-nexi\core\bridge.py — IPC bridge
- E:\ai-agnet-nexi\core\ui_state.py — State machine

## Implementation Steps (Execute in Order)

Step 1.1 — Edit intent/taxonomy.py:
- Add "jarvis" to ROUTES set
- Add JARVIS_INTENTS constant with all 12 intents
- Extend validate_intent() to include JARVIS_INTENTS
- Add ALL_INTENTS merge

Step 1.2 — Edit core/config.py:
- Add NexiJarvisConfig dataclass with 7 fields
- Add `jarvis: NexiJarvisConfig = field(default_factory=NexiJarvisConfig)` to NexiConfig
- Defaults: jarvis_enabled=True, jarvis_tool_calling=True, jarvis_max_tool_steps=10, jarvis_memory_type="unified", jarvis_training_enabled=False, jarvis_brain_provider="gemini", jarvis_brain_api_key=""
- No need to modify .env.example

Step 1.3 — Edit intent/router.py:
- Add _jarvis_prefixes dict with 15+ deterministic prefix→(route, intent) mappings
- Add _match_jarvis_prefix() function called before LLM fallback
- Add "jarvis" route reference to LLM router prompt

Step 1.4 — Edit skills/dispatch.py:
- Add `from skills import jarvis as jarvis_skill`
- Add 12 intent→handler mappings to SKILL_MAP

Step 1.5 — CREATE skills/jarvis.py:
- Create with 12 stub handler functions (all return descriptive strings about which future phase will implement them)
- Each function takes appropriate params and returns str
- Functions: run_agent, execute_tool, train_on_correction, show_rules, add_rule, remove_rule, agent_status, reflect, run_plan, list_tools, tool_help, cancel_agent
- agent_status() must return a multi-line status string

Step 1.6 — Edit core/tts.py:
- Add _get_tts_provider() that returns cfg.tts_provider_order or "groq"
- TTS/ASR stay Groq regardless of brain provider

Step 1.7 — Edit core/asr.py:
- Add _get_asr_provider() that returns cfg.asr_provider or "groq"

Step 1.8 — Edit brain/gemini.py:
- Add _get_brain_config() helper supporting three providers:
  - "claude": api_base=anthropic.com, model=claude-opus-4-8, key=ANTHROPIC_API_KEY
  - "deepseek": api_base=deepseek.com, model=deepseek-v4-pro
  - default/gemini: api_base=googleapis.com, model=gemini-2.5-flash
- Route API calls to correct provider based on config

Step 1.9 — Edit core/dispatcher.py:
- Add handler block for route == "jarvis" at priority ~4.5
- Call skills.dispatch.handle_skill with intent and entity
- Respect cfg.jarvis.jarvis_enabled flag

Step 1.10 — CREATE tests/test_phase1_taxonomy.py
Step 1.11 — CREATE tests/test_phase1_config.py
Step 1.12 — CREATE tests/test_phase1_router.py
Step 1.13 — CREATE tests/test_phase1_jarvis_skill.py

See phase-1-plan.md for exact test content.

## Verification

After ALL steps complete, run:
```powershell
cd E:\ai-agnet-nexi
python -m pytest tests/ -v --tb=short
```

Expected: All 161 tests pass (137 existing + 24 new).

Then run the manual smoke test:
```powershell
python -c "
from intent.router import route_intent
r = route_intent('agent status')
assert r['route'] == 'jarvis', f'Expected jarvis, got {r}'
print(f'Jarvis route works: {r}')
from core.config import cfg
print(f'Jarvis config: enabled={cfg.jarvis.jarvis_enabled}')
from skills.jarvis import agent_status
print(agent_status())
"
```

## Important Rules
1. Do NOT break any existing functionality
2. All new code must have proper type hints
3. Use pathlib, dataclasses, and modern Python patterns (match existing NEXI style)
4. Do NOT add comments to code
5. Do NOT modify .env or .env.example unless explicitly instructed
6. If you encounter ambiguity, read the referenced plan files for context
```
