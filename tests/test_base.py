import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from engine.control.base import ControlResult, ControlFunction


class TestControlResult(unittest.TestCase):
    def test_success_defaults(self):
        r = ControlResult.success()
        self.assertTrue(r.ok)
        self.assertEqual(r.message, "")
        self.assertEqual(r.data, {})
        self.assertIsNone(r.error)

    def test_success_with_message(self):
        r = ControlResult.success(message="All good")
        self.assertTrue(r.ok)
        self.assertEqual(r.message, "All good")

    def test_success_with_data(self):
        r = ControlResult.success(data={"key": "value"})
        self.assertEqual(r.data["key"], "value")

    def test_failure_defaults(self):
        r = ControlResult.failure()
        self.assertFalse(r.ok)
        self.assertEqual(r.message, "Action failed.")
        self.assertEqual(r.error["code"], "")

    def test_failure_with_details(self):
        r = ControlResult.failure(message="Oops", code="ERR001", error_message="Details")
        self.assertFalse(r.ok)
        self.assertEqual(r.error["code"], "ERR001")
        self.assertEqual(r.error["message"], "Details")

    def test_to_dict_success(self):
        r = ControlResult.success(message="OK", data={"x": 1})
        d = r.to_dict()
        self.assertTrue(d["ok"])
        self.assertEqual(d["message"], "OK")
        self.assertEqual(d["data"]["x"], 1)

    def test_to_dict_failure(self):
        r = ControlResult.failure(code="ERR", error_message="msg")
        d = r.to_dict()
        self.assertFalse(d["ok"])
        self.assertEqual(d["error"]["code"], "ERR")


class TestControlFunction(unittest.TestCase):
    def test_create(self):
        def handler(app_name=None, **_):
            return ControlResult.success(message=f"Opened {app_name}")
        cf = ControlFunction(
            name="test_action",
            intent="test action",
            description="A test action",
            risk_level="SAFE",
            handler=handler
        )
        self.assertEqual(cf.name, "test_action")
        self.assertEqual(cf.risk_level, "SAFE")

    def test_call_handler(self):
        def handler(app_name=None, **_):
            return ControlResult.success(data={"app": app_name})
        cf = ControlFunction(name="test", intent="test", description="test", handler=handler)
        r = cf(app_name="chrome")
        self.assertTrue(r.ok)
        self.assertEqual(r.data["app"], "chrome")

    def test_no_handler(self):
        cf = ControlFunction(name="test", intent="test", description="test")
        r = cf()
        self.assertFalse(r.ok)
        self.assertEqual(r.error["code"], "NO_HANDLER")

    def test_to_contract(self):
        cf = ControlFunction(
            name="test", intent="test intent",
            description="desc", risk_level="HIGH",
            requires_confirmation=True
        )
        c = cf.to_contract()
        self.assertEqual(c["name"], "test")
        self.assertEqual(c["risk_level"], "HIGH")
        self.assertTrue(c["requires_confirmation"])


if __name__ == "__main__":
    unittest.main()
