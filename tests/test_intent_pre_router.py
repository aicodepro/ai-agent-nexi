import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_active_training_only_captures_plausible_training_instruction():
    from engine.intent_pre_router import pre_route

    context = {"active_training": {"need": "coding"}}

    training = pre_route(
        "For coding tasks, inspect files before editing and run focused tests.",
        context=context,
    )
    normal_command = pre_route("open chrome", context=context)

    assert training is not None
    assert training["route"] == "training"
    assert training["intent"] == "training_answer"
    assert normal_command is None
