import os
import sys
import threading
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_typed_and_voice_use_same_command_bus():
    from engine.command_bus import submit_user_command
    with patch("engine.command.allCommands") as mock_all:
        submit_user_command("search ronaldo", source="typed", mode="typed")
        submit_user_command("search messi", source="hotword", mode="voice")
    assert mock_all.call_args_list[0].args == ("search ronaldo",)
    assert mock_all.call_args_list[1].args == ("search messi",)


def test_voice_command_posts_to_bridge_only():
    import multiprocessing
    from engine.audio_wake_pipeline import AudioWakePipeline
    q = multiprocessing.Queue()
    pipeline = AudioWakePipeline(command_queue=q, asr=lambda a, s: "search messi")
    with patch("engine.command.allCommands") as mock_all:
        pipeline.emit_command(b"\x00\x00" * 1600, source="clap")
    mock_all.assert_not_called()
    events = [q.get(timeout=1), q.get(timeout=1), q.get(timeout=1)]
    assert any(event["type"] == "command_text" and event["text"] == "search messi" for event in events)


def test_rejected_voice_clarification_is_handled_without_dispatch():
    from engine.command_bus import submit_user_command
    with patch("engine.command.allCommands") as mock_all, patch("engine.command.speak") as mock_speak:
        assert submit_user_command("Sarıç", source="hotword", mode="voice") is True
    mock_all.assert_not_called()
    mock_speak.assert_called_once()


def test_short_voice_goodbye_dispatches():
    from engine.command_bus import submit_user_command

    with patch("engine.command.allCommands") as mock_all:
        assert submit_user_command("Bye.", source="hotword", mode="voice") is True

    mock_all.assert_called_once_with("Bye.")


def test_explicit_studio_voice_command_bypasses_generic_transcript_filter():
    from engine.command_bus import submit_user_command

    with patch("engine.command.allCommands") as mock_all, patch("engine.command.speak") as mock_speak:
        assert submit_user_command("Studio mode", source="hotword", mode="voice") is True

    mock_all.assert_called_once_with("Studio mode")
    mock_speak.assert_not_called()


def test_voice_dispatch_does_not_start_post_tts_cleanup():
    from engine.command_bus import submit_user_command

    cleanup_called = threading.Event()
    with patch("engine.command.allCommands"), patch(
        "engine.post_tts_cleanup.post_tts_cleanup",
        side_effect=cleanup_called.set,
    ):
        assert submit_user_command("search ronaldo", source="hotword", mode="voice") is True

    assert cleanup_called.wait(0.1) is False


@pytest.mark.parametrize(
    "command",
    [
        "Nexi, start building a finance app",
        "Hey Nexi, studio status",
        "Nexi, cancel studio build",
        "Hey Nexi, studio continue: use Stripe",
    ],
)
def test_explicit_studio_command_clears_pending_without_rewrite(command):
    from engine.clarification_manager import ask_custom_clarification, has_pending_clarification
    from engine.command_bus import submit_user_command
    from engine.followup_manager import has_pending_followup

    ask_custom_clarification("Which app?", followup_type="open_app", reason="test")
    with patch("engine.command.allCommands") as mock_all:
        assert submit_user_command(command, source="typed", mode="typed") is True

    mock_all.assert_called_once_with(command)
    assert has_pending_clarification() is False
    assert has_pending_followup() is False


def test_explicit_studio_command_bypasses_active_local_workflow():
    import engine.command as command
    from engine.command_bus import dispatch_unified_command
    from engine.workflow_dialog_manager import cancel_workflow, start_workflow

    cancel_workflow("test_setup")
    start_workflow("create_folder", "create a folder", "typed")
    try:
        with patch.object(command, "_handle_product_intelligence_v2", return_value=True) as product, \
             patch("engine.workflow_dialog_manager.handle_workflow_turn") as workflow, \
             patch.object(command, "safe_eel_call"):
            dispatch_unified_command("Nexi, studio status", source="typed")
        product.assert_called_once_with("Nexi, studio status", "typed")
        workflow.assert_not_called()
    finally:
        cancel_workflow("test_teardown")


def test_pending_studio_goal_answer_reconstructs_explicit_build_command():
    from engine.command_bus import submit_user_command
    from engine.followup_manager import clear_followup, set_pending_followup

    clear_followup("test_setup")
    set_pending_followup("What should we build now?", "nexi_start_studio_build", "clarify")
    try:
        with patch("engine.command.allCommands") as mock_all:
            assert submit_user_command("a coffee landing page", source="hotword", mode="voice") is True
        mock_all.assert_called_once_with("let's build a coffee landing page")
    finally:
        clear_followup("test_teardown")
