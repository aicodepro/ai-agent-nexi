from src.orin.vision.screen_context import get_context_label


class VisionAnalyzer:

    _DEFAULT_SUMMARIES = {
        "code": "The screen shows code content.",
        "terminal": "The screen shows a terminal or command prompt.",
        "browser": "The screen shows a web browser.",
        "app": "The screen shows an application window.",
        "unknown": "I cannot identify what is on this screen. Try showing a code editor, terminal, browser, or an application window.",
    }

    def __init__(self):
        self._mock_mode = True
        self._analysis_count = 0

    def analyze(self, payload):
        self._analysis_count += 1
        if not payload:
            return self._result(ok=False, error="No image data provided")
        context = self._classify(payload)
        return self._result(context=context)

    def _classify(self, payload):
        visible_text = payload.get("visible_text", "") if isinstance(payload, dict) else ""
        lower = visible_text.lower()
        if "code" in lower or "def " in lower or "class " in lower or "import " in lower or "function " in lower:
            return "code"
        if "terminal" in lower or "$ " in lower or "> " in lower or "error" in lower or "command" in lower:
            return "terminal"
        if "browser" in lower or "http" in lower or "www." in lower or ".com" in lower:
            return "browser"
        if "app" in lower or "window" in lower or "application" in lower:
            return "app"
        return "unknown"

    def _result(self, ok=True, context="unknown", error=None):
        summary = self._DEFAULT_SUMMARIES.get(context, self._DEFAULT_SUMMARIES["unknown"])
        return {
            "ok": ok,
            "summary": summary,
            "detected_context": context,
            "context_label": get_context_label(context),
            "possible_issue": "",
            "suggested_next_step": "User should review the analysis and confirm next action",
            "sensitive_content_detected": False,
            "requires_confirmation_before_action": True,
            "error": error,
        }

    @property
    def analysis_count(self):
        return self._analysis_count
