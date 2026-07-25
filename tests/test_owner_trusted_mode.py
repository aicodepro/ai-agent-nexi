import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import threading
from unittest import mock

from vision.screen_trust import ScreenTrust
from engine.control.permission_manager import PermissionManager
from engine.control.safety import EmergencyStop, SandboxPolicy, AuditLog
from engine.app.phase3_command_bridge import Phase3CommandBridge
from engine.app.runtime_context import reset_runtime


class TestOwnerTrustedModeDefault(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_all()
        EmergencyStop.clear()

    def test_owner_trusted_is_true_by_default(self):
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_owner_trusted_persists_after_reset_to_ask(self):
        ScreenTrust.reset_to_ask()
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_owner_trusted_can_be_disabled(self):
        ScreenTrust.set_owner_trusted(False)
        self.assertFalse(ScreenTrust.is_owner_trusted())

    def test_owner_trusted_can_be_re_enabled(self):
        ScreenTrust.set_owner_trusted(False)
        ScreenTrust.set_owner_trusted(True)
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_owner_trusted_overridden_by_emergency_stop(self):
        self.assertTrue(ScreenTrust.is_owner_trusted())
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_owner_trusted())
        EmergencyStop.clear()

    def test_owner_trusted_restored_after_emergency_clear(self):
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_owner_trusted())
        EmergencyStop.clear()
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_owner_trusted_independent_of_screen_mode(self):
        ScreenTrust.set_mode("ask_each_time")
        self.assertTrue(ScreenTrust.is_owner_trusted())
        ScreenTrust.set_mode("denied")
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_to_dict_includes_owner_trusted(self):
        d = ScreenTrust.to_dict()
        self.assertIn("owner_trusted", d)
        self.assertTrue(d["owner_trusted"])

    def test_to_dict_owner_trusted_false_when_emergency(self):
        EmergencyStop.engage(reason="test")
        d = ScreenTrust.to_dict()
        self.assertFalse(d["owner_trusted"])
        EmergencyStop.clear()

    def test_to_dict_owner_trusted_false_when_disabled(self):
        ScreenTrust.set_owner_trusted(False)
        d = ScreenTrust.to_dict()
        self.assertFalse(d["owner_trusted"])


class TestOwnerTrustedModeResetAll(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()

    def test_reset_all_restores_owner_trusted(self):
        ScreenTrust.set_owner_trusted(False)
        ScreenTrust.reset_all()
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_reset_all_restores_mode(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        ScreenTrust.reset_all()
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")


class TestPermissionManagerOwnerTrusted(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        ScreenTrust.reset_all()
        self.pm = PermissionManager()

    def test_safe_auto_approves_with_owner_trusted(self):
        result = self.pm.evaluate("run_diagnostics")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])

    def test_medium_auto_approves_with_owner_trusted(self):
        result = self.pm.evaluate("open_application")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])

    def test_high_auto_approves_with_owner_trusted(self):
        result = self.pm.evaluate("screen_capture")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])
        self.assertTrue(result["owner_trusted"])
        self.assertIn("trusted", result["confirmation_prompt"].lower())

    def test_draft_email_remains_pending_with_owner_trusted(self):
        result = self.pm.evaluate("draft_email")
        self.assertEqual(result["decision"], "pending")
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["owner_trusted"])

    def test_draft_whatsapp_remains_pending_with_owner_trusted(self):
        result = self.pm.evaluate("draft_whatsapp")
        self.assertEqual(result["decision"], "pending")
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["owner_trusted"])

    def test_send_message_remains_pending_with_owner_trusted(self):
        result = self.pm.evaluate("send_message")
        self.assertEqual(result["decision"], "pending")
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["owner_trusted"])

    def test_critical_still_blocked_with_owner_trusted(self):
        result = self.pm.evaluate("delete_files")
        self.assertEqual(result["decision"], "blocked")
        self.assertIn("sandbox", result["block_reason"].lower())

    def test_critical_send_message_auto_still_blocked(self):
        result = self.pm.evaluate("send_message_auto")
        self.assertEqual(result["decision"], "blocked")
        self.assertEqual(result["risk_level"], "CRITICAL")

    def test_emergency_stop_overrides_owner_trusted(self):
        EmergencyStop.engage(reason="test")
        result = self.pm.evaluate("run_diagnostics")
        self.assertEqual(result["decision"], "blocked")
        self.assertIn("emergency", result["block_reason"].lower())
        EmergencyStop.clear()

    def test_emergency_stop_blocks_high_even_with_owner_trusted(self):
        EmergencyStop.engage(reason="test")
        result = self.pm.evaluate("screen_capture")
        self.assertEqual(result["decision"], "blocked")
        EmergencyStop.clear()


