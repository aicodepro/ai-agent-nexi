"""Orchestrator: dispatch a coding task to Claude Code, then verify the result.

Exposes the Nexi tool wrappers (nexi_code_task/nexi_code_stop) and the eel bridge
functions that stream a live run to the UI panel.
"""
import os
import threading

from engine.claude_code import dispatcher, verifier


def run_task(
    task,
    project_dir=None,
    *,
    verify=True,
    on_event=None,
    run_tests_after=True,
    verifier_fn=None,
    baseline=None,
    test_cmd=None,
    require_tests=False,
    owner_id=None,
    permission_mode=None,
    extra_args=None,
    agent_name=None,
    agents_json=None,
    allowlisted_skills=None,
    resume_session_id=None,
    fork_session=False,
    control_cwd=None,
):
    """Dispatch -> verify. Returns {ok, on_track, dispatch, verify, message}."""
    dispatch_kwargs = {"project_dir": project_dir, "on_event": on_event}
    if owner_id is not None:
        dispatch_kwargs["owner_id"] = owner_id
    if permission_mode is not None:
        dispatch_kwargs["permission_mode"] = permission_mode
    if extra_args:
        dispatch_kwargs["extra_args"] = list(extra_args)
    if agent_name is not None:
        dispatch_kwargs["agent_name"] = agent_name
    if agents_json is not None:
        dispatch_kwargs["agents_json"] = agents_json
    if allowlisted_skills is not None:
        dispatch_kwargs["allowlisted_skills"] = list(allowlisted_skills)
    if resume_session_id is not None:
        dispatch_kwargs["resume_session_id"] = resume_session_id
    if fork_session:
        dispatch_kwargs["fork_session"] = True
    if control_cwd is not None:
        dispatch_kwargs["control_cwd"] = control_cwd
    result = dispatcher.dispatch(task, **dispatch_kwargs)
    if result.get("reason") or not result.get("ok"):
        verifier.clear_test_cancellation(owner_id)
        return {"ok": False, "on_track": False, "dispatch": result, "verify": None,
                "message": result.get("message") or "Claude Code run failed."}

    v = None
    try:
        if verify:
            v = verifier.verify(task, project_dir or os.getcwd(), result,
                                run_tests_after=run_tests_after, verifier_fn=verifier_fn,
                                baseline=baseline, test_cmd=test_cmd, require_tests=require_tests,
                                owner_id=owner_id)
    finally:
        verifier.clear_test_cancellation(owner_id)
    on_track = v["on_track"] if v else bool(result.get("ok"))
    return {
        "ok": bool(result.get("ok")),
        "on_track": bool(on_track),
        "dispatch": result,
        "verify": v,
        "message": _summary(result, v),
    }


def _summary(result, v) -> str:
    if not result.get("ok"):
        return result.get("message") or "Claude Code run failed."
    if v is None:
        return "Claude Code finished."
    checks = v.get("checks", {})
    if not v.get("on_track"):
        why = []
        if not checks.get("made_changes"):
            why.append("no files changed")
        if checks.get("tests_ran") and not checks.get("tests_passed"):
            why.append("tests failing")
        if checks.get("model_verdict") is False:
            why.append("verifier flagged it off-task")
        return f"Claude Code ran but looks off-track ({', '.join(why) or 'unverified'}). Review before trusting it."
    last_diff = checks.get("diff_stat", "").splitlines()
    where = last_diff[-1].strip() if last_diff else "changes applied"
    test_note = "tests ok" if checks.get("tests_ran") and checks.get("tests_passed") else "tests skipped"
    return f"Claude Code finished and verified on-track ({where}; {test_note})."


def stop(owner_id=None) -> bool:
    claude_stopped = dispatcher.stop(owner_id=owner_id)
    tests_stopped = verifier.cancel_tests(str(owner_id or "")) if owner_id else True
    return bool(claude_stopped and tests_stopped)


# ── Nexi tool wrappers ────────────────────────────────────────────────────────
def nexi_code_task(task="", project_dir=None, **_):
    return run_task(task, project_dir=project_dir, owner_id="nexi-code")


def nexi_code_stop(**_):
    return {"ok": stop(owner_id="nexi-code"), "message": "Stopped the Claude Code run."}


# ── Live streaming to the UI panel ────────────────────────────────────────────
def start_streaming(task, project_dir=None, emit=None, verify=True):
    """Run a task on a daemon thread, pushing each event to `emit`. Returns at once."""
    def _work():
        def on_event(ev):
            if emit:
                try:
                    emit({"kind": "event", "event": ev})
                except Exception:
                    pass
        final = run_task(task, project_dir=project_dir, verify=verify, on_event=on_event, owner_id="ui")
        if emit:
            try:
                emit({"kind": "done", "result": final})
            except Exception:
                pass

    threading.Thread(target=_work, daemon=True).start()
    return {"ok": True, "message": "started"}


def register_eel(eel) -> None:
    """Wire the UI panel <-> dispatcher. Call once at UI startup when the feature is on."""
    @eel.expose
    def claude_code_start(task, project_dir=None):  # noqa: unused (exposed to JS)
        def emit(payload):
            try:
                eel.claude_code_event(payload)()
            except Exception:
                pass
        return start_streaming(task, project_dir=project_dir, emit=emit)

    @eel.expose
    def claude_code_stop():  # noqa: unused (exposed to JS)
        return {"ok": stop(owner_id="ui")}
