# Phase 1: Foundation Layer — Detailed Implementation Plan

> **Duration:** 3-4 days
> **New code:** ~295 lines across 8 files
> **New tests:** ~24 tests
> **Exit gate:** All 137 existing tests + 24 new Phase 1 tests pass

---

## Step 1.1: Extend `intent/taxonomy.py` (+30 lines, +4 tests)

### What to change
Add a new `"jarvis"` route, 12 JARVIS_INTENTS, and extend the validation functions.

### Code changes

**File:** `E:\ai-agnet-nexi\intent\taxonomy.py`

```python
# Add to ROUTES set:
# "jarvis" — agent orchestration, tool execution, training, reflection

# Add new constant:
JARVIS_INTENTS: set[str] = {
    "run_agent",           # Execute a multi-step agent task
    "execute_tool",        # Run a specific tool by name
    "train_on_correction", # Learn from a correction
    "show_rules",          # Display learned rules
    "add_rule",            # "when I say X do Y"
    "remove_rule",         # Remove a learned rule
    "agent_status",        # Show agent system status
    "reflect",             # Trigger reflection on past turns
    "run_plan",            # Execute a multi-step plan
    "list_tools",          # Show available tools
    "tool_help",           # Explain how to use a tool
    "cancel_agent",        # Interrupt running agent
}

# Add to ALL_INTENTS:
ALL_INTENTS = BRAIN_INTENTS | OUTPUT_INTENTS | LOCAL_INTENTS | JARVIS_INTENTS | {
    "greeting", "identity", "cancel", "sleep", "wake", "repeat", "unknown",
}

# Extend validate_intent to include JARVIS_INTENTS
```

### Test changes

New file `tests/test_phase1_taxonomy.py`:
```python
def test_jarvis_route_in_routes():
    assert "jarvis" in ROUTES

def test_jarvis_intents_count():
    assert len(JARVIS_INTENTS) == 12

def test_validate_route_jarvis():
    assert validate_route("jarvis") == "jarvis"

def test_validate_intent_jarvis():
    assert validate_intent("run_agent") == "run_agent"
    assert validate_intent("invalid_jarvis") is None
```

---

## Step 1.2: Extend `core/config.py` (+40 lines, +3 tests)

### What to change
Add `NexiJarvisConfig` section with 7 new configuration fields driven by environment variables.

### Code changes

**File:** `E:\ai-agnet-nexi\core\config.py`

```python
@dataclass
class NexiJarvisConfig:
    jarvis_enabled: bool = field(default_factory=lambda: env_bool("JARVIS_ENABLED", True))
    jarvis_tool_calling: bool = field(default_factory=lambda: env_bool("JARVIS_TOOL_CALLING", True))
    jarvis_max_tool_steps: int = field(default_factory=lambda: env_int("JARVIS_MAX_TOOL_STEPS", 10))
    jarvis_memory_type: str = field(default_factory=lambda: os.getenv("JARVIS_MEMORY_TYPE", "unified"))
    jarvis_training_enabled: bool = field(default_factory=lambda: env_bool("JARVIS_TRAINING_ENABLED", False))
    jarvis_brain_provider: str = field(default_factory=lambda: os.getenv("JARVIS_BRAIN_PROVIDER", "gemini").strip())
    jarvis_brain_api_key: str = field(default_factory=lambda: (os.getenv("JARVIS_BRAIN_API_KEY") or "").strip())

# Add to NexiConfig:
jarvis: NexiJarvisConfig = field(default_factory=NexiJarvisConfig)
```

### Environment variables to add to `.env.example`
```ini
# Jarvis Integration
JARVIS_ENABLED=true
JARVIS_TOOL_CALLING=true
JARVIS_MAX_TOOL_STEPS=10
JARVIS_MEMORY_TYPE=unified
JARVIS_TRAINING_ENABLED=false
JARVIS_BRAIN_PROVIDER=claude       # claude | gemini | deepseek
ANTHROPIC_API_KEY=                  # Required for Claude Opus 4.8
# JARVIS_BRAIN_API_KEY=             # Only needed for non-Claude providers
```

### Test changes

New tests in `tests/test_phase1_config.py`:
```python
def test_jarvis_config_defaults():
    assert cfg.jarvis.jarvis_enabled is True
    assert cfg.jarvis.jarvis_max_tool_steps == 10

def test_jarvis_config_env_override(monkeypatch):
    monkeypatch.setenv("JARVIS_ENABLED", "false")
    cfg_reload = NexiConfig()
    assert cfg_reload.jarvis.jarvis_enabled is False

def test_jarvis_provider_defaults_to_gemini():
    assert cfg.jarvis.jarvis_brain_provider == "gemini"
```

