"""Real screen vision: capture -> multimodal analysis -> privacy-guarded result.

Vision was a stub: ScreenshotService.capture() returned a hardcoded mock and
VisionAnalyzer keyword-matched on always-empty text, so NEXI could not actually see
the screen. Now capture grabs the real desktop and analysis asks Gemini's multimodal
brain what's on it.

The live network call cannot run in CI / the tool sandbox (its HTTPS proxy drops
image uploads — verified: text POST to the same endpoint is 200, any inline_data body
fails at the TLS layer). So these mock the transport and assert MY code is correct:
the request body matches Gemini's inline_data spec, the pipeline returns the model's
answer, secrets are redacted, and every failure degrades to the keyword fallback
instead of crashing the voice turn.
"""
import base64
import io
import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


# ---- capture -------------------------------------------------------------------

def test_capture_downscales_and_returns_real_bytes(monkeypatch):
    """A full-res PNG is ~2x the bytes and vision is billed per image token, so
    capture must downscale. Uses a fake grab so it runs headless."""
    PIL = pytest.importorskip("PIL")
    from PIL import Image
    from vision.screenshot_service import ScreenshotService

    fake = Image.new("RGB", (1920, 1080), (30, 40, 50))
    monkeypatch.setattr("PIL.ImageGrab.grab", lambda *a, **k: fake)
    monkeypatch.setenv("NEXI_VISION_MAX_WIDTH", "1280")

    shot = ScreenshotService().capture_real()   # explicit real-capture entry point
    assert shot["method"] == "pil_imagegrab"
    assert shot["scaled_size"][0] == 1280, "did not downscale to max width"
    assert shot["mime"] == "image/jpeg"
    assert len(shot["image_bytes"]) > 500, "no real image bytes"
    # the bytes must be a valid JPEG the model can decode
    Image.open(io.BytesIO(shot["image_bytes"])).verify()


def test_capture_falls_back_to_installed_pyautogui_when_imagegrab_fails(monkeypatch):
    """Use the already-installed capture backend before declaring vision unavailable."""
    from vision.screenshot_service import ScreenshotService
    from PIL import Image

    def _boom(*a, **k):
        raise OSError("no display")

    monkeypatch.setattr("PIL.ImageGrab.grab", _boom)
    monkeypatch.setattr("pyautogui.screenshot", lambda: Image.new("RGB", (640, 480), "white"))
    shot = ScreenshotService().capture_real()
    assert shot["ok"] is True
    assert shot["method"] == "pyautogui"
    assert shot["image_bytes"]


def test_capture_failure_is_truthfully_unavailable_not_mock(monkeypatch):
    from vision.screenshot_service import ScreenshotService

    monkeypatch.setattr("PIL.ImageGrab.grab", lambda *a, **k: (_ for _ in ()).throw(OSError("no display")))
    monkeypatch.setattr("pyautogui.screenshot", lambda: (_ for _ in ()).throw(OSError("capture failed")))
    shot = ScreenshotService().capture_real()
    assert shot["ok"] is False
    assert shot["method"] == "unavailable"
    assert shot["image_bytes"] == b""
    assert shot["error"]


def test_real_capture_includes_available_local_window_text(monkeypatch):
    from PIL import Image
    from vision.screenshot_service import ScreenshotService

    monkeypatch.setattr("PIL.ImageGrab.grab", lambda *a, **k: Image.new("RGB", (640, 480), "white"))
    monkeypatch.setattr("win32gui.GetForegroundWindow", lambda: 42)
    monkeypatch.setattr("win32gui.GetWindowText", lambda _hwnd: "Visual Studio Code - ImportError")
    shot = ScreenshotService().capture_real()
    assert "Visual Studio Code" in shot["visible_text"]


def test_capture_respects_the_disable_flag(monkeypatch):
    from vision.screenshot_service import ScreenshotService
    monkeypatch.setenv("NEXI_VISION_REAL_CAPTURE", "0")
    shot = ScreenshotService().capture()
    assert shot["ok"] is False
    assert shot["method"] == "unavailable"
    assert shot["image_bytes"] == b""


# ---- request construction ------------------------------------------------------

