"""Privacy-aware screen capture for NEXI vision."""
from datetime import datetime
import io
import os


def _env_int(key, default):
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


class ScreenshotService:
    def __init__(self):
        # Default OFF: the generic capture() path reports unavailable unless explicitly
        # enabled, so nothing grabs the screen without an intentional caller. The OWNER vision
        # path (ScreenObserver.observe_screen) calls capture_real() directly to get real
        # pixels when Devendra asks NEXI to look — that is the intentional caller.
        # NEXI_VISION_REAL_CAPTURE=1 flips the default for callers that use capture().
        self._real_capture_enabled = os.getenv("NEXI_VISION_REAL_CAPTURE", "0") != "0"
        self._capture_count = 0

    def capture(self):
        self._capture_count += 1
        if self._real_capture_enabled:
            return self._capture_real()
        return self._unavailable("Real screen capture is disabled")

    def capture_real(self):
        """Always attempt a real grab and report failure truthfully."""
        self._capture_count += 1
        return self._capture_real()

    def _capture_real(self):
        try:
            from PIL import ImageGrab, Image
        except Exception as exc:
            print(f"[VISION] capture_backend_missing reason={type(exc).__name__}", flush=True)
            return self._unavailable(exc)
        method = "pil_imagegrab"
        try:
            img = ImageGrab.grab()
        except Exception as exc:
            print(f"[VISION] capture_failed reason={type(exc).__name__}", flush=True)
            try:
                import pyautogui
                img = pyautogui.screenshot()
                method = "pyautogui"
            except Exception as fallback_exc:
                print(f"[VISION] capture_fallback_failed reason={type(fallback_exc).__name__}", flush=True)
                return self._unavailable(fallback_exc)

        w, h = img.size
        max_w = _env_int("NEXI_VISION_MAX_WIDTH", 1280)
        quality = _env_int("NEXI_VISION_JPEG_QUALITY", 70)
        scale = min(1.0, max_w / float(w)) if w else 1.0
        if scale < 1.0:
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        return {
            "ok": True,
            "captured_at": datetime.now().isoformat(),
            "method": method,
            "width": w,
            "height": h,
            "scaled_size": list(img.size),
            "format": "jpeg",
            "image_bytes": data,
            "mime": "image/jpeg",
            "size_kb": round(len(data) / 1024, 1),
            "visible_text": self._active_window_text(),
            "error": None,
        }

    @staticmethod
    def _active_window_text():
        try:
            import win32gui
            return win32gui.GetWindowText(win32gui.GetForegroundWindow()) or ""
        except Exception:
            return ""

    @staticmethod
    def _unavailable(error):
        return {
            "ok": False,
            "captured_at": datetime.now().isoformat(),
            "method": "unavailable",
            "width": 0,
            "height": 0,
            "visible_text": "",
            "format": "unavailable",
            "image_bytes": b"",
            "mime": "",
            "error": str(error) or type(error).__name__,
        }

    def capture_mock(self, visible_text=""):
        return {
            "ok": True,
            "captured_at": datetime.now().isoformat(),
            "method": "mock",
            "width": 1920,
            "height": 1080,
            "visible_text": visible_text,
            "format": "mock",
            "image_bytes": b"",
            "mime": "image/jpeg",
            "error": None,
        }

    @property
    def capture_count(self):
        return self._capture_count

    def enable_real_capture(self):
        self._real_capture_enabled = True

    def disable_real_capture(self):
        self._real_capture_enabled = False
