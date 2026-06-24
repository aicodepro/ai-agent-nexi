import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_ui_state_manager_contract_flow():
    from engine.ui_state_manager import UIStateManager

    mgr = UIStateManager(dedupe_ms=0)
    states = ["sleep", "online", "listening", "recognising", "thinking", "saying", "sleep"]
    events = [mgr.emit(state, source="hotword") for state in states]
    assert [event.state for event in events if event] == states
    assert events[1].label == "ONLINE"
    assert events[-1].label == "SLEEPING"


def test_ui_state_manager_aliases_speaking_to_saying():
    from engine.ui_state_manager import canonical_state

    assert canonical_state("speaking") == "saying"
    assert canonical_state("online") == "online"
