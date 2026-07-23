"""Studio must size the model to the stage — Nexi switching models on its own.

Three defects this pins:

1. `AgentRunRequest` had no `task_kind`, so the adapters' per-task model selection read
   an empty string and NEVER fired. Every Studio stage ran on whichever single model the
   runtime defaulted to — a `closeout` summary burning the same expensive model as
   `architecture`.
2. Studio's manager judgement (`_manager_llm_answer`) asked for `select_model("intent_json")`,
   which is ranked by SPEED for fast classification. Nexi's manager reasoning about scope,
   cost and security was therefore running on the FASTEST model, not the best one.
3. `_dispatch_agent_task` hardcoded a "claude-code" fallback instead of the selected runtime.

No model NAME is asserted anywhere here — only that the right WEIGHT class is chosen,
because the concrete model is discovered and ranked at run time.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_agent_run_request_carries_task_kind():
    """Without this field the adapters cannot size the model at all."""
    from engine.agent_runtime.contracts import AgentRunRequest
    req = AgentRunRequest(task="t", project_dir=".", owner_id="o", task_kind="code")
    assert req.task_kind == "code"


def test_task_kind_defaults_to_empty_for_old_callers():
    """Backward compatible: existing constructions must keep working."""
    from engine.agent_runtime.contracts import AgentRunRequest
    assert AgentRunRequest(task="t", project_dir=".", owner_id="o").task_kind == ""


def test_every_studio_stage_maps_to_a_task_kind():
    from engine.studio import governance, supervisor
    for stage in governance.CANONICAL_STAGES:
        assert stage in supervisor._STAGE_TASK_KIND, f"stage '{stage}' has no task kind"
        assert supervisor._STAGE_TASK_KIND[stage], f"stage '{stage}' maps to empty"


def test_heavy_stages_are_not_run_on_cheap_models():
    """architecture / implementation / security_review are where quality matters."""
    from engine.agent_runtime.cli_capabilities import task_weight
    from engine.studio.supervisor import _STAGE_TASK_KIND
    for stage in ("requirements", "research", "architecture", "sprint_plan",
                  "implementation", "security_review", "integration", "release"):
        assert task_weight(_STAGE_TASK_KIND[stage]) == "heavy", f"{stage} would use a cheap model"


def test_light_stages_use_the_cheap_tier():
    """Tests/QA/closeout are high-volume and verifiable — spend little here."""
    from engine.agent_runtime.cli_capabilities import task_weight
    from engine.studio.supervisor import _STAGE_TASK_KIND
    for stage in ("developer_tests", "qa", "closeout"):
        assert task_weight(_STAGE_TASK_KIND[stage]) == "light", f"{stage} would burn a strong model"


def test_stage_map_contains_no_model_names():
    """The map must classify WORK, never pin a model (Darsh's no-hardcoding rule)."""
    from engine.studio.supervisor import _STAGE_TASK_KIND
    banned = ("gpt", "claude", "opus", "sonnet", "haiku", "gemini", "deepseek", "llama", "/")
    for stage, kind in _STAGE_TASK_KIND.items():
        low = kind.lower()
        assert not any(b in low for b in banned), f"{stage} pins a model: {kind}"


def test_manager_reasoning_is_ranked_by_reasoning_not_speed():
    """REGRESSION: manager judgement used the speed-ranked 'intent_json' task."""
    from engine.model_registry import TASKS
    assert "manager_reasoning" in TASKS
    assert TASKS["manager_reasoning"]["rank"] == "reasoning"
    assert TASKS["manager_reasoning"]["env"] == "NEXI_STUDIO_MANAGER_MODEL"


def test_manager_model_is_at_least_as_capable_as_the_intent_model(monkeypatch):
    from engine.model_registry import MODELS, select_model
    monkeypatch.setenv("GROQ_API_KEY", "k")
    for env in ("GROQ_INTENT_MODEL", "NEXI_STUDIO_MANAGER_MODEL"):
        monkeypatch.delenv(env, raising=False)
    mgr, intent = select_model("manager_reasoning"), select_model("intent_json")
    assert MODELS[mgr]["reasoning"] >= MODELS[intent]["reasoning"], (
        f"manager ({mgr}) reasons worse than the intent classifier ({intent})")


def test_supervisor_uses_manager_reasoning_task():
    """Guard the call site itself, not just the registry entry."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "studio" / "supervisor.py").read_text(
        encoding="utf-8", errors="replace")
    assert 'select_model("manager_reasoning")' in src
    assert 'model=select_model("intent_json")' not in src


def test_dispatch_does_not_hardcode_a_provider():
    """It must honour the selected runtime, not fall back to a fixed CLI."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "engine" / "studio" / "supervisor.py").read_text(
        encoding="utf-8", errors="replace")
    assert 'studio.get("runtime_provider") or "claude-code"' not in src
