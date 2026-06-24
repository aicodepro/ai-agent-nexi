from __future__ import annotations

from engine import workflow_state

_CANCEL_WORDS = {
    "cancel", "stop", "never mind", "nevermind", "exit", "leave it", "quit", "forget it",
}


def is_cancel_command(text: str) -> bool:
    return (text or "").strip().lower().rstrip(".!?") in _CANCEL_WORDS


def handle_active_workflow(query: str):
    wf = workflow_state.get_workflow()
    if not wf:
        return None
    if workflow_state.is_expired():
        workflow_state.clear_workflow()
        return "Cancelled."
    if is_cancel_command(query):
        workflow_state.clear_workflow()
        return "Cancelled."

    name = wf.get("name", "")
    if name == "create_folder":
        from engine.create_folder_workflow import handle_workflow_reply
        return handle_workflow_reply(query)
    if name.startswith("local_"):
        from engine.local_skills import continue_workflow
        return continue_workflow(query)

    workflow_state.clear_workflow()
    return "Cancelled."
