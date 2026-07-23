"""Optional CrewAI backend for the Nexi Agency Engine ("clue.ai").

Dormant by default. Activate with BOTH:
    pip install crewai
    NEXI_AGENCY_BACKEND=crewai

When active, each agent pass's model call is executed by a CrewAI Agent+Task, so
the agency runs "through CrewAI" — while NEXI keeps orchestration, the safety
proxy, persistence, and events. The clean-room engine stays the default: no
shadowing, no forced dependency, fully reversible (this reverses the earlier
"de-brand CrewAI" decision ONLY when explicitly enabled).
"""
import logging
import os


_LOG = logging.getLogger(__name__)


def backend_enabled():
    return os.getenv("NEXI_AGENCY_BACKEND", "").strip().lower() == "crewai"


def is_available():
    try:
        import crewai  # noqa: F401
        return True
    except Exception:
        return False


def run_role(role: str, prompt: str) -> str:
    """Execute one agent pass via a CrewAI Agent+Task. Returns text ('' on failure)."""
    try:
        from crewai import Agent, Task, Crew
        agent = Agent(
            role=f"Nexi {role}",
            goal=prompt,
            backstory=f"You are Nexi's {role}, concise and evidence-driven.",
            verbose=False,
            allow_delegation=False,
        )
        task = Task(description=prompt, expected_output="A concise, direct answer.", agent=agent)
        crew = Crew(agents=[agent], tasks=[task], verbose=False)
        return str(crew.kickoff() or "")
    except Exception:
        _LOG.exception("CrewAI role %s failed", role)
        return ""


def _maybe(role: str, prompt: str) -> str:
    """Model-override callback: run via CrewAI only when enabled + installed."""
    if backend_enabled() and is_available():
        return run_role(role, prompt)
    return ""  # not enabled -> let the engine fall through to its default


def register():
    """Plug this backend into the agency engine's model-override hook."""
    from engine.agency import workflow_engine
    workflow_engine.set_model_override(_maybe)
