import threading


def test_concurrent_workflow_slot_updates_do_not_lose_slots():
    from engine import workflow_state

    workflow_state.start_workflow("demo", "collect", {"initial": True})
    threads = [
        threading.Thread(target=workflow_state.update_workflow, kwargs={"slots": {f"slot_{i}": i}})
        for i in range(10)
    ]

    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    slots = workflow_state.get_workflow()["slots"]
    assert slots["initial"] is True
    assert slots == {"initial": True, **{f"slot_{i}": i for i in range(10)}}
    workflow_state.clear_workflow()


def test_workflow_does_not_share_nested_slot_state_with_callers():
    from engine import workflow_state

    slots = {"options": {"mode": "safe"}}
    workflow_state.start_workflow("demo", "collect", slots)
    slots["options"]["mode"] = "control"

    assert workflow_state.get_workflow()["slots"]["options"]["mode"] == "safe"
    workflow_state.clear_workflow()


def test_workflow_update_copies_nested_slot_state():
    from engine import workflow_state

    workflow_state.start_workflow("demo", "collect")
    update = {"options": {"mode": "safe"}}
    workflow_state.update_workflow(slots=update)
    update["options"]["mode"] = "control"

    assert workflow_state.get_workflow()["slots"]["options"]["mode"] == "safe"
    workflow_state.clear_workflow()
