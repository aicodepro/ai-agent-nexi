import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_semantic_memory_upsert_and_recall(tmp_path):
    from engine.memory.semantic_memory import SemanticFact, SemanticMemory

    memory = SemanticMemory(tmp_path / "semantic.json")
    fact_id = memory.upsert(SemanticFact(subject="user", predicate="prefers", object="short answers", category="preference"))
    assert fact_id.startswith("sem_")
    matches = memory.recall("short answer", limit=1)
    assert matches[0].object == "short answers"
    assert matches[0].category == "preference"


def test_semantic_memory_deduplicates_fact(tmp_path):
    from engine.memory.semantic_memory import SemanticFact, SemanticMemory

    memory = SemanticMemory(tmp_path / "semantic.json")
    first = memory.upsert(SemanticFact(subject="user", predicate="prefers", object="markdown", category="preferences", confidence=0.5))
    second = memory.upsert(SemanticFact(subject="user", predicate="prefers", object="markdown", category="preference", confidence=0.9, tags=["format"]))
    assert first == second
    assert memory.count() == 1
    fact = memory.recall("markdown", limit=1)[0]
    assert fact.confidence == 0.9
    assert "format" in fact.tags


def test_semantic_memory_extracts_preferences_and_identity():
    from engine.memory.semantic_memory import extract_semantic_facts

    facts = extract_semantic_facts("my name is Mark. from now on keep answers short")
    categories = {fact.category for fact in facts}
    assert "identity" in categories
    assert "preference" in categories


def test_semantic_memory_filters_secret_text(tmp_path):
    from engine.memory.semantic_memory import SemanticFact, SemanticMemory

    memory = SemanticMemory(tmp_path / "semantic.json")
    fact_id = memory.upsert(SemanticFact(subject="user", predicate="has", object="api key is abc123", category="fact"))
    assert fact_id == ""
    assert memory.count() == 0


def test_semantic_memory_context_is_compact(tmp_path):
    from engine.memory.semantic_memory import SemanticFact, SemanticMemory

    memory = SemanticMemory(tmp_path / "semantic.json")
    for idx in range(10):
        memory.upsert(SemanticFact(subject="user", predicate="prefers", object=f"setting {idx}", category="preference"))
    context = memory.build_context("setting", limit=3, max_chars=200)
    assert len(context.splitlines()) == 3
    assert "evidence" not in context.lower()


def test_semantic_memory_forget(tmp_path):
    from engine.memory.semantic_memory import SemanticFact, SemanticMemory

    memory = SemanticMemory(tmp_path / "semantic.json")
    memory.upsert(SemanticFact(subject="user", predicate="prefers", object="markdown", category="preference"))
    assert memory.forget("markdown") == 1
    assert memory.count() == 0
