import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_reflection_memory_store_recall_and_context(tmp_path, monkeypatch):
    from engine.reflection_memory import ReflectionMemory

    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    lesson_id = ReflectionMemory.store_lesson(
        failure="open_app failed verification",
        lesson="Opening apps needs verification.",
        next_action="Check the process or window before saying done.",
        context="tool=open_app verification",
        tool_name="open_app",
    )
    assert lesson_id.startswith("ref_")
    matches = ReflectionMemory.recall_similar("open_app verification failed", top_k=1)
    assert matches[0]["tool_name"] == "open_app"
    context = ReflectionMemory.get_context("open_app verification failed", max_lessons=1)
    assert "Lessons from past experience" in context
    assert "Check the process" in context


def test_reflection_memory_deduplicates_failure(tmp_path, monkeypatch):
    from engine.reflection_memory import ReflectionMemory

    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    first = ReflectionMemory.store_lesson("same failure", "first lesson")
    second = ReflectionMemory.store_lesson("same failure", "better lesson")
    assert first == second
    assert ReflectionMemory.count() == 1
    assert ReflectionMemory.recall_similar("same failure", top_k=1)[0]["count"] == 2


def test_reflection_memory_skips_secrets(tmp_path, monkeypatch):
    from engine.reflection_memory import ReflectionMemory

    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    lesson_id = ReflectionMemory.store_lesson("api key leaked", "never store secrets")
    assert lesson_id == ""
    assert ReflectionMemory.count() == 0


def test_reflection_memory_prunes_old_lessons(tmp_path, monkeypatch):
    from engine.reflection_memory import ReflectionMemory

    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    ReflectionMemory.store_lesson("old failure", "old lesson")
    data = ReflectionMemory._load()
    data["lessons"][0]["timestamp"] = time.time() - 86400 * 40
    ReflectionMemory._save(data)
    ReflectionMemory.store_lesson("new failure", "new lesson")
    assert ReflectionMemory.prune_old(days=30) == 1
    assert ReflectionMemory.count() == 1


def test_reflection_engine_feeds_reflection_memory(monkeypatch, tmp_path):
    import engine.adaptive_memory as adaptive_memory
    import engine.reflection_engine as reflection_engine
    from engine.reflection_memory import ReflectionMemory

    monkeypatch.setattr(reflection_engine, "REFLECTION_PATH", tmp_path / "reflection_events.json")
    monkeypatch.setattr(adaptive_memory, "MEMORY_PATH", tmp_path / "adaptive_memory.json")
    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")

    result = reflection_engine.reflect_after_turn(
        "open app",
        {},
        {"tool": "open_app", "success": False, "message": "verification failed"},
        "I could not verify that.",
    )
    assert result["stored"] >= 1
    assert ReflectionMemory.count() == 1
    assert ReflectionMemory.recall_similar("open_app verification failed", top_k=1)
