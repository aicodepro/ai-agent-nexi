import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_memory_remember_and_recall(tmp_path, monkeypatch):
    from engine import memory_store
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "jarvis_memory.json")
    monkeypatch.setattr("engine.memory_store.remember", lambda *a, **kw: {})
    monkeypatch.setattr("engine.memory_store._grouped_memory_summary", lambda q="": "")
    assert memory_store.remember_fact("tomorrow is your presentation") == "Remembered. Tomorrow is your presentation."
    result = memory_store.parse_memory_command("show memory")
    assert "tomorrow is your presentation" in result


def test_note_saved_to_memory(tmp_path, monkeypatch):
    from engine import memory_store
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "jarvis_memory.json")
    assert memory_store.add_note("buy milk") == "Note saved."
    assert "buy milk" in memory_store.show_notes()


def test_show_memory_command(tmp_path, monkeypatch):
    from engine import memory_store
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "jarvis_memory.json")
    monkeypatch.setattr("engine.memory_store.remember", lambda *a, **kw: {})
    monkeypatch.setattr("engine.memory_store._grouped_memory_summary", lambda q="": "")
    memory_store.remember_fact("demo starts at 10")
    assert "demo starts at 10" in memory_store.parse_memory_command("show memory")


def test_memory_logs_safe_events(tmp_path, monkeypatch, capsys):
    from engine import memory_store
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "jarvis_memory.json")
    monkeypatch.setattr("engine.memory_store.remember", lambda *a, **kw: {})
    memory_store.remember_fact("demo starts at 10")
    out = capsys.readouterr().out
    assert "[MEMORY] intent=remember" in out
    assert "[MEMORY] saved key=demo_starts_at_10" in out


def test_brain_memory_context_filters_empty_and_secrets(tmp_path, monkeypatch):
    from engine import memory_store
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "jarvis_memory.json")
    monkeypatch.setattr("engine.memory_store.remember", lambda *a, **kw: {})
    memory_store.remember_fact("project is due tomorrow")
    assert "project is due tomorrow" in memory_store.get_brain_memory_context()
    assert memory_store.remember_fact("api key is secret") == "I can't store secrets or empty memories."
