import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_ask_brain_defaults_to_gemini(monkeypatch):
    from engine import features
    features._brain_fail_until = 0.0
    monkeypatch.delenv("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_PRIMARY", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_FALLBACK", raising=False)
    with patch("engine.gemini_brain.ask_gemini", return_value="Gemini answer.") as mock_gemini:
        assert features.ask_brain("explain python") == "Gemini answer."
    mock_gemini.assert_called_once()


def test_stale_hugchat_primary_is_ignored_without_legacy_enable(monkeypatch):
    from engine import features
    monkeypatch.setenv("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS", "false")
    monkeypatch.setenv("NEXI_BRAIN_PRIMARY", "hugchat")
    monkeypatch.setenv("NEXI_BRAIN_FALLBACK", "lightning")
    assert features._resolve_provider_chain() == ["gemini"]


def test_memory_command_does_not_call_gemini(tmp_path, monkeypatch):
    import engine.command as command
    from engine import memory_store, workflow_state
    from engine.followup_manager import clear_followup
    clear_followup("test_cleanup")
    workflow_state.clear_workflow()
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "nexi_memory.json")
    with patch("engine.gemini_brain.ask_gemini") as mock_gemini, \
         patch("engine.command.speak") as mock_speak, \
         patch("engine.command.eel"):
        command.allCommands("remember tomorrow is your presentation")
    mock_gemini.assert_not_called()
    mock_speak.assert_called_once()
    assert "Remembered" in mock_speak.call_args.args[0]


def test_brain_failure_message_is_demo_safe(monkeypatch):
    from engine import features
    features._brain_fail_until = 0.0
    monkeypatch.delenv("NEXI_ENABLE_LEGACY_BRAIN_PROVIDERS", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_PRIMARY", raising=False)
    monkeypatch.delenv("NEXI_BRAIN_FALLBACK", raising=False)
    with patch("engine.gemini_brain.ask_gemini", side_effect=RuntimeError("down")):
        result = features.ask_brain("what is 2+2")
    assert result == "I can't connect to my brain right now, but local actions are working."
    assert "providers" not in result.lower()
