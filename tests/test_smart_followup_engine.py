import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_copy_it_routes_to_latest_output_action():
    from engine.smart_followup_engine import resolve_followup

    result = resolve_followup("copy it", {"latest_output": {"available": True}})
    assert result["route"] == "output"
    assert result["intent"] == "copy_latest_output"
    assert result["should_call_tool"] is False


def test_copy_it_uses_latest_output(monkeypatch):
    import engine.output_actions as output_actions
    from engine.smart_followup_engine import execute_output_action, resolve_followup

    monkeypatch.setattr(output_actions, "_latest_output", {})
    output_actions.set_latest_output("latest answer", title="Latest", content_type="text")

    copied = []
    monkeypatch.setitem(sys.modules, "pyperclip", SimpleNamespace(copy=lambda text: copied.append(text)))

    decision = resolve_followup("copy it", {"latest_output": {"available": True}})
    result = execute_output_action(decision["intent"], decision.get("slots") or {})

    assert result["ok"] is True
    assert copied == ["latest answer"]
