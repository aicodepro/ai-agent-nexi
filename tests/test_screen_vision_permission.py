import unittest
import importlib

from vision.screen_observer import ScreenObserver
from vision.screenshot_service import ScreenshotService
from vision.vision_analyzer import VisionAnalyzer
from vision.privacy_guard import PrivacyGuard
from vision.screen_context import detect_screen_command, get_context_label, create_safe_summary
from engine.control.safety import EmergencyStop


def _observed_text(observer, request_id):
    req = observer._requests.get(request_id)
    if req and req.get("screenshot_data"):
        return req["screenshot_data"].get("visible_text", "")
    return ""


class TestScreenObservationRequest(unittest.TestCase):

    def setUp(self):
        EmergencyStop.clear()
        self.observer = ScreenObserver()
        self.observer._screenshot_service._capture_real = lambda: {
            "ok": True, "method": "test_capture", "image_bytes": b"test",
            "mime": "image/jpeg", "visible_text": "test application window",
            "error": None,
        }

    def test_request_requires_permission(self):
        result = self.observer.request_observation("User asked to look at screen")
        self.assertTrue(result["requires_permission"])
        self.assertFalse(result["permission_granted"])

    def test_no_screenshot_captured_before_approval(self):
        self.observer.request_observation("Check this error")
        self.assertEqual(self.observer.screenshot_service.capture_count, 0)

    def test_approval_uses_real_screenshot_capture(self):
        self.observer._screenshot_service._capture_real = lambda: {
            "ok": True, "method": "pil_imagegrab", "image_bytes": b"jpeg",
            "mime": "image/jpeg", "visible_text": "Notepad window",
        }
        req = self.observer.request_observation("Look at screen")
        result = self.observer.approve_observation(req["request_id"], "yes")
        self.assertTrue(result["ok"])
        self.assertEqual(self.observer.screenshot_service.capture_count, 1)
        self.assertEqual(req["screenshot_data"]["method"], "pil_imagegrab")

    def test_cancel_prevents_analysis(self):
        req = self.observer.request_observation("Screen dekho")
        cancel = self.observer.cancel_observation(req["request_id"])
        self.assertTrue(cancel["ok"])
        analysis = self.observer.analyze_observation(req["request_id"])
        self.assertFalse(analysis["ok"])
        self.assertIn("cancelled", analysis["error"])

    def test_cloud_analysis_false_by_default(self):
        req = self.observer.request_observation("Look")
        self.assertFalse(req["allow_cloud_analysis"])

    def test_store_screenshot_false_by_default(self):
        req = self.observer.request_observation("Look")
        self.assertFalse(req["store_screenshot"])

    def test_sensitive_content_flagged_by_guard(self):
        result = PrivacyGuard.analyze_text("my password is hello123")
        self.assertTrue(result["sensitive_content_detected"])
        self.assertEqual(result["reason"], "Sensitive content detected: password")

    def test_password_text_detected(self):
        result = PrivacyGuard.analyze_text("My password is secret123")
        self.assertTrue(result["sensitive_content_detected"])
        self.assertIn("REDACTED", result["redacted_text"])

    def test_api_key_text_detected(self):
        result = PrivacyGuard.analyze_text("API_KEY=sk-abc123")
        self.assertTrue(result["sensitive_content_detected"])
        self.assertIn("api_key", result["reason"])

    def test_token_cookie_text_detected(self):
        result_token = PrivacyGuard.analyze_text("my auth token is xyz")
        self.assertTrue(result_token["sensitive_content_detected"])
        result_cookie = PrivacyGuard.analyze_text("session cookie=abc")
        self.assertTrue(result_cookie["sensitive_content_detected"])

    def test_analyzer_returns_code_context(self):
        payload = {"visible_text": "def hello(): print('hello')", "method": "pil_imagegrab"}
        analyzer = VisionAnalyzer()
        result = analyzer.analyze(payload)
        self.assertEqual(result["detected_context"], "code")

    def test_analyzer_returns_terminal_context(self):
        payload = {"visible_text": "$ npm install - Error: module not found", "method": "pil_imagegrab"}
        analyzer = VisionAnalyzer()
        result = analyzer.analyze(payload)
        self.assertEqual(result["detected_context"], "terminal")

    def test_analyzer_returns_browser_context(self):
        payload = {"visible_text": "http://localhost:3000 browser tab", "method": "pil_imagegrab"}
        analyzer = VisionAnalyzer()
        result = analyzer.analyze(payload)
        self.assertEqual(result["detected_context"], "browser")

    def test_analyzer_returns_app_context(self):
        payload = {"visible_text": "running application window", "method": "pil_imagegrab"}
        analyzer = VisionAnalyzer()
        result = analyzer.analyze(payload)
        self.assertEqual(result["detected_context"], "app")

    def test_analyzer_returns_unknown_context(self):
        payload = {"visible_text": "some random text with no keywords", "method": "pil_imagegrab"}
        analyzer = VisionAnalyzer()
        result = analyzer.analyze(payload)
        self.assertEqual(result["detected_context"], "unknown")

    def test_trusted_read_only_uses_real_local_capture(self):
        self.observer._screenshot_service.capture_real = lambda: {
            "ok": True, "method": "pil_imagegrab", "image_bytes": b"jpeg",
            "mime": "image/jpeg", "visible_text": "Visual Studio Code window",
        }
        result = self.observer.request_trusted_read_only("screen dekho")
        obs = result["data"]["observation"]
        self.assertTrue(result["ok"])
        self.assertEqual(obs["screenshot_method"], "pil_imagegrab")
        self.assertFalse(obs["allow_cloud_analysis"])
        self.assertFalse(obs["store_screenshot"])

    def test_trusted_read_only_capture_failure_is_truthful(self):
        self.observer._screenshot_service.capture_real = lambda: {
            "ok": False, "method": "unavailable", "image_bytes": b"",
            "visible_text": "", "error": "capture failed",
        }
        result = self.observer.request_trusted_read_only("screen dekho")
        self.assertFalse(result["ok"])
        self.assertEqual(result["data"]["observation"]["status"], "unavailable")
        self.assertEqual(result["data"]["observation"]["screenshot_method"], "unavailable")
        self.assertIn("unavailable", result["summary"].lower())

    def test_trusted_read_only_does_not_retain_pixels_or_raw_text(self):
        self.observer._screenshot_service.capture_real = lambda: {
            "ok": True, "method": "pil_imagegrab", "image_bytes": b"private pixels",
            "mime": "image/jpeg", "visible_text": "private screen dump",
        }
        result = self.observer.request_trusted_read_only("screen dekho")
        stored = self.observer._requests[result["request_id"]]["screenshot_data"]
        self.assertNotIn("image_bytes", stored)
        self.assertNotIn("visible_text", stored)

    def test_analysis_requires_confirmation_before_action(self):
        req = self.observer.request_observation("Look at this screen")
        self.observer.approve_observation(req["request_id"], "yes")
        analysis = self.observer.analyze_observation(req["request_id"])
        self.assertTrue(analysis["requires_confirmation_before_action"])

    def test_hidden_screenshot_impossible_through_public_api(self):
        self.observer.request_observation("Check screen")
        self.assertEqual(self.observer.screenshot_service.capture_count, 0)

    def test_screenshot_not_stored_by_default(self):
        req = self.observer.request_observation("Look at screen")
        self.observer.approve_observation(req["request_id"], "yes")
        self.assertFalse(req["store_screenshot"])

    def test_invalid_request_id_returns_safe_error(self):
        analysis = self.observer.analyze_observation("nonexistent_id")
        self.assertFalse(analysis["ok"])
        self.assertEqual(analysis["error"], "Invalid request_id")

    def test_emergency_stop_blocks_observation_request(self):
        EmergencyStop.engage("Test emergency")
        result = self.observer.request_observation("Screen dekho")
        self.assertFalse(result["ok"])
        self.assertIn("emergency", result["error"].lower())
        EmergencyStop.clear()

    def test_emergency_stop_blocks_approval(self):
        req = self.observer.request_observation("Look")
        EmergencyStop.engage("stop")
        result = self.observer.approve_observation(req["request_id"], "yes")
        self.assertFalse(result["ok"])
        self.assertIn("emergency", result["error"].lower())
        EmergencyStop.clear()

    def test_approve_with_no_response_denied(self):
        req = self.observer.request_observation("Look")
        result = self.observer.approve_observation(req["request_id"], "")
        self.assertFalse(result["ok"])
        self.assertIn("not granted", result["error"].lower())

    def test_approve_with_no_negative_response_denied(self):
        req = self.observer.request_observation("Look")
        result = self.observer.approve_observation(req["request_id"], "no")
        self.assertFalse(result["ok"])
        self.assertIn("not granted", result["error"].lower())

    def test_analyzer_deterministic_results(self):
        payload = {"visible_text": "def foo(): pass", "method": "pil_imagegrab"}
        a1 = VisionAnalyzer()
        a2 = VisionAnalyzer()
        r1 = a1.analyze(payload)
        r2 = a2.analyze(payload)
        self.assertEqual(r1["detected_context"], r2["detected_context"])
        self.assertEqual(r1["summary"], r2["summary"])

    def test_detect_screen_command(self):
        self.assertTrue(detect_screen_command("screen dekho"))
        self.assertTrue(detect_screen_command("look at this screen"))
        self.assertTrue(detect_screen_command("kya error hai screen pe"))
        self.assertTrue(detect_screen_command("check this terminal error"))
        self.assertFalse(detect_screen_command(""))
        self.assertFalse(detect_screen_command("open chrome"))

    def test_get_context_label(self):
        self.assertEqual(get_context_label("code"), "Code Editor")
        self.assertEqual(get_context_label("terminal"), "Terminal / Command Prompt")
        self.assertEqual(get_context_label("unknown"), "Unknown Content")

    def test_create_safe_summary(self):
        analysis = {
            "ok": True,
            "summary": "The screen shows code content.",
            "detected_context": "code",
            "sensitive_content_detected": False,
        }
        summary = create_safe_summary(analysis)
        self.assertIn("code", summary.lower())
        self.assertNotIn("sensitive", summary.lower())

    def test_create_safe_summary_with_sensitive(self):
        analysis = {
            "ok": True,
            "summary": "The screen shows code content.",
            "detected_context": "code",
            "sensitive_content_detected": True,
        }
        summary = create_safe_summary(analysis)
        self.assertIn("sensitive", summary.lower())

    def test_privacy_guard_none_text(self):
        result = PrivacyGuard.analyze_text(None)
        self.assertFalse(result["sensitive_content_detected"])

    def test_privacy_guard_empty_text(self):
        result = PrivacyGuard.analyze_text("")
        self.assertFalse(result["sensitive_content_detected"])

    def test_privacy_guard_safe_text_unchanged(self):
        result = PrivacyGuard.analyze_text("hello world")
        self.assertFalse(result["sensitive_content_detected"])
        self.assertEqual(result["redacted_text"], "hello world")

    def test_privacy_guard_sk_pattern(self):
        result = PrivacyGuard.analyze_text("sk-mykey123")
        self.assertTrue(result["sensitive_content_detected"])

    def test_privacy_guard_bearer(self):
        result = PrivacyGuard.analyze_text("Bearer token123")
        self.assertTrue(result["sensitive_content_detected"])

    def test_privacy_guard_private_key(self):
        result = PrivacyGuard.analyze_text("private_key is secret")
        self.assertTrue(result["sensitive_content_detected"])

    def test_privacy_guard_check_payload_dict(self):
        payload = {"visible_text": "my password is test", "method": "pil_imagegrab"}
        result = PrivacyGuard.check_payload(payload)
        self.assertTrue(result["sensitive_content_detected"])

    def test_vision_module_importable(self):
        mod = importlib.import_module("vision")
        self.assertTrue(hasattr(mod, "ScreenObserver"))
        self.assertTrue(hasattr(mod, "ScreenshotService"))
        self.assertTrue(hasattr(mod, "VisionAnalyzer"))
        self.assertTrue(hasattr(mod, "PrivacyGuard"))
        self.assertTrue(hasattr(mod, "detect_screen_command"))

    def test_observer_reset(self):
        req = self.observer.request_observation("Test")
        self.observer.reset()
        analysis = self.observer.analyze_observation(req["request_id"])
        self.assertFalse(analysis["ok"])
        self.assertEqual(self.observer.screenshot_service.capture_count, 0)

    def test_get_observation_status(self):
        req = self.observer.request_observation("Check screen")
        status = self.observer.get_observation_status(req["request_id"])
        self.assertTrue(status["ok"])
        self.assertEqual(status["status"], "pending")

    def test_get_observation_status_invalid(self):
        status = self.observer.get_observation_status("bad_id")
        self.assertFalse(status["ok"])

    def test_observation_approve_then_get_status(self):
        req = self.observer.request_observation("Look")
        self.observer.approve_observation(req["request_id"], "yes")
        status = self.observer.get_observation_status(req["request_id"])
        self.assertEqual(status["status"], "approved")
        self.assertTrue(status["permission_granted"])

    def test_cancel_nonexistent_returns_error(self):
        result = self.observer.cancel_observation("ghost_id")
        self.assertFalse(result["ok"])

    def test_analysis_error_payload_none(self):
        analyzer = VisionAnalyzer()
        result = analyzer.analyze(None)
        self.assertFalse(result["ok"])
        self.assertIn("no image", result["error"].lower())

    def test_privacy_guard_check_payload_none(self):
        result = PrivacyGuard.check_payload(None)
        self.assertFalse(result["sensitive_content_detected"])

    def test_detect_screen_command_edge_cases(self):
        self.assertFalse(detect_screen_command(None))
        self.assertFalse(detect_screen_command("   "))

    def test_create_safe_summary_failed_analysis(self):
        result = create_safe_summary({"ok": False})
        self.assertEqual(result, "Could not analyze the screen.")

    def test_create_safe_summary_none(self):
        result = create_safe_summary(None)
        self.assertEqual(result, "Could not analyze the screen.")

    def test_vision_analyzer_analysis_count(self):
        analyzer = VisionAnalyzer()
        self.assertEqual(analyzer.analysis_count, 0)
        analyzer.analyze({"visible_text": "test", "method": "pil_imagegrab"})
        analyzer.analyze({"visible_text": "test2", "method": "pil_imagegrab"})
        self.assertEqual(analyzer.analysis_count, 2)


if __name__ == "__main__":
    unittest.main()
