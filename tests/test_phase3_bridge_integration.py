import unittest
from engine.app.phase3_command_bridge import Phase3CommandBridge
from engine.control.safety import EmergencyStop
from engine.memory.preference_store import PreferenceStore
from engine.diagnostic_doctors.runtime_doctor import RuntimeDoctor
from vision.screen_trust import ScreenTrust


class TestPhase3BridgeIntegration(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        ScreenTrust.set_owner_trusted(False)

    def test_remember_preferred_browser_is_handled(self):
        result = Phase3CommandBridge.try_handle("remember my preferred browser is Chrome")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])

    def test_safe_memory_is_stored(self):
        result = Phase3CommandBridge.try_handle("remember my preferred browser is Firefox")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])

    def test_what_do_you_remember_returns_summary(self):
        result = Phase3CommandBridge.try_handle("what do you remember")
        self.assertTrue(result["handled"])

    def test_forget_preferred_browser_removes_memory(self):
        Phase3CommandBridge.try_handle("remember my planning model is DeepSeek")
        result = Phase3CommandBridge.try_handle("forget my planning model")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])

    def test_password_memory_is_blocked(self):
        result = Phase3CommandBridge.try_handle("remember my password is secret123")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])

    def test_api_key_memory_is_blocked(self):
        result = Phase3CommandBridge.try_handle("remember my api_key is sk-abcdefghijklmnop")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])

    def test_diagnose_nexi_is_handled(self):
        result = Phase3CommandBridge.try_handle("diagnose Nexi")
        self.assertTrue(result["handled"])

    def test_diagnosis_contains_status_and_checks(self):
        result = Phase3CommandBridge.try_handle("diagnose Nexi")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertIn("diagnosis", data)
        self.assertIn("checks", data)
        self.assertIn("ok", result["result"])

    def test_plan_this_task_creates_safe_plan(self):
        result = Phase3CommandBridge.try_handle("plan this task")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertIn("task", data)
        self.assertIn("risk_level", data)

    def test_delete_all_files_is_blocked(self):
        result = Phase3CommandBridge.try_handle("plan this task: delete all files")
        self.assertTrue(result["handled"])
        risk = result["result"]["data"].get("risk_level", "")
        task = result["result"]["data"].get("task", {})
        steps = task.get("steps", [])
        if steps:
            self.assertEqual(steps[0].get("risk_level"), "CRITICAL")

    def test_screen_dekho_creates_permission_request(self):
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertTrue(data.get("requires_permission", False))
        self.assertIn("request_id", data)

    def test_screen_dekho_does_not_capture_screenshot_before_approval(self):
        from vision.screen_observer import ScreenObserver
        observer = ScreenObserver()
        capture_count_before = observer.screenshot_service.capture_count
        req = observer.request_observation("test screen")
        self.assertEqual(observer.screenshot_service.capture_count, capture_count_before)

    def test_cloud_analysis_false_by_default(self):
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        observation = data.get("observation", {})
        self.assertFalse(observation.get("allow_cloud_analysis", True))

    def test_stop_everything_engages_emergency_stop(self):
        EmergencyStop.clear()
        self.assertFalse(EmergencyStop.is_engaged())
        result = Phase3CommandBridge.try_handle("stop everything")
        self.assertTrue(result["handled"])
        self.assertTrue(EmergencyStop.is_engaged())

    def test_risky_action_after_stop_is_blocked(self):
        Phase3CommandBridge.try_handle("stop everything")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])

    def test_unknown_command_returns_handled_false(self):
        result = Phase3CommandBridge.try_handle("the quick brown fox")
        self.assertFalse(result["handled"])

    def test_existing_command_path_still_available(self):
        result = Phase3CommandBridge.try_handle("open chrome")
        self.assertFalse(result["handled"])

    def test_check_yourself_returns_diagnosis(self):
        result = Phase3CommandBridge.try_handle("check yourself")
        self.assertTrue(result["handled"])
        self.assertIn("checks", result["result"]["data"])

    def test_remember_hindi_memory(self):
        result = Phase3CommandBridge.try_handle("yaad rakho preferred editor vs code")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])

    def test_sab_band_karo_engages_stop(self):
        EmergencyStop.clear()
        Phase3CommandBridge.try_handle("sab band karo")
        self.assertTrue(EmergencyStop.is_engaged())

    def test_emergency_stop_blocks_screen(self):
        EmergencyStop.engage("test stop")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertFalse(result["result"]["ok"])
        EmergencyStop.clear()

    def test_check_hotword_specific(self):
        result = Phase3CommandBridge.try_handle("check hotword")
        self.assertTrue(result["handled"])

    def test_check_memory_specific(self):
        result = Phase3CommandBridge.try_handle("check memory")
        self.assertTrue(result["handled"])

    def test_bridge_reset_clears_state(self):
        Phase3CommandBridge.try_handle("remember my test_key is test_value")
        Phase3CommandBridge.reset()
        from engine.app.phase3_command_bridge import Phase3CommandBridge as PCB
        self.assertIsNone(PCB._preference_store)

    def test_empty_query_not_handled(self):
        result = Phase3CommandBridge.try_handle("")
        self.assertFalse(result["handled"])

    def test_none_query_not_handled(self):
        result = Phase3CommandBridge.try_handle(None)
        self.assertFalse(result["handled"])

    def test_forget_nonexistent_key(self):
        result = Phase3CommandBridge.try_handle("forget my nonexistent_key_xyz")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])

    def test_diagnose_returns_summary(self):
        result = Phase3CommandBridge.try_handle("diagnose Nexi")
        msg = result["result"]["message"]
        self.assertIsInstance(msg, str)
        self.assertGreater(len(msg), 5)

    def test_plan_task_with_goal(self):
        result = Phase3CommandBridge.try_handle("plan this task: organize my workspace")
        self.assertTrue(result["handled"])
        self.assertIn("task", result["result"]["data"])

    def test_bridge_does_not_interfere_with_legacy_diagnostics(self):
        old_result = RuntimeDoctor.diagnose()
        self.assertIn("checks", old_result)
        self.assertIn("ok", old_result)

    def test_evaluate_screen_request_id_returned(self):
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        request_id = data.get("request_id", "")
        self.assertTrue(request_id.startswith("obs_"))

    def test_remember_that_my_preferred(self):
        result = Phase3CommandBridge.try_handle("remember that my preferred browser is Chrome")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])


