import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tool_result_required_before_done_message(capsys):
    from engine.assistant_response import guard_unverified_action_message

    guarded = guard_unverified_action_message("Done. File created.")
    assert not guarded.lower().startswith("done")
    assert "couldn't verify" in guarded.lower()
    assert "[HALLUCINATION_GUARD] blocked_unverified_action" in capsys.readouterr().out


def test_verified_tool_result_allows_success_message():
    from engine.assistant_response import guard_unverified_action_message

    result = {"success": True, "message": "Opening chrome.", "tool": "open_app", "verified": True}
    assert guard_unverified_action_message("Opening chrome.", result) == "Opening chrome."
