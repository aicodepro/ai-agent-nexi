"""Analyze a screen capture.

When a capture carries real image bytes and Gemini is configured, the multimodal
brain describes the screen. Otherwise locally available window text is classified;
missing image analysis and missing local text are reported as unavailable.

The model's description is a fetched, untrusted string: it is run through PrivacyGuard
(redacts passwords/keys/cards) before it is returned, and it never carries tool
authority — callers get text, not actions.
"""
from vision.screen_context import get_context_label
from vision.privacy_guard import PrivacyGuard


class VisionAnalyzer:

    _DEFAULT_SUMMARIES = {
        "code": "The screen shows code content.",
        "terminal": "The screen shows a terminal or command prompt.",
        "browser": "The screen shows a web browser.",
        "app": "The screen shows an application window.",
        "unknown": "I cannot identify what is on this screen. Try showing a code editor, terminal, browser, or an application window.",
    }

    _VISION_PROMPT = (
        "You are NEXI's eyes. Look at this screenshot of the user's screen and reply in "
        "2-4 short sentences: what app/window is shown, what the user appears to be doing, "
        "and any obvious error or problem visible. Be concrete and specific. Do not read "
        "out passwords, API keys, tokens, or card numbers even if visible."
    )

    def __init__(self):
        self._analysis_count = 0

    def analyze(self, payload, allow_cloud=True):
        """allow_cloud gates the multimodal model. It sends the screenshot to Gemini's
        cloud, so callers that promised the user a LOCAL-only observation
        (ScreenObserver.request_trusted_read_only sets allow_cloud_analysis=False) MUST
        pass allow_cloud=False — otherwise the screen leaves the machine despite the
        promise. Local keyword classification always runs."""
        self._analysis_count += 1
        if not payload:
            return self._result(ok=False, error="No image data provided")
        if isinstance(payload, dict) and (
            payload.get("ok") is False or payload.get("method") == "unavailable"
        ):
            return self._result(
                ok=False,
                error=payload.get("error") or "Screen capture unavailable",
                source="capture_unavailable",
            )

        image_bytes = payload.get("image_bytes") if isinstance(payload, dict) else None
        if image_bytes and allow_cloud:
            real = self._analyze_with_model(payload, image_bytes)
            if real is not None:
                return real
            # model unavailable/failed -> fall through to the keyword classifier so the
            # caller still gets a usable, well-formed result instead of an exception.

        visible_text = payload.get("visible_text", "") if isinstance(payload, dict) else ""
        if visible_text.strip():
            return self._result(context=self._classify_text(visible_text))
        if image_bytes:
            return self._result(
                ok=False,
                error="No cloud vision model or useful local screen text is available",
                source="analysis_unavailable",
            )
        return self._result(context=self._classify(payload))

    def _analyze_with_model(self, payload, image_bytes):
        try:
            from engine.gemini_brain import ask_gemini_vision, is_gemini_configured
        except Exception:
            return None
        if not is_gemini_configured():
            return None
        mime = payload.get("mime", "image/jpeg") if isinstance(payload, dict) else "image/jpeg"
        try:
            description = ask_gemini_vision(self._VISION_PROMPT, image_bytes, mime=mime)
        except Exception as exc:
            print(f"[VISION] model_analysis_failed reason={type(exc).__name__}", flush=True)
            return None

        # The description is model-generated text about the screen — treat it as
        # untrusted and redact anything sensitive before it leaves this function.
        guard = PrivacyGuard.analyze_text(description)
        clean = guard["redacted_text"]
        context = self._classify_text(clean)
        return {
            "ok": True,
            "summary": clean,
            "detected_context": context,
            "context_label": get_context_label(context),
            "possible_issue": "",
            "suggested_next_step": "User should review the analysis and confirm next action",
            "sensitive_content_detected": guard["sensitive_content_detected"],
            "requires_confirmation_before_action": True,
            "source": "gemini_vision",
            "error": None,
        }

    def _classify(self, payload):
        visible_text = payload.get("visible_text", "") if isinstance(payload, dict) else ""
        return self._classify_text(visible_text)

    def _classify_text(self, text):
        lower = (text or "").lower()
        if "code" in lower or "def " in lower or "class " in lower or "import " in lower or "function " in lower:
            return "code"
        if "terminal" in lower or "$ " in lower or "> " in lower or "error" in lower or "command" in lower:
            return "terminal"
        if "browser" in lower or "http" in lower or "www." in lower or ".com" in lower:
            return "browser"
        if "app" in lower or "window" in lower or "application" in lower:
            return "app"
        return "unknown"

    def _result(self, ok=True, context="unknown", error=None, source="keyword_fallback"):
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
            "source": source,
            "error": error,
        }

    @property
    def analysis_count(self):
        return self._analysis_count
