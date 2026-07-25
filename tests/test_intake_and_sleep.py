"""NEXI as intake manager (ask -> plan -> hand down) + sleep-time compute (#75).

Darsh: "NEXI acts as a questioner, then creates the plan/flow/requirements itself,
then hands that data to the agents step by step."

Also pins a real bug found while wiring this: `_prior_handoffs` tail-cut its context at
9000 chars, which silently drops the OLDEST handoffs first — requirements, architecture,
acceptance criteria. By `release` an agent could be reasoning without ever seeing the
goal, so a build drifts off-spec while every individual stage looks fine.
"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from engine import sleep_time
from engine.studio import intake


# ---- intake: ask before building -------------------------------------------------

@pytest.mark.parametrize("cmd", ["open chrome", "what time is it", "play music",
                                 "close the window", "screenshot"])
def test_routine_commands_never_trigger_an_interview(cmd):
    """Interrogating someone who said 'open chrome' is what makes an assistant painful."""
    assert intake.needs_intake(cmd) is False


@pytest.mark.parametrize("req", ["build a login system", "refactor the auth module",
                                 "create a REST api for orders", "fix the payment bug"])
def test_development_work_does_trigger_an_interview(req):
    assert intake.needs_intake(req) is True


def test_questions_target_what_is_actually_missing():
    vague = intake.analyse("build a dashboard")
    detailed = intake.analyse(
        "build a dashboard so that the admin can see revenue; must be offline and free; "
        "reads from the sqlite database; extends the existing UI; done when tests pass; "
        "scope excludes mobile")
    assert detailed["coverage"] > vague["coverage"]
    assert len(detailed["missing"]) < len(vague["missing"])


def test_questions_are_capped_and_explain_why():
    qs = intake.questions("build a thing", limit=4)
    assert 1 <= len(qs) <= 4, "a wall of questions gets skipped, which is worse than none"
    assert all(q["why"] for q in qs), "each question must justify itself"


def test_acceptance_is_never_invented():
    """Fabricating a success criterion is worse than admitting it is missing."""
    brief = intake.build_brief("build a dashboard")
    assert "ACCEPTANCE NOT DEFINED" in brief["acceptance"][0]


def test_stated_acceptance_is_used():
    brief = intake.build_brief("build x", {"done": "the CSV exports without error"})
    assert "CSV exports" in brief["acceptance"][0]


def test_flow_matches_the_stages_that_will_actually_run():
    """The plan must not describe a workflow the supervisor does not execute."""
    from engine.studio import governance
    brief = intake.build_brief("build a service")
    assert [f["stage"] for f in brief["flow"]] == list(governance.CANONICAL_STAGES)
    for step in brief["flow"]:
        assert step["agent"] == governance.CANONICAL_STAGE_AGENTS[step["stage"]]


def test_answers_raise_readiness():
    low = intake.build_brief("build a dashboard")["readiness"]
    high = intake.build_brief("build a dashboard", {
        "outcome": "see revenue", "scope": "web only", "users": "admins",
        "constraints": "offline", "data": "sqlite", "done": "tests pass"})["readiness"]
    assert high > low


# ---- context ledger --------------------------------------------------------------

def test_ledger_accumulates_prior_work():
    led = intake.ContextLedger(intake.build_brief("build a dashboard"))
    led.add("research", "research-analyst", "Found an existing chart library.", verified=True)
    ctx = led.for_stage("architecture")
    assert "ORIGINAL REQUEST" in ctx
    assert "existing chart library" in ctx, "next agent did not receive prior work"
    assert "YOUR STAGE: architecture" in ctx


def test_unanswered_questions_travel_with_the_context():
    """An agent must know what is unknown, or it will quietly invent it."""
    led = intake.ContextLedger(intake.build_brief("build a dashboard"))
    ctx = led.for_stage("research")
    assert "STILL UNANSWERED" in ctx
    assert "do not invent" in ctx.lower()


def test_ledger_marks_unverified_work_as_such():
    led = intake.ContextLedger(intake.build_brief("build x"))
    led.add("research", "r", "a claim", verified=False)
    assert "unverified" in led.for_stage("architecture")


# ---- the truncation bug ----------------------------------------------------------

def test_oldest_anchors_survive_a_long_run():
    """REGRESSION: a tail cut dropped requirements/architecture first."""
    from engine.studio import supervisor

    class _Run:
        run_id = "r1"
        artifacts = [{"stage": s, "name": f"{s}.md", "sha256": "a" * 12}
                     for s in supervisor.STAGES[:9]]

    big = {s: ("X" * 4000 if s not in supervisor._ANCHOR_STAGES else f"ANCHOR-{s}" + "y" * 200)
           for s in supervisor.STAGES}
    original = supervisor._read_artifact
    supervisor._read_artifact = lambda run, stage: big.get(stage, "")
    try:
        text = supervisor._prior_handoffs(_Run(), "release", budget=9000)
    finally:
        supervisor._read_artifact = original

    assert "ANCHOR-requirements" in text, "requirements were dropped — the goal was lost"
    assert "ANCHOR-architecture" in text, "the architecture decision was dropped"
    assert "OMITTED FOR LENGTH" in text, "omission must be visible, not silent"


def test_no_prior_handoffs_is_stated_plainly():
    from engine.studio import supervisor

    class _Run:
        run_id = "r"
        artifacts = []

    assert supervisor._prior_handoffs(_Run(), "research") == "No prior handoffs."


# ---- sleep-time compute (#75) ----------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_jobs(monkeypatch):
    sleep_time._JOBS.clear()
    sleep_time._history.clear()
    monkeypatch.setenv("NEXI_SLEEP_IDLE_SECONDS", "0.2")
    yield
    sleep_time._JOBS.clear()


def test_sleep_work_yields_the_moment_the_user_returns():
    """The 83s-freeze lesson: offline work must never delay a voice turn."""
    sleep_time.register("job", lambda: {"detail": "ran"}, min_interval_s=0)
    sleep_time.note_activity()
    assert sleep_time.is_idle() is False
    rows = sleep_time.run_due_jobs()
    assert rows and rows[0].get("skipped") == "user_active"


def test_jobs_run_once_idle():
    sleep_time.register("job", lambda: {"detail": "ran"}, min_interval_s=0)
    sleep_time.note_activity()
    time.sleep(0.25)
    assert sleep_time.is_idle() is True
    assert sleep_time.run_due_jobs()[0]["ok"] is True


def test_one_failing_job_does_not_stop_the_rest():
    sleep_time.register("boom", lambda: (_ for _ in ()).throw(RuntimeError("x")), min_interval_s=0)
    sleep_time.register("after", lambda: {"detail": "ok"}, min_interval_s=0)
    rows = {r["job"]: r for r in sleep_time.run_due_jobs(force=True)}
    assert rows["boom"]["ok"] is False
    assert rows["after"]["ok"] is True


def test_interval_prevents_rerunning_too_soon():
    calls = []
    sleep_time.register("j", lambda: calls.append(1) or {"detail": "x"}, min_interval_s=999)
    sleep_time.run_due_jobs(force=True)
    sleep_time.run_due_jobs()          # not forced -> interval blocks it
    assert len(calls) == 1


def test_default_jobs_are_registered_and_named():
    sleep_time.register_defaults()
    assert {"consolidate_workflows", "warm_model_discovery", "self_audit"} <= set(sleep_time._JOBS)


def test_status_reports_idle_state():
    sleep_time.note_activity()
    st = sleep_time.status()
    assert st["is_idle"] is False and st["idle_seconds"] >= 0
