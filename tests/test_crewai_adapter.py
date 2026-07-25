"""Optional CrewAI backend (engine/agency/crewai_adapter.py). Uses a fake crewai."""
import sys
import types

import engine.agency.crewai_adapter as ca
import engine.agency.workflow_engine as we


def _install_fake_crewai(monkeypatch, output="CREW OUTPUT"):
    mod = types.ModuleType("crewai")

    class Agent:
        def __init__(self, **k):
            pass

    class Task:
        def __init__(self, **k):
            pass

    class Crew:
        def __init__(self, **k):
            pass

        def kickoff(self):
            return output

    mod.Agent, mod.Task, mod.Crew = Agent, Task, Crew
    monkeypatch.setitem(sys.modules, "crewai", mod)
    return mod


def test_backend_disabled_by_default(monkeypatch):
    monkeypatch.delenv("NEXI_AGENCY_BACKEND", raising=False)
    assert ca.backend_enabled() is False


def test_backend_enabled_via_env(monkeypatch):
    monkeypatch.setenv("NEXI_AGENCY_BACKEND", "crewai")
    assert ca.backend_enabled() is True


def test_run_role_uses_crew(monkeypatch):
    _install_fake_crewai(monkeypatch, output="PLAN: do X")
    assert ca.is_available() is True
    assert ca.run_role("planner", "make a plan") == "PLAN: do X"


def test_run_role_graceful_when_crewai_absent(monkeypatch):
    monkeypatch.setitem(sys.modules, "crewai", None)  # force ImportError on import
    assert ca.is_available() is False
    assert ca.run_role("planner", "x") == ""


def test_model_routes_through_crewai_when_enabled(monkeypatch):
    monkeypatch.setattr(we, "autonomy_enabled", lambda: True)
    monkeypatch.setenv("NEXI_AGENCY_BACKEND", "crewai")
    _install_fake_crewai(monkeypatch, output="ROUTED VIA CREW")
    assert we._model("planner", "goal") == "ROUTED VIA CREW"


def test_model_ignores_crewai_when_disabled(monkeypatch):
    monkeypatch.setattr(we, "autonomy_enabled", lambda: True)
    monkeypatch.delenv("NEXI_AGENCY_BACKEND", raising=False)
    _install_fake_crewai(monkeypatch, output="SHOULD NOT BE USED")
    # backend disabled -> must NOT return crew output (falls through to gemini/stub)
    assert we._model("planner", "goal") != "SHOULD NOT BE USED"
