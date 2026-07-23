import os
import sys
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_tool_alias_youtube_to_website(monkeypatch, tmp_path):
    import engine.tool_usage_intelligence as tool_ai
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", tmp_path / "tools.json")
    alias = tool_ai.resolve_tool_alias("youtube")
    assert alias["handled"] is True
    assert alias["name"] == "open_website"
    assert alias["slots"]["url"] == "youtube.com"


def test_tool_result_required_for_done():
    from engine.assistant_response import guard_unverified_action_message
    text = guard_unverified_action_message("Done. Opened Chrome.", {"success": False})
    assert "couldn't verify" in text


def test_tool_result_updates_are_serialized(monkeypatch, tmp_path):
    import engine.tool_usage_intelligence as tool_ai

    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", tmp_path / "tools.json")
    original_load = tool_ai._load
    guard = threading.Lock()
    active = 0
    max_active = 0

    def slow_load():
        nonlocal active, max_active
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        data = original_load()
        with guard:
            active -= 1
        return data

    monkeypatch.setattr(tool_ai, "_load", slow_load)
    threads = [
        threading.Thread(target=tool_ai.record_tool_result, args=("demo", {}, {"success": True}))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert max_active == 1


def test_tool_history_write_is_atomic(monkeypatch, tmp_path):
    import engine.tool_usage_intelligence as tool_ai

    target = tmp_path / "tools.json"
    monkeypatch.setattr(tool_ai, "TOOL_HISTORY_PATH", target)
    real_replace = os.replace
    calls = []

    def replace(source, destination):
        calls.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    tool_ai._save({"tools": {}})

    assert calls
    assert target.read_text(encoding="utf-8")
