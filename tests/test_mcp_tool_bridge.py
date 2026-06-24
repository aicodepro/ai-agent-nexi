import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_read_only_tools_allowed():
    from engine.mcp_tool_bridge import is_tool_allowed
    assert is_tool_allowed("memory.summary") is True
    assert is_tool_allowed("local_skills.list") is True


def test_forbidden_tools_blocked():
    from engine.mcp_tool_bridge import execute_mcp_tool
    result = execute_mcp_tool("shell.run", {"command": "dir"})
    assert result.ok is False
    assert result.error_code == "TOOL_BLOCKED"


def test_memory_summary_tool_is_read_only(tmp_path, monkeypatch):
    from engine import memory_store
    from engine.mcp_tool_bridge import execute_mcp_tool
    monkeypatch.setattr(memory_store, "MEMORY_PATH", tmp_path / "jarvis_memory.json")
    monkeypatch.setattr("engine.memory_store.remember", lambda *a, **kw: {})
    monkeypatch.setattr("engine.memory_store._grouped_memory_summary", lambda q="": "")
    memory_store.remember_fact("demo is tomorrow")
    result = execute_mcp_tool("memory.summary")
    assert result.ok is True
    assert "demo is tomorrow" in result.data["text"]
