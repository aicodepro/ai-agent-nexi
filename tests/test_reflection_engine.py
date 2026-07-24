import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_reflection_stores_tool_failure(monkeypatch, tmp_path):
    import engine.reflection_engine as reflection
    import engine.adaptive_memory as adaptive_memory
    from engine.reflection_memory import ReflectionMemory
    monkeypatch.setattr(reflection, "REFLECTION_PATH", tmp_path / "reflection.json")
    monkeypatch.setattr(adaptive_memory, "MEMORY_PATH", tmp_path / "adaptive_memory.json")
    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    result = reflection.reflect_after_turn("open app", {}, {"tool": "open_app", "success": False, "message": "failed"}, "I could not verify that.")
    assert result["stored"] >= 1
    assert any(event["type"] == "failed_tool_route" for event in result["events"])


def test_reflection_stores_user_correction(monkeypatch, tmp_path):
    import engine.reflection_engine as reflection
    import engine.user_model as user_model
    from engine.reflection_memory import ReflectionMemory
    monkeypatch.setattr(reflection, "REFLECTION_PATH", tmp_path / "reflection.json")
    monkeypatch.setattr(user_model, "USER_MODEL_PATH", tmp_path / "user_model.json")
    monkeypatch.setattr(ReflectionMemory, "PATH", tmp_path / "reflection_memory.json")
    result = reflection.reflect_after_turn("that's wrong, next time open youtube", {}, {}, "Understood.")
    assert any(event["type"] == "user_correction" for event in result["events"])


def test_reflection_write_is_atomic(monkeypatch, tmp_path):
    import os
    import engine.reflection_engine as reflection

    target = tmp_path / "reflection.json"
    monkeypatch.setattr(reflection, "REFLECTION_PATH", target)
    real_replace = os.replace
    calls = []

    def replace(source, destination):
        calls.append((source, destination))
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    reflection._save([])

    assert calls
    assert target.read_text(encoding="utf-8")
