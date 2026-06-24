import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import threading

from src.orin.app.phase3_command_bridge import Phase3CommandBridge
from src.orin.app.runtime_context import get_conversation_buffer, reset_runtime
from src.orin.vision.screen_trust import ScreenTrust
from src.orin.vision.screen_observer import ScreenObserver
from src.orin.control.safety import EmergencyStop
from src.orin.memory.conversation_buffer import ConversationBuffer


class TestConversationBufferStore(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()

    def test_command_response_stored_as_one_turn(self):
        buf = get_conversation_buffer()
        buf.append_turn("diagnose Nexi", "Nexi diagnostics complete.")
        self.assertEqual(buf.count(), 1)
        turn = buf.get_turns()[0]
        self.assertEqual(turn["user"], "diagnose Nexi")
        self.assertIn("diagnostics", turn["assistant"])
        self.assertIn("timestamp", turn)

    def test_no_duplicate_turns_stored(self):
        buf = get_conversation_buffer()
        buf.append_turn("q1", "a1")
        buf.append_turn("q2", "a2")
        buf.append_turn("q3", "a3")
        self.assertEqual(buf.count(), 3)

    def test_last_5_turns_after_7_commands(self):
        buf = get_conversation_buffer()
        for i in range(7):
            buf.append_turn(f"question {i}", f"answer {i}")
        self.assertEqual(buf.count(), 5)
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "question 2")
        self.assertEqual(turns[-1]["user"], "question 6")


