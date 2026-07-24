import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_empty_asr_status_maps_to_sleep(monkeypatch):
    import engine.runtime_bridge as rb
    seen = []
    monkeypatch.setattr(rb, "_append_log", lambda level, message: True)
    monkeypatch.setattr(rb, "_set_ui_state", lambda state, **kw: seen.append((state, kw)) or True)
    rb._handle_status_event({"type": "status", "status": "asr_result", "source": "hotword", "text": ""})
    assert seen[-1][0] == "sleep"
