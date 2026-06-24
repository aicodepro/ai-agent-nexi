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