def test_vision_request_body_matches_gemini_inline_data_spec(monkeypatch):
    """The whole feature rests on a correctly-shaped multimodal request. Capture the
    exact JSON requests.post would send and assert it against Gemini's spec."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
    from engine import gemini_brain

    captured = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": "a code editor"}]}}]}

    def _fake_post(url, params=None, json=None, timeout=None, headers=None):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["json"] = json
        return _Resp()

    monkeypatch.setattr(gemini_brain.requests, "post", _fake_post)

    img = b"\xff\xd8\xff\xe0fakejpeg\xff\xd9"
    out = gemini_brain.ask_gemini_vision("what is this", img, mime="image/jpeg")
    assert out == "a code editor"

    parts = captured["json"]["contents"][0]["parts"]
    text_parts = [p for p in parts if "text" in p]
    img_parts = [p for p in parts if "inline_data" in p]
    assert text_parts and img_parts, f"missing text or image part: {parts}"
    inline = img_parts[0]["inline_data"]
    assert inline["mime_type"] == "image/jpeg"
    # data must be valid base64 that decodes back to the exact bytes we sent
    assert base64.b64decode(inline["data"]) == img
    assert ":generateContent" in captured["url"]
    # key must ride in the header, never the URL/query (URLs get logged)
    assert captured["headers"]["x-goog-api-key"] == "test-key-123"
    assert not captured.get("params"), "API key must not be in the URL query string"


def test_vision_raises_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    from engine import gemini_brain
    with pytest.raises(gemini_brain.GeminiConfigurationError):
        gemini_brain.ask_gemini_vision("x", b"bytes")


# ---- full analyze() pipeline ---------------------------------------------------

def test_analyze_uses_the_model_when_an_image_is_present(monkeypatch):
    from vision.vision_analyzer import VisionAnalyzer

    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision",
                        lambda *a, **k: "VS Code is open showing a Python file with an ImportError.")

    res = VisionAnalyzer().analyze({"image_bytes": b"jpegbytes", "mime": "image/jpeg"})
    assert res["source"] == "gemini_vision"
    assert "VS Code" in res["summary"]
    assert res["detected_context"] == "code"       # classified from the model's OWN words


def test_analyze_redacts_secrets_the_model_reads_aloud(monkeypatch):
    """The model's description is untrusted fetched text; a key it transcribes must be
    redacted before it is returned or spoken."""
    from vision.vision_analyzer import VisionAnalyzer

    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)
    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision",
                        lambda *a, **k: "The terminal shows password=hunter2 in plain text.")

    res = VisionAnalyzer().analyze({"image_bytes": b"x", "mime": "image/jpeg"})
    assert "hunter2" not in res["summary"], "secret leaked through vision"
    assert res["sensitive_content_detected"] is True


def test_analyze_falls_back_when_the_model_is_unreachable(monkeypatch):
    """Sandbox / offline / API down -> keyword fallback, never an exception."""
    from vision.vision_analyzer import VisionAnalyzer

    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: True)

    def _boom(*a, **k):
        raise RuntimeError("ConnectionError")

    monkeypatch.setattr("engine.gemini_brain.ask_gemini_vision", _boom)

    res = VisionAnalyzer().analyze({"image_bytes": b"x", "visible_text": "def main(): import os"})
    assert res["source"] == "keyword_fallback"
    assert res["detected_context"] == "code"       # still useful from visible_text


def test_analyze_is_truthfully_unavailable_without_model_or_local_text(monkeypatch):
    from vision.vision_analyzer import VisionAnalyzer

    monkeypatch.setattr("engine.gemini_brain.is_gemini_configured", lambda: False)
    res = VisionAnalyzer().analyze({"image_bytes": b"x", "visible_text": "", "method": "pil_imagegrab"})
    assert res["ok"] is False
    assert res["source"] == "analysis_unavailable"


def test_analyze_without_an_image_uses_keywords(monkeypatch):
    from vision.vision_analyzer import VisionAnalyzer
    res = VisionAnalyzer().analyze({"visible_text": "https://www.example.com"})
    assert res["source"] == "keyword_fallback"
    assert res["detected_context"] == "browser"
