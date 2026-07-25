"""The OWNER path does real capture + real cloud analysis.

request_trusted_read_only is the conservative real-capture, local-only preview. But
"NEXI, look at my screen" from the machine owner must actually SEE the screen — real
grab, multimodal description, secrets redacted. This pins that observe_screen wires
capture -> analyze(allow_cloud=True) -> privacy guard, with the live model mocked
(the tool sandbox blocks image uploads; see test_vision_pipeline).
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture
def observer(monkeypatch):
    from vision.screen_observer import ScreenObserver
    obs = ScreenObserver()
    # real-looking capture without touching the display. observe_screen uses
    # capture_real() (the explicit owner "look now" path), so patch that.
    monkeypatch.setattr(obs._screenshot_service, "capture_real", lambda: {
        "method": "pil_imagegrab", "image_bytes": b"\xff\xd8jpeg\xff\xd9",
        "mime": "image/jpeg", "visible_text": "", "width": 1920, "height": 1080,
    })
    return obs


def test_owner_vision_uses_the_real_model(observer, monkeypatch):
    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision",
                        lambda *a, **k: "A browser is open on the NEXI docs page.")

    res = observer.observe_screen("what's on my screen", allow_cloud=True)
    assert res["ok"]
    assert "browser" in res["summary"].lower()
    obs = res["data"]["observation"]
    assert obs["screenshot_method"] == "pil_imagegrab"   # REAL capture, not mock
    assert obs["source"] == "gemini_vision"              # REAL analysis


def test_owner_vision_redacts_secrets(observer, monkeypatch):
    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision",
                        lambda *a, **k: "Your .env shows GEMINI_API_KEY=AIzaSyReal12345 on screen.")

    res = observer.observe_screen("look", allow_cloud=True)
    assert "AIzaSyReal12345" not in res["summary"], "vision leaked a real-shaped key"
    assert res["data"]["observation"]["sensitive_content_detected"] is True


def test_owner_vision_never_stores_the_screenshot(observer, monkeypatch):
    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision", lambda *a, **k: "desktop")
    res = observer.observe_screen("look", allow_cloud=True)
    assert res["data"]["observation"]["store_screenshot"] is False


def test_owner_vision_degrades_when_model_unreachable(observer, monkeypatch):
    """Sandbox / offline without local text is reported unavailable, not invented."""
    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("ConnectionError")))
    res = observer.observe_screen("look", allow_cloud=True)
    assert res["ok"] is False                               # truthful, did not crash
    assert res["data"]["observation"]["source"] == "analysis_unavailable"


def test_owner_vision_reports_real_capture_failure(observer, monkeypatch):
    monkeypatch.setattr(observer._screenshot_service, "capture_real", lambda: {
        "ok": False, "method": "unavailable", "image_bytes": b"",
        "visible_text": "", "error": "no display",
    })
    res = observer.observe_screen("look", allow_cloud=False)
    assert res["ok"] is False
    assert res["data"]["observation"]["screenshot_method"] == "unavailable"
    assert "unavailable" in res["summary"].lower()


def test_owner_vision_does_not_retain_screenshot_bytes(observer, monkeypatch):
    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision", lambda *a, **k: "desktop")
    res = observer.observe_screen("look", allow_cloud=True)
    stored = observer._requests[res["request_id"]]["screenshot_data"]
    assert "image_bytes" not in stored
    assert "visible_text" not in stored


def test_owner_vision_status_is_observable(observer, monkeypatch):
    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision", lambda *a, **k: "desktop")
    result = observer.observe_screen("look", allow_cloud=True)
    status = observer.get_observation_status(result["request_id"])
    assert status["ok"] is True
    assert status["status"] == "completed"
    assert status["permission_granted"] is True


def test_emergency_stop_blocks_owner_vision(observer, monkeypatch):
    monkeypatch.setattr("engine.control.safety.EmergencyStop.is_engaged", lambda: True)
    res = observer.observe_screen("look")
    assert res["ok"] is False
    assert "Emergency stop" in res["error"]
