from datetime import datetime


class ScreenshotService:
    def __init__(self):
        self._real_capture_enabled = False
        self._capture_count = 0

    def capture(self):
        if self._real_capture_enabled:
            pass
        return self.capture_mock()

    def capture_mock(self, visible_text=""):
        self._capture_count += 1
        return {
            "captured_at": datetime.now().isoformat(),
            "method": "mock",
            "width": 1920,
            "height": 1080,
            "visible_text": visible_text,
            "format": "mock",
        }

    @property
    def capture_count(self):
        return self._capture_count

    def enable_real_capture(self):
        self._real_capture_enabled = True

    def disable_real_capture(self):
        self._real_capture_enabled = False