---

## Step 1.3: Extend `intent/router.py` (+80 lines, +6 tests)

### What to change
Add 15 deterministic patterns for Jarvis-specific commands. Extend the LLM router prompt to include the `"jarvis"` route.

### Deterministic patterns to add

Insert after the existing math/greeting/sleep patterns (before LLM fallback):

```python
# === Jarvis patterns ===
_jarvis_prefixes = {
    "run agent": ("jarvis", "run_agent"),
    "execute tool": ("jarvis", "execute_tool"),
    "use tool": ("jarvis", "execute_tool"),
    "train on that": ("jarvis", "train_on_correction"),
    "learn from that": ("jarvis", "train_on_correction"),
    "show rules": ("jarvis", "show_rules"),
    "what rules": ("jarvis", "show_rules"),
    "add rule": ("jarvis", "add_rule"),
    "when i say": ("jarvis", "add_rule"),
    "remove rule": ("jarvis", "remove_rule"),
    "agent status": ("jarvis", "agent_status"),
    "system status": ("jarvis", "agent_status"),
    "list tools": ("jarvis", "list_tools"),
    "what tools": ("jarvis", "list_tools"),
    "cancel agent": ("jarvis", "cancel_agent"),
    "stop agent": ("jarvis", "cancel_agent"),
    "run plan": ("jarvis", "run_plan"),
    "plan": ("jarvis", "run_plan"),  # before general "plan" for workflow
}

# Insert into _deterministic() before LLM fallback:
def _match_jarvis_prefix(text: str) -> dict | None:
    for prefix, (route, intent) in _jarvis_prefixes.items():
        if text.startswith(prefix):
            entity = text[len(prefix):].strip().strip('."!?')
            return {"route": route, "intent": intent, "confidence": 0.85, "entity": entity}
    return None
```

### LLM router prompt extension

Add to the Groq prompt file (`prompts/intent_router_prompt.txt` or inline):
```
- "jarvis" — agent orchestration and tool execution (run_agent, execute_tool, train_on_correction, agent_status, list_tools, cancel_agent, run_plan)
```

### Test changes

New file `tests/test_phase1_router.py`:
```python
import pytest
from intent.router import route_intent

def test_jarvis_run_agent():
    result = route_intent("run agent deploy my app")
    assert result["route"] == "jarvis"
    assert result["intent"] == "run_agent"

def test_jarvis_list_tools():
    result = route_intent("list tools")
    assert result["route"] == "jarvis"
    assert result["intent"] == "list_tools"

def test_jarvis_add_rule():
    result = route_intent("when i say open chrome do open edge")
    assert result["route"] == "jarvis"
    assert result["intent"] == "add_rule"

def test_jarvis_agent_status():
    result = route_intent("agent status")
    assert result["route"] == "jarvis"
    assert result["intent"] == "agent_status"

def test_jarvis_cancel_agent():
    result = route_intent("stop agent")
    assert result["route"] == "jarvis"
    assert result["intent"] == "cancel_agent"

def test_jarvis_train_on_correction():
    result = route_intent("train on that")
    assert result["route"] == "jarvis"
    assert result["intent"] == "train_on_correction"
```

---

## Step 1.4: Extend `skills/dispatch.py` (+25 lines, +2 tests)

### What to change
Add Jarvis skill module import and 12 new intent→handler mappings.

### Code changes

**File:** `E:\ai-agnet-nexi\skills\dispatch.py`

```python
# Add import at top:
from skills import jarvis as jarvis_skill

# Add to SKILL_MAP:
SKILL_MAP.update({
    # Jarvis agent skills
    "run_agent":           lambda e: jarvis_skill.run_agent(e),
    "execute_tool":        lambda e: jarvis_skill.execute_tool(e),
    "train_on_correction": lambda e: jarvis_skill.train_on_correction(e),
    "show_rules":          lambda e: jarvis_skill.show_rules(),
    "add_rule":            lambda e: jarvis_skill.add_rule(e),
    "remove_rule":         lambda e: jarvis_skill.remove_rule(e),
    "agent_status":        lambda e: jarvis_skill.agent_status(),
    "reflect":             lambda e: jarvis_skill.reflect(),
    "run_plan":            lambda e: jarvis_skill.run_plan(e),
    "list_tools":          lambda e: jarvis_skill.list_tools(),
    "tool_help":           lambda e: jarvis_skill.tool_help(e),
    "cancel_agent":        lambda e: jarvis_skill.cancel_agent(),
})
```

### Test changes

