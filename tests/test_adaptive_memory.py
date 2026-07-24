import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_adaptive_memory_stores_preference(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    assert memory.learn_from_user_text("from now on, keep your answers short and direct") is True
    context = memory.build_memory_context()
    assert "preferences" in context
    assert "short and direct" in context


def test_remember_explicit_preference(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    item = memory.remember("User prefers short direct answers.", "preferences")
    assert item["type"] == "preferences"
    assert item["safe"] is True


def test_extract_from_now_on_preference(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    items = memory.maybe_extract_memory("from now on, keep your answers short and direct")
    assert items
    assert "short and direct" in items[0]["text"].lower()


def test_adaptive_memory_stores_correction(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    assert memory.learn_from_user_text("actually, my project folder is E drive") is True
    assert "corrections" in memory.build_memory_context()


def test_extract_correction(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    items = memory.maybe_extract_memory("no, when I say YouTube open youtube.com")
    assert items[0]["type"] == "corrections"


def test_store_tool_failure_summary(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    memory.record_tool_failure("tts", "failed when answering long essay")
    assert memory.recall("long essay", limit=1)[0]["type"] == "tool_failures"


def test_recall_relevant_memory(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    memory.remember("User prefers markdown files.", "file_preferences")
    assert memory.recall("markdown", limit=1)[0]["type"] == "file_preferences"


def test_forget_matching_memory(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    memory.remember("User prefers short answers.", "preferences")
    assert memory.forget("short")["removed"] == 1


def test_memory_stores_output_preference(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    items = memory.maybe_extract_memory("always open long answers in the box")
    assert items[0]["type"] == "output_preferences"


def test_adaptive_memory_skips_secret(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    assert memory.learn_from_user_text("remember my API key is secret") is False
    assert memory.build_memory_context() == ""


def test_memory_context_is_compact(tmp_path, monkeypatch):
    import engine.adaptive_memory as memory
    monkeypatch.setattr(memory, "MEMORY_PATH", tmp_path / "adaptive.json")
    for idx in range(20):
        memory.store_memory("preferences", f"I prefer setting {idx}")
    context = memory.build_memory_context(limit=4)
    assert len(context.splitlines()) <= 5