class TestPermissionManagerOwnerDisabled(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        ScreenTrust.reset_all()
        ScreenTrust.set_owner_trusted(False)
        self.pm = PermissionManager()

    def test_high_requires_confirmation_when_owner_disabled(self):
        result = self.pm.evaluate("screen_capture")
        self.assertEqual(result["decision"], "pending")
        self.assertTrue(result["requires_confirmation"])
        self.assertFalse(result["owner_trusted"])

    def test_safe_still_auto_approves_when_owner_disabled(self):
        result = self.pm.evaluate("run_diagnostics")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])

    def test_medium_still_auto_approves_when_owner_disabled(self):
        result = self.pm.evaluate("open_application")
        self.assertEqual(result["decision"], "approved")
        self.assertFalse(result["requires_confirmation"])

    def test_critical_still_blocked_when_owner_disabled(self):
        result = self.pm.evaluate("delete_files")
        self.assertEqual(result["decision"], "blocked")


class TestBridgeOwnerModeCommands(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()
        ScreenTrust.reset_all()

    def test_enable_owner_mode(self):
        ScreenTrust.set_owner_trusted(False)
        result = Phase3CommandBridge.try_handle("owner mode on")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_disable_owner_mode(self):
        result = Phase3CommandBridge.try_handle("owner mode off")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])
        self.assertFalse(ScreenTrust.is_owner_trusted())

    def test_owner_mode_status_enabled(self):
        result = Phase3CommandBridge.try_handle("owner mode status")
        self.assertTrue(result["handled"])
        self.assertIn("enabled", result["result"]["message"])

    def test_owner_mode_status_disabled(self):
        ScreenTrust.set_owner_trusted(False)
        result = Phase3CommandBridge.try_handle("owner mode status")
        self.assertTrue(result["handled"])
        self.assertIn("disabled", result["result"]["message"])

    def test_owner_mode_status_with_emergency(self):
        EmergencyStop.engage(reason="test")
        result = Phase3CommandBridge.try_handle("owner mode status")
        self.assertTrue(result["handled"])
        self.assertIn("emergency", result["result"]["message"].lower())
        EmergencyStop.clear()

    def test_enable_owner_mode_hindi(self):
        ScreenTrust.set_owner_trusted(False)
        result = Phase3CommandBridge.try_handle("owner mode enable karo")
        self.assertTrue(result["handled"])
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_disable_owner_mode_hindi(self):
        result = Phase3CommandBridge.try_handle("owner mode disable karo")
        self.assertTrue(result["handled"])
        self.assertFalse(ScreenTrust.is_owner_trusted())


class TestBridgeScreenDekhoOwnerTrusted(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()
        ScreenTrust.reset_all()
        observer = Phase3CommandBridge._get_screen_observer()
        observer.reset()
        observer._screenshot_service.capture_real = lambda: {
            "ok": True, "method": "pil_imagegrab", "image_bytes": b"jpeg",
            "mime": "image/jpeg", "visible_text": "Visual Studio Code window",
            "error": None,
        }
        observer._vision_analyzer.analyze = lambda payload, allow_cloud=True: {
            "ok": True, "summary": "The screen shows Visual Studio Code.",
            "detected_context": "code", "sensitive_content_detected": False,
            "requires_confirmation_before_action": True,
            "source": "deterministic_test_analyzer", "error": None,
        }

    def test_screen_dekho_owner_trusted_no_permission_needed(self):
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertFalse(data.get("requires_permission", True))

    def test_screen_dekho_owner_trusted_message(self):
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertIn("trusted", result["result"]["message"].lower())

    def test_screen_dekho_owner_disabled_needs_permission(self):
        ScreenTrust.set_owner_trusted(False)
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertTrue(data.get("requires_permission", False))

    def test_screen_dekho_owner_disabled_message(self):
        ScreenTrust.set_owner_trusted(False)
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertIn("permission", result["result"]["message"].lower())

    def test_screen_dekho_emergency_blocks(self):
        EmergencyStop.engage(reason="test")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])
        EmergencyStop.clear()