New tests in existing or new test file:
```python
def test_jarvis_skill_map_has_all_intents():
    jarvis_intents = {"run_agent", "execute_tool", "train_on_correction", "show_rules",
                      "add_rule", "remove_rule", "agent_status", "reflect", "run_plan",
                      "list_tools", "tool_help", "cancel_agent"}
    for intent in jarvis_intents:
        assert intent in SKILL_MAP, f"Missing SKILL_MAP entry for {intent}"

def test_handle_jarvis_skill():
    result = handle_skill("agent_status", "")
    assert result is not None
```

---

## Step 1.5: Create `skills/jarvis.py` (+60 lines, +3 tests)

### What to create
A new skill module with stub handlers for all 12 Jarvis intents. These stubs return structured results that will be replaced with real implementations in Phases 2-5.

### Code

**File:** `E:\ai-agnet-nexi\skills\jarvis.py`

```python
from __future__ import annotations

import logging

# Placeholder — Phase 1 stubs only
# Real implementations come in Phase 2 (tools), Phase 3 (ReAct), Phase 5 (training)

LOGGER = logging.getLogger(__name__)


def run_agent(task: str) -> str:
    LOGGER.info("[JARVIS] run_agent task=%s", task)
    return f"Agent task queued: {task}. Full ReAct planner coming in Phase 3."


def execute_tool(tool_name: str) -> str:
    LOGGER.info("[JARVIS] execute_tool name=%s", tool_name)
    return f"Tool execution requested: {tool_name}. Tool registry coming in Phase 2."


def train_on_correction(text: str) -> str:
    LOGGER.info("[JARVIS] train_on_correction text=%s", text)
    return f"Correction noted. Training engine coming in Phase 5."


def show_rules() -> str:
    return "No rules defined yet. Rule engine coming in Phase 4."


def add_rule(rule_text: str) -> str:
    LOGGER.info("[JARVIS] add_rule text=%s", rule_text)
    return f"Rule noted: '{rule_text}'. Rule persistence coming in Phase 4."


def remove_rule(rule_text: str) -> str:
    LOGGER.info("[JARVIS] remove_rule text=%s", rule_text)
    return f"Rule removal requested: '{rule_text}'. Coming in Phase 4."


def agent_status() -> str:
    return (
        "NEXI-JARVIS Fusion — Phase 1 foundation active.\n"
        "  Jarvis route:    ✅ configured\n"
        "  Tool registry:   ⏳ Phase 2\n"
        "  ReAct planner:   ⏳ Phase 3\n"
        "  Advanced memory: ⏳ Phase 4\n"
        "  Training:        ⏳ Phase 5"
    )


def reflect() -> str:
    return "Reflection engine coming in Phase 4."


def run_plan(task: str) -> str:
    LOGGER.info("[JARVIS] run_plan task=%s", task)
    return f"Multi-step plan requested: {task}. ReAct planner coming in Phase 3."


def list_tools() -> str:
    return "Available tools: (none yet). Tool registry coming in Phase 2."


def tool_help(tool_name: str) -> str:
    return f"Help for '{tool_name}': Tool documentation coming in Phase 2."


def cancel_agent() -> str:
    LOGGER.info("[JARVIS] cancel_agent")
    return "Agent cancellation requested. Interrupt handler coming in Phase 3."
```

### Test changes

New file `tests/test_phase1_jarvis_skill.py`:
```python
from skills.jarvis import agent_status, list_tools, cancel_agent

def test_agent_status_returns_string():
    result = agent_status()
    assert isinstance(result, str)
    assert "Jarvis route" in result

def test_list_tools_returns_string():
    result = list_tools()
    assert isinstance(result, str)

def test_cancel_agent_returns_string():
    result = cancel_agent()
    assert isinstance(result, str)
```

---

## Step 1.6: Make `core/tts.py` Provider-Aware (+15 lines, +2 tests)

### What to change
Add a simple provider selection based on `cfg.jarvis.jarvis_brain_provider`. Groq TTS remains the primary — Claude Opus 4.8 is for brain/planning only, not TTS.

**File:** `E:\ai-agnet-nexi\core\tts.py`

```python
# At the top or in the speak() function, add:
def _get_tts_provider() -> str:
    # TTS is independent of the brain provider.
    # Groq TTS is best-in-class; keep it regardless of brain choice.
    return cfg.tts_provider_order or "groq"
```

---

## Step 1.7: Make `core/asr.py` Provider-Aware (+15 lines, +2 tests)

### What to change
Same as TTS — ASR remains Groq Whisper regardless of brain provider.

**File:** `E:\ai-agnet-nexi\core\asr.py`

```python
# In the transcribe() function or init:
def _get_asr_provider() -> str:
    # ASR is independent of the brain provider.
    # Groq Whisper is best-in-class; keep it.
    return cfg.asr_provider or "groq"
```

---

