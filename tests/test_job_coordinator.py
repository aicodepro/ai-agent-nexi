"""Goal and job truthfulness.

The behaviour under test is the one that was actually wrong in the runtime:
starting work was reported as finished work. The live trace emitted
`verified=true` and `[TOOL] success` before the planner agent had run.

COMPLETED and verified are deliberately different things here. Reaching the end
of execution is not proof the postcondition holds.
"""
from __future__ import annotations

import pytest

from engine.job_coordinator import JobCoordinator, JobState


@pytest.fixture
def jc():
    return JobCoordinator()


# --- starting is not finishing -----------------------------------------------

def test_a_new_job_is_neither_complete_nor_verified(jc):
    jc.start_goal("create a folder")
    job = jc.add_job("create Project Alpha")
    assert job.state is JobState.QUEUED
    assert job.verified is False


def test_completed_is_not_verified(jc):
    jc.start_goal("create a folder")
    job = jc.add_job("create Project Alpha")
    jc.set_state(job.job_id, JobState.COMPLETED)

    assert jc.get(job.job_id).verified is False, "finishing execution was treated as proof"
    assert jc.progress_summary()["completed"] == []
    assert jc.progress_summary()["completed_unverified"] == ["create Project Alpha"]


def test_verification_is_what_makes_it_done(jc):
    jc.start_goal("create a folder")
    job = jc.add_job("create Project Alpha")
    jc.set_state(job.job_id, JobState.COMPLETED)
    jc.mark_verified(job.job_id, evidence="path exists: C:/Users/x/Desktop/Project Alpha")

    assert jc.get(job.job_id).verified is True
    assert jc.progress_summary()["completed"] == ["create Project Alpha"]
    assert jc.progress_summary()["all_done"] is True


def test_a_job_that_never_completed_cannot_be_verified(jc):
    """The executor must not be able to stamp its own unfinished work."""
    jc.start_goal("create a folder")
    job = jc.add_job("create Project Alpha")
    jc.set_state(job.job_id, JobState.RUNNING)
    jc.mark_verified(job.job_id, evidence="trust me")

    assert jc.get(job.job_id).verified is False


def test_leaving_completed_clears_a_stale_verified_flag(jc):
    jc.start_goal("g")
    job = jc.add_job("j")
    jc.set_state(job.job_id, JobState.COMPLETED)
    jc.mark_verified(job.job_id, evidence="ok")
    jc.set_state(job.job_id, JobState.FAILED, error="regressed")

    assert jc.get(job.job_id).verified is False


# --- what the user can ask ---------------------------------------------------

def test_progress_distinguishes_done_active_waiting_and_failed(jc):
    jc.start_goal("build a website")
    a = jc.add_job("create project structure")
    b = jc.add_job("install dependencies")
    c = jc.add_job("build auth module")
    d = jc.add_job("deploy")

    jc.set_state(a.job_id, JobState.COMPLETED); jc.mark_verified(a.job_id, "dir exists")
    jc.set_state(b.job_id, JobState.COMPLETED); jc.mark_verified(b.job_id, "lockfile written")
    jc.set_state(c.job_id, JobState.FAILED, error="auth module build failed")
    jc.set_state(d.job_id, JobState.WAITING_FOR_APPROVAL, blocked_reason="deploy needs approval")

    s = jc.progress_summary()
    assert s["completed"] == ["create project structure", "install dependencies"]
    assert s["failed"][0]["error"] == "auth module build failed"
    assert s["waiting"][0]["reason"] == "deploy needs approval"
    assert s["all_done"] is False


def test_missing_information_is_reportable(jc):
    jc.start_goal("create a folder")
    jc.set_missing_information(["folder_name", "folder_location"])
    assert jc.progress_summary()["missing_information"] == ["folder_name", "folder_location"]


# --- dependencies, retries, cancellation -------------------------------------

def test_a_dependency_blocks_until_it_is_verified(jc):
    jc.start_goal("g")
    first = jc.add_job("install dependencies")
    second = jc.add_job("run build", depends_on=[first.job_id])

    assert jc.blocking_dependencies(second.job_id) == [first.job_id]

    jc.set_state(first.job_id, JobState.COMPLETED)
    assert jc.blocking_dependencies(second.job_id) == [first.job_id], \
        "an unverified dependency was treated as satisfied"

    jc.mark_verified(first.job_id, "installed")
    assert jc.blocking_dependencies(second.job_id) == []


def test_retries_are_counted_and_bounded(jc):
    jc.start_goal("g")
    job = jc.add_job("flaky step", max_attempts=2)

    jc.set_state(job.job_id, JobState.RUNNING)
    jc.set_state(job.job_id, JobState.FAILED, error="boom")
    assert jc.get(job.job_id).can_retry() is True

    jc.set_state(job.job_id, JobState.RUNNING)
    jc.set_state(job.job_id, JobState.FAILED, error="boom again")
    assert jc.get(job.job_id).can_retry() is False, "retried past max_attempts"


def test_cancelling_a_goal_stops_only_unfinished_jobs(jc):
    jc.start_goal("g")
    done = jc.add_job("already done")
    running = jc.add_job("still going")
    jc.set_state(done.job_id, JobState.COMPLETED)
    jc.mark_verified(done.job_id, "ok")
    jc.set_state(running.job_id, JobState.RUNNING)

    assert jc.cancel_goal("user asked to stop") == 1
    assert jc.get(running.job_id).state is JobState.CANCELLED
    assert jc.get(done.job_id).state is JobState.COMPLETED


def test_evidence_accumulates_on_the_job(jc):
    jc.start_goal("g")
    job = jc.add_job("j")
    jc.set_state(job.job_id, JobState.RUNNING, evidence="started at 10:00")
    jc.set_state(job.job_id, JobState.COMPLETED, evidence="exit code 0")
    jc.mark_verified(job.job_id, "path exists")

    assert len(jc.get(job.job_id).evidence) == 3
