import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_what_do_you_remember_safe_summary(tmp_path, monkeypatch):
    import engine.adaptive_memory as adaptive
    import engine.memory_store as store
    monkeypatch.setattr(adaptive, "MEMORY_PATH", tmp_path / "adaptive.json")
    store.parse_memory_command("remember that I prefer short answers")
    summary = store.parse_memory_command("what do you remember?")
    assert "preferences" in summary.lower()
    assert "short" in summary.lower()


def test_forget_matching_memory_command(tmp_path, monkeypatch):
    import engine.adaptive_memory as adaptive
    import engine.memory_store as store
    monkeypatch.setattr(adaptive, "MEMORY_PATH", tmp_path / "adaptive.json")
    store.parse_memory_command("remember that I prefer markdown")
    assert store.parse_memory_command("forget markdown") == "Forgot it."


# --- compound "remember X then do Y" ---------------------------------------

def test_trailing_command_is_not_stored_as_part_of_the_fact():
    """Regression: the greedy prefix match stored the second command too.

    "remember that my deadline is friday, then tell me what you remember"
    stored the entire tail as one fact.
    """
    from engine.memory_store import _split_trailing_command

    clause, trailing = _split_trailing_command(
        "my project deadline is friday, then tell me what you remember about deadlines")
    assert clause == "my project deadline is friday"
    assert trailing.startswith(", then tell")


def test_plain_facts_containing_and_are_not_split():
    """"buy milk and eggs" is one fact, not a compound command."""
    from engine.memory_store import _split_trailing_command

    for fact in ["I need to buy milk and eggs",
                 "my deadline is friday",
                 "my manager is Sam and my skip is Alex"]:
        assert _split_trailing_command(fact) == (fact, "")


def test_compound_stores_the_fact_and_defers_the_second_command(tmp_path, monkeypatch):
    """The fact must be stored AND the second clause must reach the router."""
    import engine.adaptive_memory as adaptive
    import engine.memory_store as store
    monkeypatch.setattr(adaptive, "MEMORY_PATH", tmp_path / "adaptive.json")

    result = store.parse_memory_command(
        "remember that my project deadline is friday, then tell me what you remember about deadlines")
    assert result is None, "must fall through so the recall half actually runs"

    summary = store.parse_memory_command("what do you remember?")
    assert "friday" in summary.lower(), "the fact still has to be stored"
    assert "tell me what you remember" not in summary.lower(), "second command leaked into the fact"


def test_simple_remember_still_confirms(tmp_path, monkeypatch):
    import engine.adaptive_memory as adaptive
    import engine.memory_store as store
    monkeypatch.setattr(adaptive, "MEMORY_PATH", tmp_path / "adaptive.json")

    assert store.parse_memory_command("remember that my deadline is friday") is not None