class TestPhase3BridgeMemoryPersistence(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        ScreenTrust.set_owner_trusted(False)

    def test_memory_persists_across_calls(self):
        Phase3CommandBridge.try_handle("remember my coding_model is GLM 5.1")
        result = Phase3CommandBridge.try_handle("what do you remember")
        self.assertIn("coding_model", result["result"]["message"])


class TestPhase3BridgeSafety(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        ScreenTrust.set_owner_trusted(False)

    def test_emergency_stop_blocks_autonomy(self):
        EmergencyStop.engage("test")
        result = Phase3CommandBridge.try_handle("plan this task")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])
        EmergencyStop.clear()

    def test_try_handle_returns_valid_structure(self):
        result = Phase3CommandBridge.try_handle("hello")
        self.assertIn("handled", result)
        self.assertIn("result", result)
        result2 = Phase3CommandBridge.try_handle("diagnose Nexi")
        self.assertIn("handled", result2)
        self.assertIn("result", result2)
        r = result2["result"]
        self.assertIn("ok", r)
        self.assertIn("message", r)
        self.assertIn("data", r)
        self.assertIn("error", r)


class TestPhase3ScreenVisionApproval(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        ScreenTrust.set_owner_trusted(False)

    def _get_fresh_observer(self):
        observer = Phase3CommandBridge._get_screen_observer()
        observer.reset()
        observer._screenshot_service._capture_real = lambda: {
            "ok": True,
            "method": "pil_imagegrab",
            "image_bytes": b"jpeg",
            "mime": "image/jpeg",
            "visible_text": "Visual Studio Code window",
            "error": None,
        }
        observer._vision_analyzer.analyze = lambda payload, allow_cloud=True: {
            "ok": True,
            "summary": "The screen shows Visual Studio Code.",
            "detected_context": "code",
            "context_label": "Code Editor",
            "possible_issue": "",
            "suggested_next_step": "Review before action",
            "sensitive_content_detected": False,
            "requires_confirmation_before_action": True,
            "source": "deterministic_test_analyzer",
            "error": None,
        }
        return observer

    def test_screen_observation_request_then_approve_uses_real_capture_method(self):
        observer = self._get_fresh_observer()

        req = observer.request_observation("test screen observation")
        self.assertTrue(req["requires_permission"])
        self.assertFalse(req["permission_granted"])
        self.assertFalse(req["allow_cloud_analysis"])
        self.assertFalse(req["store_screenshot"])
        self.assertEqual(req["status"], "pending")

        capture_count_before = observer.screenshot_service.capture_count
        approve_result = observer.approve_observation(req["request_id"], "yes")
        self.assertTrue(approve_result["ok"])
        self.assertEqual(approve_result["status"], "approved")

        self.assertEqual(observer.screenshot_service.capture_count, capture_count_before + 1)

        updated = observer._requests.get(req["request_id"])
        screenshot = updated["screenshot_data"]
        self.assertIsNotNone(screenshot)
        self.assertEqual(screenshot.get("method"), "pil_imagegrab")

    def test_approved_observation_analyze_returns_safe_result(self):
        observer = self._get_fresh_observer()

        req = observer.request_observation("analyze this screen")
        request_id = req["request_id"]

        approve_result = observer.approve_observation(request_id, "yes")
        self.assertTrue(approve_result["ok"])

        analysis = observer.analyze_observation(request_id)
        self.assertTrue(analysis.get("ok"))
        self.assertIn("detected_context", analysis)
        self.assertIn("summary", analysis)
        self.assertFalse(analysis.get("sensitive_content_detected"))
        self.assertTrue(analysis.get("requires_confirmation_before_action"))
        updated = observer._requests[request_id]
        self.assertEqual(updated["status"], "completed")
        self.assertFalse(updated["allow_cloud_analysis"])
        self.assertFalse(updated["store_screenshot"])
        self.assertNotIn("image_bytes", updated["screenshot_data"])

    def test_cloud_analysis_false_by_default_after_approval(self):
        observer = self._get_fresh_observer()

        req = observer.request_observation("check this screen")
        request_id = req["request_id"]

        observer.approve_observation(request_id, "yes", allow_cloud_analysis=False, store_screenshot=False)
        updated = observer._requests.get(request_id)
        self.assertFalse(updated["allow_cloud_analysis"])
        self.assertFalse(updated["store_screenshot"])

    def test_screenshot_not_stored_by_default(self):
        observer = self._get_fresh_observer()

        req = observer.request_observation("view screen")
        request_id = req["request_id"]

        observer.approve_observation(request_id, "yes")
        updated = observer._requests.get(request_id)
        self.assertFalse(updated["store_screenshot"])

    def test_real_capture_disabled_by_default_is_unavailable(self):
        from vision.screenshot_service import ScreenshotService
        service = ScreenshotService()
        self.assertFalse(service._real_capture_enabled)
        result = service.capture()
        self.assertFalse(result["ok"])
        self.assertEqual(result["method"], "unavailable")

    def test_diagnose_nexi_alias_works(self):
        result = Phase3CommandBridge.try_handle("diagnose Nexi")
        self.assertTrue(result["handled"])

    def test_diagnose_jarvi_alias_works(self):
        result = Phase3CommandBridge.try_handle("diagnose Jarvi")
        self.assertTrue(result["handled"])


if __name__ == "__main__":
    unittest.main()