class TestConversationRecallCommands(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()

    def test_what_did_i_just_ask_returns_previous(self):
        buf = get_conversation_buffer()
        buf.append_turn("diagnose Nexi", "All systems OK.")
        result = Phase3CommandBridge.try_handle("what did I just ask")
        self.assertTrue(result["handled"])
        msg = result["result"]["message"]
        self.assertIn("diagnose Nexi", msg)
        self.assertNotIn("what did I just ask", msg)

    def test_repeat_my_last_question_returns_previous(self):
        buf = get_conversation_buffer()
        buf.append_turn("open Chrome", "Opening Chrome.")
        result = Phase3CommandBridge.try_handle("repeat my last question")
        self.assertTrue(result["handled"])
        msg = result["result"]["message"]
        self.assertIn("open Chrome", msg)
        self.assertNotIn("repeat", msg.lower())

    def test_what_did_i_just_ask_with_no_history(self):
        result = Phase3CommandBridge.try_handle("what did I just ask")
        self.assertTrue(result["handled"])
        self.assertIn("No conversation", result["result"]["message"])

    def test_show_last_5_chats_returns_history(self):
        buf = get_conversation_buffer()
        buf.append_turn("q1", "a1")
        buf.append_turn("q2", "a2")
        result = Phase3CommandBridge.try_handle("show last 5 chats")
        self.assertTrue(result["handled"])
        msg = result["result"]["message"]
        self.assertIn("q1", msg)
        self.assertIn("q2", msg)
        self.assertIn("Nexi:", msg)

    def test_show_last_5_chats_empty(self):
        result = Phase3CommandBridge.try_handle("show last 5 chats")
        self.assertTrue(result["handled"])
        self.assertIn("No conversation", result["result"]["message"])

    def test_show_last_5_chats_redacted(self):
        buf = get_conversation_buffer()
        buf.append_turn("my password is secret123", "ok")
        buf.append_turn("open Chrome", "Opening Chrome.")
        result = Phase3CommandBridge.try_handle("show last 5 chats")
        self.assertTrue(result["handled"])
        msg = result["result"]["message"]
        self.assertNotIn("secret123", msg)
        self.assertIn("[Content blocked]", msg)
        self.assertIn("open Chrome", msg)

    def test_clear_conversation_memory(self):
        buf = get_conversation_buffer()
        buf.append_turn("q1", "a1")
        result = Phase3CommandBridge.try_handle("clear conversation memory")
        self.assertTrue(result["handled"])
        self.assertIn("cleared", result["result"]["message"].lower())
        self.assertEqual(buf.count(), 0)

    def test_clear_conversation_memory_hindi(self):
        buf = get_conversation_buffer()
        buf.append_turn("q1", "a1")
        result = Phase3CommandBridge.try_handle("conversation memory clear karo")
        self.assertTrue(result["handled"])
        self.assertEqual(buf.count(), 0)


class TestConversationBufferSecurity(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()

    def test_password_not_stored_raw(self):
        buf = get_conversation_buffer()
        buf.append_turn("my password is secret123", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_api_key_not_stored_raw(self):
        buf = get_conversation_buffer()
        buf.append_turn("api_key = sk-abc123def456", "ok")
        turns = buf.get_turns()
        self.assertEqual(turns[0]["user"], "[Content blocked]")

    def test_recall_returns_redacted_text(self):
        buf = get_conversation_buffer()
        buf.append_turn("my email is test@example.com", "ok")
        result = Phase3CommandBridge.try_handle("what did I just ask")
        msg = result["result"]["message"]
        self.assertNotIn("test@example.com", msg)
        self.assertIn("[REDACTED]", msg)


class TestScreenTrustCommands(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()
        ScreenTrust.reset_to_ask()
        ScreenTrust.set_owner_trusted(False)

    def test_allow_screen_access_sets_trusted(self):
        result = Phase3CommandBridge.try_handle("allow screen access for this session")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])
        self.assertEqual(ScreenTrust.get_mode(), "trusted_session_read_only")
        self.assertTrue(ScreenTrust.is_trusted())

    def test_trust_screen_access_sets_trusted(self):
        result = Phase3CommandBridge.try_handle("trust screen access for this session")
        self.assertTrue(result["handled"])
        self.assertEqual(ScreenTrust.get_mode(), "trusted_session_read_only")

    def test_screen_access_allow_karo(self):
        result = Phase3CommandBridge.try_handle("screen access allow karo")
        self.assertTrue(result["handled"])
        self.assertEqual(ScreenTrust.get_mode(), "trusted_session_read_only")

    def test_screen_access_status_reports_trusted(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen access status")
        self.assertTrue(result["handled"])
        self.assertIn("trusted", result["result"]["data"]["mode"])
        self.assertTrue(result["result"]["data"]["is_trusted"])

    def test_screen_trust_status(self):
        result = Phase3CommandBridge.try_handle("screen trust status")
        self.assertTrue(result["handled"])
        self.assertIn("ask_each_time", result["result"]["data"]["mode"])
        self.assertFalse(result["result"]["data"]["is_trusted"])

    def test_revoke_screen_access_resets(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("revoke screen access")
        self.assertTrue(result["handled"])
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")
        self.assertFalse(ScreenTrust.is_trusted())

    def test_screen_access_off(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen access off")
        self.assertTrue(result["handled"])
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")

    def test_emergency_stop_makes_trust_inactive(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        self.assertTrue(ScreenTrust.is_trusted())
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_trusted())
        EmergencyStop.clear()

    def test_emergency_stop_with_screen_access_status(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        EmergencyStop.engage(reason="test")
        result = Phase3CommandBridge.try_handle("screen access status")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["data"]["emergency_stop_active"])
        EmergencyStop.clear()


class TestScreenObservationTrustedFlow(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()
        ScreenTrust.reset_to_ask()
        ScreenTrust.set_owner_trusted(False)
        observer = Phase3CommandBridge._get_screen_observer()
        observer.reset()

    def test_screen_dekho_without_trust_needs_permission(self):
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertTrue(data.get("requires_permission", False))

    def test_screen_dekho_with_trust_skips_permission(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        data = result["result"]["data"]
        self.assertFalse(data.get("requires_permission", True))

    def test_trusted_flow_preserves_ok_on_success(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        self.assertTrue(result["result"]["ok"])

    def test_trusted_flow_returns_error_on_failure(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        EmergencyStop.engage(reason="test block")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])
        error = result["result"]["error"]
        if isinstance(error, dict):
            self.assertIn("emergency", error.get("message", "").lower())
        else:
            self.assertIn("emergency", error.lower())
        EmergencyStop.clear()

    def test_trusted_flow_no_cloud_upload(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        obs = data.get("observation", {})
        self.assertFalse(obs.get("allow_cloud_analysis", True))

    def test_trusted_flow_no_screenshot_stored(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        obs = data.get("observation", {})
        self.assertFalse(obs.get("store_screenshot", True))

    def test_trusted_read_only_flag_set(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        self.assertTrue(data.get("trusted_read_only", False))

    def test_emergency_stop_blocks_trusted_observation(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        EmergencyStop.engage(reason="test")
        result = Phase3CommandBridge.try_handle("screen dekho")
        self.assertTrue(result["handled"])
        self.assertFalse(result["result"]["ok"])
        EmergencyStop.clear()

    def test_trusted_flow_returns_analysis_summary(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        obs = data.get("observation", {})
        self.assertIn("summary", obs)
        self.assertIn("detected_context", obs)

    def test_trusted_screen_response_includes_trust_message(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        msg = result["result"]["message"]
        self.assertIn("Using trusted local read-only access.", msg)

    def test_trusted_screen_response_includes_result_or_fallback(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        msg = result["result"]["message"]
        self.assertTrue(
            "Current analyzer result:" in msg
            or "could not classify" in msg
            or "Mock screen analysis" in msg
        )

    def test_trusted_screen_response_includes_mock_phase_fallback(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        msg = result["result"]["message"]
        self.assertIn("Mock screen analysis is active. Real screen capture is not enabled yet.", msg)
        self.assertIn("real screen capture/OCR vision is not enabled in this phase", msg)

    def test_trusted_screen_formatter_preserves_observation_data(self):
        msg = Phase3CommandBridge._format_trusted_screen_message({
            "ok": True,
            "summary": "Top-level summary.",
            "message": "Analyzer message.",
            "analysis": {"detected_context": "code", "summary": "Analysis summary."},
            "data": {
                "observation": {
                    "summary": "Observation summary.",
                    "detected_context": "code",
                    "screenshot_method": "mock",
                }
            },
            "error": "non-blocking warning",
        })
        self.assertIn("Top-level summary.", msg)
        self.assertIn("Analyzer message.", msg)
        self.assertIn("Observation summary.", msg)
        self.assertIn("Detected screen context: code.", msg)
        self.assertIn("non-blocking warning", msg)

    def test_trusted_screen_response_not_only_trust_message(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        msg = result["result"]["message"].strip()
        self.assertNotEqual(msg, "Using trusted local read-only access.")

    def test_trusted_screen_response_no_yes_no_prompt(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        result = Phase3CommandBridge.try_handle("screen dekho")
        msg = result["result"]["message"].lower()
        self.assertNotIn("yes or no", msg)
        self.assertNotIn("say yes", msg)
        self.assertNotIn("permission", msg)

    def test_owner_trusted_screen_uses_trusted_observation(self):
        ScreenTrust.set_owner_trusted(True)
        result = Phase3CommandBridge.try_handle("screen dekho")
        data = result["result"]["data"]
        self.assertFalse(data.get("requires_permission", True))
        self.assertIn("Current analyzer result:", result["result"]["message"])


class TestRequestTrustedReadOnly(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.observer = ScreenObserver()

    def test_emergency_stop_blocks_capture(self):
        EmergencyStop.engage(reason="test")
        result = self.observer.request_trusted_read_only("test screen")
        self.assertFalse(result["ok"])
        self.assertIn("emergency", result["error"].lower())
        self.assertIsNone(result["request_id"])
        EmergencyStop.clear()

    def test_success_returns_analysis(self):
        result = self.observer.request_trusted_read_only("test screen")
        self.assertTrue(result["ok"])
        self.assertIsNotNone(result["request_id"])
        self.assertIn("summary", result)
        self.assertIn("analysis", result)

    def test_no_permission_required(self):
        result = self.observer.request_trusted_read_only("test screen")
        data = result["data"]
        self.assertFalse(data["requires_permission"])
        self.assertTrue(data["trusted_read_only"])

    def test_no_screenshot_stored(self):
        result = self.observer.request_trusted_read_only("test screen")
        obs = result["data"]["observation"]
        self.assertFalse(obs["store_screenshot"])
        self.assertFalse(obs["allow_cloud_analysis"])

    def test_observation_status_completed(self):
        result = self.observer.request_trusted_read_only("test screen")
        req_id = result["request_id"]
        status = self.observer.get_observation_status(req_id)
        self.assertTrue(status["ok"])
        self.assertEqual(status["status"], "completed")


class TestUnknownCommandFallback(unittest.TestCase):
    def setUp(self):
        Phase3CommandBridge.reset()
        EmergencyStop.clear()
        reset_runtime()
        ScreenTrust.reset_to_ask()

    def test_unknown_command_falls_back(self):
        result = Phase3CommandBridge.try_handle("the quick brown fox jumps")
        self.assertFalse(result["handled"])

    def test_existing_command_not_affected_by_bridge(self):
        result = Phase3CommandBridge.try_handle("open chrome")
        self.assertFalse(result["handled"])


class TestExistingTestsStillPass(unittest.TestCase):
    def test_conversation_buffer_import(self):
        from src.orin.memory.conversation_buffer import ConversationBuffer
        buf = ConversationBuffer()
        buf.append_turn("test", "ok")
        self.assertEqual(buf.count(), 1)

    def test_screen_trust_import(self):
        from src.orin.vision.screen_trust import ScreenTrust
        ScreenTrust.reset_to_ask()
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")

    def test_screen_observer_import(self):
        from src.orin.vision.screen_observer import ScreenObserver
        observer = ScreenObserver()
        req = observer.request_observation("test")
        self.assertTrue(req["requires_permission"])

    def test_screen_context_import(self):
        from src.orin.vision.screen_context import detect_screen_command
        self.assertTrue(detect_screen_command("screen dekho"))
        self.assertFalse(detect_screen_command("open chrome"))

    def test_phase3_bridge_import(self):
        from src.orin.app.phase3_command_bridge import Phase3CommandBridge
        result = Phase3CommandBridge.try_handle("")
        self.assertFalse(result["handled"])

    def test_runtime_context_import(self):
        from src.orin.app.runtime_context import get_conversation_buffer, get_screen_trust
        buf = get_conversation_buffer()
        self.assertIsInstance(buf, ConversationBuffer)
        trust = get_screen_trust()
        self.assertEqual(trust, ScreenTrust)


class TestThreadSafety(unittest.TestCase):
    def setUp(self):
        reset_runtime()
        EmergencyStop.clear()
        ScreenTrust.reset_to_ask()

    def test_concurrent_conversation_store(self):
        buf = get_conversation_buffer()
        barrier = threading.Barrier(10)

        def worker(idx):
            barrier.wait()
            buf.append_turn(f"q{idx}", f"a{idx}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertLessEqual(buf.count(), 5)
        self.assertGreater(buf.count(), 0)

    def test_concurrent_trust_changes(self):
        barrier = threading.Barrier(5)

        def worker(mode):
            barrier.wait()
            ScreenTrust.set_mode(mode)

        modes = ["denied", "trusted_session_read_only", "trusted_local_read_only",
                 "ask_each_time", "denied"]
        threads = [threading.Thread(target=worker, args=(m,)) for m in modes]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertIn(ScreenTrust.get_mode(), ["denied", "trusted_session_read_only",
                                                "trusted_local_read_only", "ask_each_time"])


if __name__ == "__main__":
    unittest.main()
