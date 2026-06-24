from __future__ import annotations

from engine import workflow_state


def has_active_workflow() -> bool:
    return workflow_state.has_active_workflow()


def get_active_workflow_context() -> dict:
    return dict(workflow_state.get_workflow() or {})


def cancel_workflow(reason: str = "") -> None:
    print(f"[WORKFLOW] cancelled reason={(reason or '').strip()}", flush=True)
    workflow_state.clear_workflow()


def pause_workflow(reason: str = "") -> None:
    print(f"[WORKFLOW] paused reason={(reason or '').strip()}", flush=True)


def _switch_target(planner: dict) -> str:
    route = planner.get("route", "")
    intent = planner.get("intent", "")
    if route == "repeat_last":
        return "repeat_last"
    if intent in {"essay_request", "general_qa", "summarize", "explain"}:
        return "brain"
    if intent in {"open_app", "open_website", "web_search", "local_skill"}:
        return "local_skill"
    return route or intent or "unknown"


def start_workflow(intent: str, initial_text: str, source: str) -> dict:
    if intent == "create_folder":
        from engine.create_folder_workflow import start_create_folder
        response = start_create_folder(initial_text)
        return _result(response, expects_user_reply=response.endswith("?"), workflow_id="create_folder")
    return _result("I don't know how to start that workflow yet.", False, "")


def handle_workflow_turn(text: str, source: str) -> dict:
    wf = workflow_state.get_workflow()
    if not wf:
        return _result("", False, "", handled=False)

    from engine.groq_intent_planner import classify_intent
    planner = classify_intent(text, source=source, active_workflow=wf)
    if planner.get("route") in {"cancel", "interrupt"} or planner.get("workflow_action") == "cancel":
        cancel_workflow("user_request")
        return _result("Cancelled.", False, wf.get("name", ""))
    if planner.get("route") in {"workflow_switch", "repeat_last"} or planner.get("workflow_action") == "switch":
        pause_workflow("intent_switch")
        print(f"[WORKFLOW] switch_detected from={wf.get('name', '')} to={_switch_target(planner)}", flush=True)
        return {
            "handled": False,
            "response": "Alright, I'll pause that task.",
            "expects_user_reply": False,
            "workflow_id": wf.get("name", ""),
            "action_executed": False,
            "switch": True,
            "planner": planner,
        }

    from engine.workflow_manager import handle_active_workflow
    response = handle_active_workflow(text)
    if response is None:
        return _result("", False, "", handled=False)
    return _result(response, expects_user_reply=response.endswith("?"), workflow_id=wf.get("name", ""))


def _result(response: str, expects_user_reply: bool, workflow_id: str, handled: bool = True) -> dict:
    return {
        "handled": handled,
        "response": response,
        "expects_user_reply": expects_user_reply,
        "workflow_id": workflow_id,
        "action_executed": bool(response and not expects_user_reply and response.lower().startswith("done")),
    }