## Step 1.8: Make `brain/gemini.py` Provider-Pluggable (+30 lines, +2 tests)

### What to change
Add a check for `cfg.jarvis.jarvis_brain_provider`. Support three providers: `"claude"` (Opus 4.8 — primary), `"gemini"` (existing fallback), `"deepseek"` (optional self-hosted fallback).

**File:** `E:\ai-agnet-nexi\brain/gemini.py` (rename to `brain/provider.py` in future)

```python
# At the top, add an API configuration helper:
def _get_brain_config() -> dict:
    provider = cfg.jarvis.jarvis_brain_provider
    if provider == "claude":
        return {
            "api_base": "https://api.anthropic.com/v1",
            "model": "claude-opus-4-8",
            "api_key": os.getenv("ANTHROPIC_API_KEY", ""),
            "max_tokens": 4096,
        }
    if provider == "deepseek":
        return {
            "api_base": "https://api.deepseek.com/v1",
            "model": "deepseek-v4-pro",
            "api_key": cfg.jarvis.jarvis_brain_api_key,
        }
    # Default: Gemini
    return {
        "api_base": "https://generativelanguage.googleapis.com/v1beta",
        "model": cfg.gemini_model_chain[0] if cfg.gemini_model_chain else "gemini-2.5-flash",
        "api_key": cfg.gemini_api_key,
    }

# In ask_gemini():
# Replace: direct Gemini API call with:
#   config = _get_brain_config()
#   route to provider-specific handler based on config["api_base"]
#   (Claude uses anthropic SDK messages API, Gemini uses google generateContent API)
```

### Test changes

```python
def test_brain_config_defaults_to_gemini():
    config = _get_brain_config()
    assert "googleapis" in config["api_base"] or "gemini" in config["api_base"].lower()

def test_brain_config_claude(monkeypatch):
    monkeypatch.setattr(cfg.jarvis, "jarvis_brain_provider", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")
    config = _get_brain_config()
    assert "anthropic.com" in config["api_base"]
    assert config["model"] == "claude-opus-4-8"
```

---

## Step 1.9: Wire Dispatcher for Jarvis Route (+20 lines, +2 tests)

### What to change
In `core/dispatcher.py`, add a small handler block for `route == "jarvis"` at priority ~4.5 (between intent routing and skill dispatch).

**File:** `E:\ai-agnet-nexi\core\dispatcher.py`

```python
# In _dispatch(), add after intent routing (~line 130-150):
if route == "jarvis":
    if not cfg.jarvis.jarvis_enabled:
        return "Jarvis features are disabled in configuration."
    from skills.dispatch import handle_skill
    result = handle_skill(route_data.get("intent", "agent_status"), route_data.get("entity", ""))
    return result if result else "Jarvis handler executed. Full implementation coming in later phases."
```

---

## Step 1.10: Run All Tests

### Verification commands

```powershell
# 1. Run all existing tests to confirm no regression
python -m pytest tests/ -v --tb=short

# 2. Run Phase 1 new tests
python -m pytest tests/test_phase1_taxonomy.py tests/test_phase1_config.py tests/test_phase1_router.py tests/test_phase1_jarvis_skill.py -v --tb=short

# 3. Run everything together
python -m pytest tests/ -v --tb=short --tb=short 2>&1 | Select-String -Pattern "passed|failed|error"
```

**Expected:** All 161 tests pass (137 existing + 24 new).

### Manual smoke test

```powershell
# Test Jarvis route integration
python -c "
from intent.router import route_intent
r = route_intent('agent status')
assert r['route'] == 'jarvis', f'Expected jarvis route, got {r}'
print(f'✅ Jarvis route works: {r}')

from core.config import cfg
assert cfg.jarvis.jarvis_enabled is True
print(f'✅ Jarvis config loaded: enabled={cfg.jarvis.jarvis_enabled}')

from skills.jarvis import agent_status
s = agent_status()
print(f'✅ Jarvis skill stub works:\n{s}')
"
```

---

## Phase 1 Exit Gate Checklist

- [ ] All 137 existing NEXI tests pass
- [ ] All 24 new Phase 1 tests pass
- [ ] `"jarvis"` route recognized by `intent/router.py`
- [ ] All 12 JARVIS_INTENTS validated by `intent/taxonomy.py`
- [ ] 7 new Jarvis config fields loadable from environment
- [ ] `skills/jarvis.py` imported and mapped in `skills/dispatch.py`
- [ ] Jarvis route triggers stub handlers via dispatcher
- [ ] TTS/ASR/brain provider selection works for `"claude"` (Opus 4.8)
- [ ] Manual smoke test passes

**Phase 1 complete. Ready for Phase 2: Tool Registry & Execution.**
