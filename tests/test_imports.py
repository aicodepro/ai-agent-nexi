"""Smoke-test that NEXI's real modules import.

This file used to import `brain.gemini`, `core.config`, `intent.router`, `skills.apps`,
`ui.adapter` ... — a package layout that was refactored into `engine/` long ago. Those
top-level directories still exist but are EMPTY (0 .py files), so all 27 tests failed
with ModuleNotFoundError on every single run. They tested an architecture that does not
exist, which is worse than having no test: a permanently-red file trains you to ignore
the suite, and it caught nothing because the code it named was never there.

The intent was sound — catch import-time breakage (a syntax error, a circular import, a
missing dependency) before it reaches a voice turn. So the intent is kept and pointed at
the modules NEXI actually loads.

Import-time cost matters here too: `main.py` does `from engine.features import *` BEFORE
it can open the window, so anything heavy added at module scope is startup latency the
user feels — see tests/test_features_lazy_import.py.
"""
import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# Core runtime — if any of these stop importing, NEXI does not start.
CORE_MODULES = [
    "engine.command",
    "engine.command_bus",
    "engine.features",
    "engine.helper",
    "engine.intents",
    "engine.intent_taxonomy",
    "engine.tool_registry",
    "engine.groq_intent_router_v2",
    "engine.gemini_brain",
    "engine.groq_asr",
    "engine.memory_safety",
    "engine.model_registry",
    "engine.ui_event_bridge",
    "engine.ui_state_manager",
    "engine.diagnostics",
]

# Subsystems — each must be independently loadable.
SUBSYSTEM_MODULES = [
    "engine.agent_runtime.registry",
    "engine.agent_runtime.adapters",
    "engine.agent_runtime.model_policy",
    "engine.agent_runtime.model_health",
    "engine.agent_runtime.model_ranking",
    "engine.agent_runtime.model_discovery",
    "engine.agent_runtime.cli_capabilities",
    "engine.agent_runtime.mcp_preflight",
    "engine.studio.supervisor",
    "engine.studio.governance",
    "engine.studio.intake",
    "engine.studio.intent_detect",
    "engine.forge.forge_engine",
    "engine.forge.safety_scan",
    "engine.forge.holdout_eval",
    "engine.forge.archive",
    "engine.memory.workflow_memory",
    "engine.memory.memory_redaction",
    "engine.sleep_time",
    "vision.screenshot_service",
    "vision.vision_analyzer",
    "vision.privacy_guard",
]


@pytest.mark.parametrize("name", CORE_MODULES)
def test_core_module_imports(name):
    """A core module that fails to import takes the whole assistant down."""
    assert importlib.import_module(name) is not None


@pytest.mark.parametrize("name", SUBSYSTEM_MODULES)
def test_subsystem_module_imports(name):
    assert importlib.import_module(name) is not None


def test_no_module_imports_a_dead_top_level_package():
    """REGRESSION: brain/, core/, intent/, skills/, ui/ are empty leftovers from the
    refactor into engine/. Importing one means code reaches for a package with no modules
    in it — which fails only at runtime, on whichever turn happens to hit that path."""
    import re
    from pathlib import Path

    dead = ("brain", "core", "intent", "skills", "ui")
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(rf"^\s*(?:import|from)\s+({'|'.join(dead)})\.", re.M)

    offenders = []
    for path in list((root / "engine").rglob("*.py")) + list((root / "vision").rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in pattern.finditer(text):
            offenders.append(f"{path.relative_to(root)}: imports {m.group(1)}.*")
    assert not offenders, "code imports an empty leftover package:\n  " + "\n  ".join(offenders[:10])


def test_engine_package_is_the_real_one():
    """Guards the premise of this file: engine/ is where the code actually lives."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    engine_py = list((root / "engine").glob("*.py"))
    assert len(engine_py) > 50, f"engine/ has only {len(engine_py)} modules — layout changed?"
