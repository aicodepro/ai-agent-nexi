"""Nexi-supervised provider-neutral agent session orchestration."""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any

from engine.agent_runtime.adapters import sanitize_runtime_value
from engine.agent_runtime.contracts import AgentRunRequest
from engine.agent_runtime import registry
from engine.claude_code import verifier


_OWNER_PROVIDERS: dict[str, str] = {}
_OWNER_LOCK = threading.RLock()


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
    provider_id=None,
):
    """Execute through the selected adapter, then verify independently."""
    del allowlisted_skills
    provider = registry.canonical_provider_id(provider_id or registry.selected_provider_id())
    if not registry.runtime_enabled(provider):
        return {
            "ok": False,
            "on_track": False,
            "dispatch": {"ok": False, "reason": "disabled", "provider_id": provider},
            "verify": None,
            "provider_id": provider,
            "message": f"Nexi agent runtime provider '{provider}' is disabled.",
        }
    adapter = registry.get_adapter(provider)
    if not adapter.available():
        return {
            "ok": False,
            "on_track": False,
            "dispatch": {"ok": False, "reason": "provider_unavailable", "provider_id": provider},
            "verify": None,
            "provider_id": provider,
            "message": f"Nexi agent runtime provider '{provider}' is not installed or configured.",
        }
    owner = str(owner_id or "nexi-agent-runtime")
    if resume_session_id is not None:
        resume_session_id = adapter.validate_session_id(resume_session_id)
    request = AgentRunRequest(
        task=str(task or ""),
        project_dir=os.path.abspath(os.path.expanduser(project_dir or os.getcwd())),
        owner_id=owner,
        permission_mode=str(permission_mode or "acceptEdits"),
        agent_name=agent_name,
        agents_json=agents_json,
        resume_session_id=resume_session_id,
        fork_session=bool(fork_session),
        control_cwd=control_cwd,
        extra_args=tuple(extra_args or ()),
    )
    with _OWNER_LOCK:
        if owner in _OWNER_PROVIDERS:
            return {
                "ok": False,
                "on_track": False,
                "dispatch": {"ok": False, "reason": "owner_busy", "provider_id": provider},
                "verify": None,
                "provider_id": provider,
                "message": f"Nexi agent runtime owner '{owner}' already has an active task.",
            }
        _OWNER_PROVIDERS[owner] = provider
    def safe_event(event):
        if on_event:
            try:
                on_event(sanitize_runtime_value(event))
            except Exception:
                pass
    try:
        dispatch = adapter.execute(request, on_event=safe_event)
    except Exception:
        with _OWNER_LOCK:
            _OWNER_PROVIDERS.pop(owner, None)
        raise
    if dispatch.get("reason") or not dispatch.get("ok"):
        verifier.clear_test_cancellation(owner_id)
        with _OWNER_LOCK:
            _OWNER_PROVIDERS.pop(owner, None)
        return {
            "ok": False,
            "on_track": False,
            "dispatch": sanitize_runtime_value(dispatch),
            "verify": None,
            "provider_id": provider,
            "message": dispatch.get("message") or f"{provider} run failed.",
        }
    verification = None
    try:
        if verify:
            verification = verifier.verify(
                str(task or ""),
                request.project_dir,
                dispatch,
                run_tests_after=run_tests_after,
                verifier_fn=verifier_fn,
                baseline=baseline,
                test_cmd=test_cmd,
                require_tests=require_tests,
                owner_id=owner_id,
            )
    finally:
        verifier.clear_test_cancellation(owner_id)
        with _OWNER_LOCK:
            _OWNER_PROVIDERS.pop(owner, None)
    on_track = verification["on_track"] if verification else bool(dispatch.get("ok"))
    return {
        "ok": bool(dispatch.get("ok")),
        "on_track": bool(on_track),
        "dispatch": sanitize_runtime_value(dispatch),
        "verify": verification,
        "provider_id": provider,
        "message": _summary(provider, dispatch, verification),
    }


def _summary(provider: str, dispatch: dict[str, Any], verification: dict[str, Any] | None) -> str:
    if not dispatch.get("ok"):
        return str(dispatch.get("message") or f"{provider} run failed.")
    if verification is None:
        return f"{provider} finished under Nexi supervision."
    checks = verification.get("checks", {})
    if not verification.get("on_track"):
        reasons = []
        if not checks.get("made_changes"):
            reasons.append("no files changed")
        if checks.get("tests_ran") and not checks.get("tests_passed"):
            reasons.append("tests failing")
        if checks.get("model_verdict") is False:
            reasons.append("verifier flagged it off-task")
        return f"{provider} ran but Nexi marked it off-track ({', '.join(reasons) or 'unverified'})."
    test_note = "tests ok" if checks.get("tests_ran") and checks.get("tests_passed") else "tests skipped"
    return f"{provider} finished and Nexi verified it on-track ({test_note})."


def stop(owner_id=None, provider_id=None) -> bool:
    owner = str(owner_id or "")
    with _OWNER_LOCK:
        provider = _OWNER_PROVIDERS.get(owner)
    provider = registry.canonical_provider_id(provider_id or provider or registry.selected_provider_id())
    provider_stopped = registry.get_adapter(provider).stop(owner_id=owner_id)
    tests_stopped = verifier.cancel_tests(owner) if owner else True
    return bool(provider_stopped and tests_stopped)


def runtime_status() -> dict[str, Any]:
    return {
        "selected_provider": registry.selected_provider_id(),
        "providers": registry.all_provider_statuses(),
    }


def start_streaming(task, project_dir=None, emit=None, verify=True, provider_id=None):
    """Run the selected provider on a daemon thread and emit normalized events."""
    try:
        provider = registry.canonical_provider_id(provider_id or registry.selected_provider_id())
    except ValueError as exc:
        return {"ok": False, "reason": "invalid_provider", "message": str(exc)}
    owner = f"ui-agent-runtime-{uuid.uuid4().hex}"
    def work():
        def on_event(event):
            if emit:
                try:
                    emit({"kind": "event", "event": event})
                except Exception:
                    pass
        result = run_task(
            task,
            project_dir=project_dir,
            verify=verify,
            on_event=on_event,
            owner_id=owner,
            provider_id=provider,
        )
        if emit:
            try:
                emit({"kind": "done", "result": result})
            except Exception:
                pass

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True, "provider_id": provider, "owner_id": owner, "message": "started"}


def register_eel(eel) -> None:
    @eel.expose
    def agent_runtime_start(task, project_dir=None, provider_id=None):  # noqa: unused
        del task, project_dir, provider_id
        return {
            "ok": False,
            "reason": "studio_authorization_required",
            "message": "Direct UI execution is disabled. Start work with an exact authorized Nexi Studio build command.",
        }

    @eel.expose
    def agent_runtime_stop():  # noqa: unused
        return {"ok": False, "reason": "run_id_required", "message": "Cancel the active run through Nexi Studio authorization."}

    @eel.expose
    def agent_runtime_status():  # noqa: unused
        return runtime_status()
