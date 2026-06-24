import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_session_memory_stores_recent_turns():
    from engine.memory.session_memory import SessionMemory

    memory = SessionMemory(max_turns=2)
    assert memory.add_user_turn("hello", source="typed") is True
    assert memory.add_assistant_turn("Hi there.") is True
    assert memory.add_user_turn("open chrome", source="typed") is True

    recent = memory.get_recent(5)
    assert len(recent) == 2
    assert recent[-1]["text"] == "open chrome"
    assert memory.get_last_user_input() == "open chrome"
    assert memory.get_last_assistant_response() == "Hi there."


def test_session_memory_context_string():
    from engine.memory.session_memory import SessionMemory

    memory = SessionMemory()
    memory.add_user_turn("what is ai", source="typed")
    memory.add_assistant_turn("AI means artificial intelligence.")
    context = memory.to_context_string()
    assert "User: what is ai" in context
    assert "Jarvis: AI means artificial intelligence." in context


def test_session_memory_filters_secret_text():
    from engine.memory.session_memory import SessionMemory

    memory = SessionMemory()
    assert memory.add_user_turn("my password is 123", source="typed") is False
    assert memory.count() == 0


def test_global_session_memory_clears_on_wake_finish():
    from engine.memory.session_memory import add_user_turn, get_session_memory
    from engine.wake_session_manager import finish_session, start_session

    finish_session("test")
    memory = get_session_memory()
    memory.clear()
    add_user_turn("before session", "typed")
    assert memory.count() == 1
    start_session("test")
    assert memory.count() == 0
    add_user_turn("during session", "hotword")
    assert memory.count() == 1
    finish_session("test")
    assert memory.count() == 0


def test_command_bus_adds_user_turn_to_session_memory(monkeypatch):
    from engine.memory.session_memory import get_session_memory
    from engine.command_bus import submit_user_command

    memory = get_session_memory()
    memory.clear()
    with monkeypatch.context() as m:
        m.setattr("engine.command.allCommands", lambda text: True)
        submit_user_command("hello", source="typed")
    assert memory.get_last_user_input() == "hello"