class TestBridgeScreenTrustWithOwnerMode(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()
        ScreenTrust.reset_all()

    def test_trusted_screen_access_with_owner_mode(self):
        # Owner vision is tested through deterministic capture and analyzer boundaries.
        ScreenTrust.set_mode("trusted_session_read_only")
        observer = Phase3CommandBridge._get_screen_observer()
        with mock.patch.object(observer._screenshot_service, "capture_real", return_value={
            "ok": True, "method": "pil_imagegrab", "image_bytes": b"\xff\xd8\xff\xd9",
            "mime": "image/jpeg", "visible_text": "", "width": 1920, "height": 1080,
        }), mock.patch.object(observer._vision_analyzer, "analyze", return_value={
            "ok": True, "summary": "A code editor is open.",
            "detected_context": "code", "sensitive_content_detected": False,
            "requires_confirmation_before_action": True,
            "source": "deterministic_test_analyzer", "error": None,
        }):
            result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])
        self.assertIn("trusted", result["result"]["message"].lower())
        observation = result["result"]["data"]["observation"]
        self.assertEqual(observation["status"], "completed")
        self.assertEqual(observation["screenshot_method"], "pil_imagegrab")
        self.assertFalse(observation["sensitive_content_detected"])
        self.assertFalse(observation["store_screenshot"])

    def test_revoke_screen_access_preserves_owner_mode(self):
        Phase3CommandBridge.try_handle("revoke screen access")
        self.assertTrue(ScreenTrust.is_owner_trusted())

    def test_allow_screen_access_preserves_owner_mode(self):
        ScreenTrust.set_owner_trusted(False)
        Phase3CommandBridge.try_handle("allow screen access for this session")
        self.assertFalse(ScreenTrust.is_owner_trusted())


class TestOwnerTrustedDecisionKeys(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        ScreenTrust.reset_all()
        self.pm = PermissionManager()

    def test_decision_has_owner_trusted_key(self):
        result = self.pm.evaluate("run_diagnostics")
        self.assertIn("owner_trusted", result)

    def test_owner_trusted_key_true_when_enabled(self):
        result = self.pm.evaluate("screen_capture")
        self.assertTrue(result["owner_trusted"])

    def test_owner_trusted_key_false_when_disabled(self):
        ScreenTrust.set_owner_trusted(False)
        result = self.pm.evaluate("screen_capture")
        self.assertFalse(result["owner_trusted"])

    def test_owner_trusted_key_false_for_safe(self):
        result = self.pm.evaluate("run_diagnostics")
        self.assertFalse(result["owner_trusted"])


class TestOwnerTrustedThreadSafety(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_all()
        EmergencyStop.clear()

    def test_concurrent_owner_mode_changes(self):
        barrier = threading.Barrier(10)
        results = []
        lock = threading.Lock()

        def worker(idx):
            barrier.wait()
            if idx % 2 == 0:
                ScreenTrust.set_owner_trusted(True)
            else:
                ScreenTrust.set_owner_trusted(False)
            with lock:
                results.append(ScreenTrust.is_owner_trusted())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 10)
        for r in results:
            self.assertIsInstance(r, bool)

    def test_concurrent_evaluate_with_owner_mode(self):
        ScreenTrust.reset_all()
        EmergencyStop.clear()
        barrier = threading.Barrier(5)
        results = []
        lock = threading.Lock()

        def worker():
            barrier.wait()
            pm = PermissionManager()
            result = pm.evaluate("screen_capture")
            with lock:
                results.append(result["decision"])

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(results), 5)
        for r in results:
            self.assertEqual(r, "approved")


class TestExistingScreenTrustTestsStillPass(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_all()
        EmergencyStop.clear()

    def test_default_mode_is_ask_each_time(self):
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")

    def test_default_is_not_trusted(self):
        self.assertFalse(ScreenTrust.is_trusted())

    def test_trusted_session_is_trusted(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        self.assertTrue(ScreenTrust.is_trusted())

    def test_trusted_local_is_trusted(self):
        ScreenTrust.set_mode("trusted_local_read_only")
        self.assertTrue(ScreenTrust.is_trusted())

    def test_denied_is_not_trusted(self):
        ScreenTrust.set_mode("denied")
        self.assertFalse(ScreenTrust.is_trusted())

    def test_emergency_stop_overrides_trusted(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        self.assertTrue(ScreenTrust.is_trusted())
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_trusted())
        EmergencyStop.clear()


if __name__ == "__main__":
    unittest.main()
