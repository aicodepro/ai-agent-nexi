"""Orchestrator: dispatch a coding task to Claude Code, then verify the result.

Exposes the Nexi tool wrappers (nexi_code_task/nexi_code_stop) and the eel bridge
functions that stream a live run to the UI panel.
"""
import os
import threading

from engine.claude_code import dispatcher, verifier


def run_task(task, project_dir=None, *, verify=True, on_event=None, run_tests_after=True, verifier_fn=None):
    """Dispatch -> verify. Returns {ok, on_track, dispatch, verify, message}."""
    result = dispatcher.dispatch(task, project_dir=project_dir, on_event=on_event)
    if result.get("reason"):  # disabled / empty / claude_not_found — nothing ran
        return {"ok": False, "on_track": False, "dispatch": result, "verify": None,
                "message": result.get("message")}

    v = None
    if verify:
        v = verifier.verify(task, project_dir or os.getcwd(), result,
                            run_tests_after=run_tests_after, verifier_fn=verifier_fn)
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
    return f"Claude Code finished and verified on-track ({where}; tests ok)."


def stop() -> bool:
    return dispatcher.stop()


# ── Nexi tool wrappers ────────────────────────────────────────────────────────
def nexi_code_task(task="", project_dir=None, **_):
    return run_task(task, project_dir=project_dir)


def nexi_code_stop(**_):
    return {"ok": stop(), "message": "Stopped the Claude Code run."}


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
        final = run_task(task, project_dir=project_dir, verify=verify, on_event=on_event)
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
        return {"ok": stop()}
