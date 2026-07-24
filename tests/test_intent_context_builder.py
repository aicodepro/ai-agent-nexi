import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_intent_context_builder_preserves_existing_keys():
    from engine.intent_context_builder import build_intent_context

    context = build_intent_context("hello", source="ui")
    for key in {
        "source",
        "text_preview",
        "pending_clarification",
        "pending_followup",
        "active_workflow",
        "active_training",
        "latest_output",
        "recent_turns",
        "memory_context",
    }:
        assert key in context


def test_intent_context_builder_includes_compact_memory_layers(tmp_path, monkeypatch):
    from engine.intent_context_builder import build_intent_context
    import engine.memory.episodic_memory as episodic_module
    import engine.memory.semantic_memory as semantic_module
    import engine.memory.session_memory as session_module
    from engine.memory.episodic_memory import Episode, EpisodicMemory
    from engine.memory.semantic_memory import SemanticFact, SemanticMemory
    from engine.reflection_memory import ReflectionMemory

    session_module.get_session_memory().clear()
    session_module.get_session_memory().add_user_turn("create folder invoices", source="test")
    episodic = EpisodicMemory(tmp_path / "episodic.json")
    episodic.store(Episode(user_input="create folder invoices", intent="create_folder", route="workflow"))
    semantic = SemanticMemory(tmp_path / "semantic.json")
    semantic.upsert(SemanticFact(subject="user", predicate="prefers", object="markdown summaries", category="preference"))
    monkeypatch.setattr(episodic_module, "_episodic_memory", episodic)
    monkeypatch.setattr(semantic_module, "_semantic_memory", semantic)
    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    ReflectionMemory.store_lesson("create_folder verification failed", "Folder creation needs verification", "Check the target path")

    context = build_intent_context("create folder invoices", source="hotword")
    memory = context["memory_context"]
    assert memory["available"] is True
    assert "create folder invoices" in memory["session"]
    assert memory["episodic"][0]["intent"] == "create_folder"
    assert "markdown summaries" in memory["semantic"]
    assert "Check the target path" in memory["reflection"]
    assert len(memory["session"]) <= 900
    session_module.get_session_memory().clear()
