import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_local_first_commands_do_not_call_gemini(tmp_path, monkeypatch):
    import engine.command as command
    from engine import memory_store, workflow_state
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "nexi_memory.json")
    commands = [
        "remember that tomorrow is my presentation",
        "what do you remember",
        "create a folder",
    ]
    with patch("engine.gemini_brain.ask_gemini") as mock_gemini, \
         patch("engine.command.speak"), \
         patch("engine.command.safe_eel_call"):
        for text in commands:
            workflow_state.clear_workflow()
            command.allCommands(text)
    mock_gemini.assert_not_called()
    workflow_state.clear_workflow()


def test_open_and_search_local_skills_do_not_call_gemini():
    import engine.command as command
    with patch("engine.gemini_brain.ask_gemini") as mock_gemini, \
         patch("engine.local_skills.subprocess.Popen"), \
         patch("engine.local_skills.webbrowser.open"), \
         patch("engine.command.speak"), \
         patch("engine.command.safe_eel_call"):
        command.allCommands("open chrome")
        command.allCommands("search ronaldo")
    mock_gemini.assert_not_called()


def test_gemini_model_chain_uses_25_flash(monkeypatch):
    from engine.gemini_brain import get_gemini_model_chain
    monkeypatch.delenv("GEMINI_MODEL_CHAIN", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.delenv("GEMINI_MODEL_PRIMARY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL_FALLBACK", raising=False)
    chain = get_gemini_model_chain()
    assert chain[0] == "gemini-2.5-flash"
    assert "gemini-2.0-flash" not in chain
    assert "gemini-1.5-flash" not in chain
