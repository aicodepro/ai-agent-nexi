import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
import threading
from vision.screen_trust import ScreenTrust, VALID_MODES
from engine.control.safety import EmergencyStop


class TestScreenTrustDefaultMode(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_to_ask()
        EmergencyStop.clear()

    def test_default_mode_is_ask_each_time(self):
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")

    def test_default_is_not_trusted(self):
        self.assertFalse(ScreenTrust.is_trusted())


class TestScreenTrustModes(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_to_ask()
        EmergencyStop.clear()

    def test_trusted_session_is_trusted(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        self.assertTrue(ScreenTrust.is_trusted())

    def test_trusted_local_is_trusted(self):
        ScreenTrust.set_mode("trusted_local_read_only")
        self.assertTrue(ScreenTrust.is_trusted())

    def test_denied_is_not_trusted(self):
        ScreenTrust.set_mode("denied")
        self.assertFalse(ScreenTrust.is_trusted())

    def test_ask_each_time_is_not_trusted(self):
        ScreenTrust.set_mode("ask_each_time")
        self.assertFalse(ScreenTrust.is_trusted())

    def test_set_mode_returns_true_on_valid(self):
        result = ScreenTrust.set_mode("trusted_session_read_only")
        self.assertTrue(result)

    def test_set_mode_returns_false_on_invalid(self):
        result = ScreenTrust.set_mode("invalid_mode")
        self.assertFalse(result)

    def test_invalid_mode_does_not_change_mode(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        ScreenTrust.set_mode("invalid_mode")
        self.assertEqual(ScreenTrust.get_mode(), "trusted_session_read_only")

    def test_all_valid_modes(self):
        for mode in VALID_MODES:
            ScreenTrust.set_mode(mode)
            self.assertEqual(ScreenTrust.get_mode(), mode)


class TestScreenTrustReset(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_to_ask()
        EmergencyStop.clear()

    def test_reset_to_ask(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        ScreenTrust.reset_to_ask()
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")
        self.assertFalse(ScreenTrust.is_trusted())

    def test_reset_alias(self):
        ScreenTrust.set_mode("trusted_local_read_only")
        ScreenTrust.reset()
        self.assertEqual(ScreenTrust.get_mode(), "ask_each_time")


class TestScreenTrustEmergencyStop(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_to_ask()
        EmergencyStop.clear()

    def test_emergency_stop_overrides_trusted(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        self.assertTrue(ScreenTrust.is_trusted())
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_trusted())

    def test_emergency_stop_cleared_restores_trust(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_trusted())
        EmergencyStop.clear()
        self.assertTrue(ScreenTrust.is_trusted())

    def test_emergency_stop_overrides_local_trusted(self):
        ScreenTrust.set_mode("trusted_local_read_only")
        EmergencyStop.engage(reason="test")
        self.assertFalse(ScreenTrust.is_trusted())


class TestScreenTrustToDict(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_to_ask()
        EmergencyStop.clear()

    def test_to_dict_has_required_keys(self):
        d = ScreenTrust.to_dict()
        self.assertIn("mode", d)
        self.assertIn("is_trusted", d)
        self.assertIn("emergency_stop_active", d)

    def test_to_dict_default_values(self):
        d = ScreenTrust.to_dict()
        self.assertEqual(d["mode"], "ask_each_time")
        self.assertFalse(d["is_trusted"])
        self.assertFalse(d["emergency_stop_active"])

    def test_to_dict_trusted_mode(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        d = ScreenTrust.to_dict()
        self.assertEqual(d["mode"], "trusted_session_read_only")
        self.assertTrue(d["is_trusted"])

    def test_to_dict_emergency_stop(self):
        ScreenTrust.set_mode("trusted_session_read_only")
        EmergencyStop.engage(reason="test")
        d = ScreenTrust.to_dict()
        self.assertTrue(d["emergency_stop_active"])


class TestScreenTrustThreadSafety(unittest.TestCase):
    def setUp(self):
        ScreenTrust.reset_to_ask()
        EmergencyStop.clear()

    def test_concurrent_mode_changes(self):
        barrier = threading.Barrier(5)
        modes = [
            "denied",
            "trusted_session_read_only",
            "trusted_local_read_only",
            "ask_each_time",
            "denied",
        ]

        def worker(mode):
            barrier.wait()
            ScreenTrust.set_mode(mode)

        threads = []
        for mode in modes:
            t = threading.Thread(target=worker, args=(mode,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        current = ScreenTrust.get_mode()
        self.assertIn(current, VALID_MODES)

    def test_concurrent_reads_and_writes(self):
        barrier = threading.Barrier(6)
        results = []
        lock = threading.Lock()

        def writer():
            barrier.wait()
            for mode in VALID_MODES:
                ScreenTrust.set_mode(mode)

        def reader():
            barrier.wait()
            for _ in range(5):
                trusted = ScreenTrust.is_trusted()
                with lock:
                    results.append(trusted)

        threads = []
        for _ in range(3):
            threads.append(threading.Thread(target=writer))
            threads.append(threading.Thread(target=reader))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertTrue(len(results) > 0)


if __name__ == "__main__":
    unittest.main()
