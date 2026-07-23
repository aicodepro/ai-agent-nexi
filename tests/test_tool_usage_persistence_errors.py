import pytest


def test_corrupt_tool_history_load_is_observable(monkeypatch, tmp_path):
    import engine.tool_usage_intelligence as tool_ai

    history = tmp_path / "tools.json"
    history.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", history)

    with pytest.warns(RuntimeWarning, match="tool usage history"):
        assert tool_ai._load() == {"tools": {}}


def test_tool_history_save_failure_is_atomic_and_observable(monkeypatch, tmp_path):
    import engine.tool_usage_intelligence as tool_ai

    history = tmp_path / "tools.json"
    history.write_text('{"tools":{"existing":{}}}', encoding="utf-8")
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", history)
    monkeypatch.setattr(tool_ai.os, "replace", lambda *_args: (_ for _ in ()).throw(OSError("replace failed")))

    with pytest.raises(OSError, match="replace failed"):
        tool_ai._save({"tools": {"new": {}}})

    assert history.read_text(encoding="utf-8") == '{"tools":{"existing":{}}}'
