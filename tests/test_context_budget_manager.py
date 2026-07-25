import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest


@pytest.fixture(autouse=True)
def _fresh():
    import engine.session_summary_manager as ssm
    import engine.autonomous_memory as am
    am.get_autonomous_memory().clear_short_term()
    ssm.reset_summary()
    yield
    am.get_autonomous_memory().clear_short_term()
    ssm.reset_summary()


def test_context_is_bounded(monkeypatch):
    from engine.autonomous_memory import get_autonomous_memory
    from engine.context_budget_manager import build_context
    mem = get_autonomous_memory()
    for i in range(20):
        mem.add_user_message(f"the plan is to fix bug {i} in the auth module right now", source="test")
        mem.add_assistant_message(f"decided to patch handler {i} and verify", source="brain")
    ctx = build_context("auth bug", max_chars=1500)
    assert len(ctx) <= 1500


def test_context_includes_recent_exchanges():
    from engine.autonomous_memory import get_autonomous_memory
    from engine.context_budget_manager import build_context
    mem = get_autonomous_memory()
    mem.add_user_message("what were we discussing about the deadline", source="test")
    mem.add_assistant_message("we were planning the friday release", source="brain")
    ctx = build_context("deadline")
    assert "friday release" in ctx or "deadline" in ctx


def test_build_context_never_raises_when_empty():
    from engine.context_budget_manager import build_context
    ctx = build_context("anything")
    assert isinstance(ctx, str)


def test_context_uses_current_voice_and_workflow_state():
    from engine import workflow_state
    from engine.context_budget_manager import build_context
    from engine.voice_state_machine import get_voice_state_machine

    state_machine = get_voice_state_machine()
    state_machine.reset()
    state_machine.transition("wake_detected")
    workflow_state.start_workflow("create_folder", "ask_name", {})
    try:
        ctx = build_context("continue", max_chars=500)
    finally:
        workflow_state.clear_workflow()
        state_machine.reset()

    assert "[ACTIVE_MODE]:" in ctx
    assert "listening" in ctx
    assert "[WORKFLOW]:" in ctx
    assert "create_folder" in ctx
    assert "ask_name" in ctx
    assert len(ctx) <= 500
