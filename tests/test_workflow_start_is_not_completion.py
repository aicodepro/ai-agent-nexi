"""Starting an async workflow is not a verified completion.

Live trace - verified=true was emitted before ANY agent ran:
    [NEXI_AGENCY] wf_e952... workflow_started codebase_research
    [VERIFY] tool=nexi_run_codebase_research verified=true
    [TOOL] success name=nexi_run_codebase_research
    [ACTION] verified=true
    ... THEN ...
    [NEXI_AGENCY] wf_e952... agent_started PlannerAgent
    [NEXI_AGENCY] wf_e952... agent_started ResearchAgent
    [NEXI_AGENCY] wf_e952... workflow_completed

_ok() hardcodes verified=True and the background branch used it for a run whose
agents had not executed. `verified` is what downstream treats as evidence of a
real outcome.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from engine import agency
from engine.assistant_response import verified_action, guard_unverified_action_message


def _run_stub(status="running", result="", plan=(), artifacts=()):
    return SimpleNamespace(run_id="wf_test123", status=status, result=result,
                           plan=list(plan), artifacts=list(artifacts))


def test_background_start_is_not_reported_as_verified():
    with patch.object(agency._we, "autonomy_enabled", return_value=True), \
         patch.object(agency._we, "create_run", return_value=_run_stub("running")):
        result = agency.nexi_run_codebase_research({"goal": "x"})

    assert result["verified"] is False, "a started workflow was reported as verified"
    assert verified_action(result) is False, "downstream would treat a start as a real outcome"
    assert result.get("job_state") == "RUNNING"


def test_background_start_message_does_not_claim_completion():
    """The message must survive the unverified-action guard intact.

    "Started the ... workflow" matches ACTION_SUCCESS_RE, so with verified=False
    the guard would replace it wholesale - correct behaviour, wrong message.
    """
    with patch.object(agency._we, "autonomy_enabled", return_value=True), \
         patch.object(agency._we, "create_run", return_value=_run_stub("running")):
        result = agency.nexi_run_codebase_research({"goal": "x"})

    guarded = guard_unverified_action_message(result["message"], result)
    assert guarded == result["message"], \
        "the start message reads as a completion claim and was blocked by the guard"
    assert "couldn't verify" not in guarded


def test_completed_synchronous_run_is_verified():
    with patch.object(agency._we, "autonomy_enabled", return_value=False), \
         patch.object(agency._we, "create_run",
                      return_value=_run_stub("completed", result="1 finding.", plan=[1, 2])):
        result = agency.nexi_run_codebase_research({"goal": "x"})

    assert result["verified"] is True
    assert result.get("job_state") == "COMPLETED"


@pytest.mark.parametrize("status", ["failed", "cancelled", "partial_failure", "running", "waiting_for_tool"])
def test_non_terminal_synchronous_run_is_not_verified(status):
    with patch.object(agency._we, "autonomy_enabled", return_value=False), \
         patch.object(agency._we, "create_run", return_value=_run_stub(status)):
        result = agency.nexi_run_codebase_research({"goal": "x"})

    assert result["verified"] is False, f"status={status} was reported as verified"
    assert verified_action(result) is False


def test_every_async_workflow_tool_uses_the_same_rule():
    """The defect was in the shared _run helper, so all four must be covered."""
    tools = [agency.nexi_run_codebase_research, agency.nexi_run_router_audit,
             agency.nexi_run_test_generation, agency.nexi_run_integration_plan]
    for tool in tools:
        with patch.object(agency._we, "autonomy_enabled", return_value=True), \
             patch.object(agency._we, "create_run", return_value=_run_stub("running")):
            result = tool({"goal": "x"})
        assert result["verified"] is False, f"{tool.__name__} reported a start as verified"
