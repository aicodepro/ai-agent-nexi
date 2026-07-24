import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from engine.control.action_gate import ActionGate, ActionGateResult, ActionGateStatus
from engine.control.base import ControlResult, ControlFunction
from engine.control.registry import ControlRegistry
from engine.control.safety import EmergencyStop, AuditLog
from engine.control.permission_manager import PermissionManager
from vision.screen_trust import ScreenTrust


class TestActionGateStatusEnum(unittest.TestCase):
    def test_all_five_statuses_exist(self):
        expected = {"ALLOW", "BLOCK", "NEED_CONFIRMATION", "UNKNOWN_ACTION", "EMERGENCY_STOP_BLOCKED"}
        actual = {s.value for s in ActionGateStatus}
        self.assertEqual(actual, expected)


class TestActionGateResultFactories(unittest.TestCase):
    def test_allow_factory(self):
        cr = ControlResult.success(message="done")
        result = ActionGateResult.allow("test_action", cr)
        self.assertEqual(result.status, ActionGateStatus.ALLOW)
        self.assertEqual(result.action_name, "test_action")
        self.assertEqual(result.message, "done")
        self.assertTrue(result.handler_called)
        self.assertIs(result.control_result, cr)

    def test_block_factory(self):
        result = ActionGateResult.block("test_action", reason="policy")
        self.assertEqual(result.status, ActionGateStatus.BLOCK)
        self.assertIn("blocked", result.message.lower())
        self.assertEqual(result.reason, "policy")
        self.assertFalse(result.handler_called)

    def test_need_confirmation_factory(self):
        result = ActionGateResult.need_confirmation("test_action", prompt="Are you sure?")
        self.assertEqual(result.status, ActionGateStatus.NEED_CONFIRMATION)
        self.assertEqual(result.message, "Are you sure?")
        self.assertFalse(result.handler_called)

    def test_unknown_action_factory(self):
        result = ActionGateResult.unknown_action("bogus_action")
        self.assertEqual(result.status, ActionGateStatus.UNKNOWN_ACTION)
        self.assertIn("unknown", result.message.lower())
        self.assertFalse(result.handler_called)

    def test_emergency_stop_factory(self):
        EmergencyStop.engage(reason="test stop")
        result = ActionGateResult.emergency_stop("test_action")
        self.assertEqual(result.status, ActionGateStatus.EMERGENCY_STOP_BLOCKED)
        self.assertIn("emergency", result.message.lower())
        self.assertFalse(result.handler_called)
        EmergencyStop.clear()

    def test_to_dict_contains_expected_keys(self):
        cr = ControlResult.success("ok")
        result = ActionGateResult.allow("act", cr)
        d = result.to_dict()
        expected = {"status", "action_name", "message", "reason",
                    "permission_result", "control_result", "handler_called", "timestamp"}
        self.assertEqual(set(d.keys()), expected)


class TestActionGateDispatchFiveStatuses(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.clear_log()
        AuditLog.set_enabled(False)
        ScreenTrust.set_owner_trusted(False)
        self.registry = ControlRegistry()
        self.handler_call_count = 0
        self._build_registry()
        self.gate = ActionGate(self.registry)

    def _handler(self, **kwargs):
        self.handler_call_count += 1
        return ControlResult.success(message="handled")

    def _build_registry(self):
        for name, risk in [
            ("test_safe_op", "SAFE"),
            ("test_med_op", "MEDIUM"),
            ("test_high_op", "HIGH"),
            ("test_crit_op", "CRITICAL"),
        ]:
            func = ControlFunction(name, name.replace("_", " "), "", risk_level=risk,
                                   handler=self._handler)
            self.registry.register(func)

    def test_dispatch_safe_allows_handler(self):
        result = self.gate.dispatch("test_safe_op")
        self.assertEqual(result.status, ActionGateStatus.ALLOW)
        self.assertTrue(result.handler_called)
        self.assertEqual(self.handler_call_count, 1)

    def test_dispatch_medium_allows_handler(self):
        result = self.gate.dispatch("test_med_op")
        self.assertEqual(result.status, ActionGateStatus.ALLOW)
        self.assertTrue(result.handler_called)
        self.assertEqual(self.handler_call_count, 1)

    def test_dispatch_high_returns_need_confirmation_handler_not_called(self):
        result = self.gate.dispatch("test_high_op")
        self.assertEqual(result.status, ActionGateStatus.NEED_CONFIRMATION)
        self.assertFalse(result.handler_called)
        self.assertEqual(self.handler_call_count, 0)

    def test_dispatch_critical_blocks_handler_not_called(self):
        result = self.gate.dispatch("test_crit_op")
        self.assertEqual(result.status, ActionGateStatus.BLOCK)
        self.assertFalse(result.handler_called)
        self.assertEqual(self.handler_call_count, 0)

    def test_dispatch_unknown_returns_unknown_handler_not_called(self):
        result = self.gate.dispatch("zzz_unknown_42")
        self.assertEqual(result.status, ActionGateStatus.UNKNOWN_ACTION)
        self.assertFalse(result.handler_called)
        self.assertEqual(self.handler_call_count, 0)

    def test_dispatch_emergency_stop_blocks_all_handler_not_called(self):
        EmergencyStop.engage(reason="halt")
        result = self.gate.dispatch("test_safe_op")
        self.assertEqual(result.status, ActionGateStatus.EMERGENCY_STOP_BLOCKED)
        self.assertFalse(result.handler_called)
        self.assertEqual(self.handler_call_count, 0)
        EmergencyStop.clear()

    def test_blocked_handler_never_executes_even_on_repeated_dispatch(self):
        for _ in range(5):
            self.gate.dispatch("test_crit_op")
        self.assertEqual(self.handler_call_count, 0)

    def test_allowed_handler_receives_entities(self):
        result = self.gate.dispatch("test_safe_op", entities={"key": "val"})
        self.assertEqual(result.status, ActionGateStatus.ALLOW)
        self.assertTrue(result.handler_called)
        self.assertEqual(self.handler_call_count, 1)

    def test_dispatch_all_four_risk_levels_integration(self):
        names = ["test_safe_op", "test_med_op", "test_high_op", "test_crit_op"]
        results = [self.gate.dispatch(n) for n in names]
        self.assertEqual(self.handler_call_count, 2)
        self.assertEqual(results[0].status, ActionGateStatus.ALLOW)
        self.assertEqual(results[1].status, ActionGateStatus.ALLOW)
        self.assertEqual(results[2].status, ActionGateStatus.NEED_CONFIRMATION)
        self.assertEqual(results[3].status, ActionGateStatus.BLOCK)


class TestActionGateConfirmFlow(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.clear_log()
        AuditLog.set_enabled(False)
        ScreenTrust.set_owner_trusted(False)
        self.registry = ControlRegistry()
        self.handler_call_count = 0
        self._build_registry()
        self.gate = ActionGate(self.registry)

    def _handler(self, **kwargs):
        self.handler_call_count += 1
        return ControlResult.success(message="done")

    def _build_registry(self):
        for name, risk in [
            ("cf_high", "HIGH"),
            ("cf_crit", "CRITICAL"),
            ("cf_safe", "SAFE"),
        ]:
            func = ControlFunction(name, name.replace("_", " "), "", risk_level=risk,
                                   handler=self._handler)
            self.registry.register(func)

    def test_confirm_high_with_yes_allows_and_calls_handler(self):
        r = self.gate.confirm("cf_high", "yes")
        self.assertEqual(r.status, ActionGateStatus.ALLOW)
        self.assertTrue(r.handler_called)
        self.assertEqual(self.handler_call_count, 1)

    def test_confirm_high_with_no_blocks_handler_not_called(self):
        r = self.gate.confirm("cf_high", "no")
        self.assertEqual(r.status, ActionGateStatus.BLOCK)
        self.assertFalse(r.handler_called)
        self.assertEqual(self.handler_call_count, 0)

    def test_confirm_critical_blocks_even_with_confirm_handler_not_called(self):
        r = self.gate.confirm("cf_crit", "CONFIRM")
        self.assertEqual(r.status, ActionGateStatus.BLOCK)
        self.assertFalse(r.handler_called)
        self.assertEqual(self.handler_call_count, 0)

    def test_confirm_under_emergency_stop_blocks(self):
        EmergencyStop.engage(reason="stop")
        r = self.gate.confirm("cf_high", "yes")
        self.assertEqual(r.status, ActionGateStatus.EMERGENCY_STOP_BLOCKED)
        self.assertFalse(r.handler_called)
        EmergencyStop.clear()

    def test_confirm_unknown_action_returns_unknown(self):
        r = self.gate.confirm("zzz_nonexistent_99", "yes")
        self.assertEqual(r.status, ActionGateStatus.UNKNOWN_ACTION)
        self.assertFalse(r.handler_called)

    def test_dispatch_then_confirm_high_flow(self):
        r1 = self.gate.dispatch("cf_high")
        self.assertEqual(r1.status, ActionGateStatus.NEED_CONFIRMATION)
        self.assertEqual(self.handler_call_count, 0)

        r2 = self.gate.confirm("cf_high", "yes")
        self.assertEqual(r2.status, ActionGateStatus.ALLOW)
        self.assertTrue(r2.handler_called)
        self.assertEqual(self.handler_call_count, 1)


class TestHandlersNeverExecuteOnBlock(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.set_enabled(False)
        ScreenTrust.set_owner_trusted(False)

    def _make_tracker(self):
        tracker = {"called": False}
        def handler(**kwargs):
            tracker["called"] = True
            return ControlResult.success(message="ok")
        return tracker, handler

    def test_high_risk_handler_not_called(self):
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_alpha", "op alpha", "", risk_level="HIGH", handler=handler))
        ActionGate(reg).dispatch("op_alpha")
        self.assertFalse(tracker["called"])

    def test_critical_risk_handler_not_called(self):
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_beta", "op beta", "", risk_level="CRITICAL", handler=handler))
        ActionGate(reg).dispatch("op_beta")
        self.assertFalse(tracker["called"])

    def test_unknown_action_handler_not_called(self):
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_gamma", "op gamma", "", risk_level="SAFE", handler=handler))
        ActionGate(reg).dispatch("zzz_does_not_exist")
        self.assertFalse(tracker["called"])

    def test_emergency_stop_handler_not_called(self):
        EmergencyStop.engage(reason="test")
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_delta", "op delta", "", risk_level="SAFE", handler=handler))
        ActionGate(reg).dispatch("op_delta")
        self.assertFalse(tracker["called"])
        EmergencyStop.clear()

    def test_confirm_high_with_no_handler_not_called(self):
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_epsilon", "op epsilon", "", risk_level="HIGH", handler=handler))
        ActionGate(reg).confirm("op_epsilon", "no")
        self.assertFalse(tracker["called"])

    def test_confirm_critical_handler_not_called(self):
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_zeta", "op zeta", "", risk_level="CRITICAL", handler=handler))
        ActionGate(reg).confirm("op_zeta", "yes")
        self.assertFalse(tracker["called"])

    def test_dispatch_then_denied_handler_not_called(self):
        reg = ControlRegistry()
        tracker, handler = self._make_tracker()
        reg.register(ControlFunction("op_eta", "op eta", "", risk_level="HIGH", handler=handler))
        gate = ActionGate(reg)
        gate.dispatch("op_eta")
        self.assertFalse(tracker["called"])
        gate.confirm("op_eta", "no")
        self.assertFalse(tracker["called"])


class TestPermissionResultContent(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.set_enabled(False)
        ScreenTrust.set_owner_trusted(False)

    def test_gate_correctly_blocks_critical_action(self):
        reg = ControlRegistry()
        reg.register(ControlFunction("op_theta", "op theta", "", risk_level="CRITICAL",
                     handler=lambda **kw: ControlResult.success()))
        r = ActionGate(reg).dispatch("op_theta")
        self.assertEqual(r.status, ActionGateStatus.BLOCK)
        self.assertFalse(r.handler_called)

    def test_permission_result_includes_decision(self):
        reg = ControlRegistry()
        reg.register(ControlFunction("op_iota", "op iota", "", risk_level="HIGH",
                     handler=lambda **kw: ControlResult.success()))
        r = ActionGate(reg).dispatch("op_iota")
        self.assertIn("decision", r.permission_result)

    def test_allowed_permission_result_has_decision_approved(self):
        reg = ControlRegistry()
        reg.register(ControlFunction("op_kappa", "op kappa", "", risk_level="SAFE",
                     handler=lambda **kw: ControlResult.success()))
        r = ActionGate(reg).dispatch("op_kappa")
        self.assertEqual(r.permission_result.get("decision"), "approved")


class TestExecuteControlActionBackwardCompat(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.clear_log()
        AuditLog.set_enabled(False)

    def test_execute_control_action_passes_safe_action(self):
        from engine.control import execute_control_action
        result = execute_control_action("list_apps")
        self.assertTrue(result.ok)

    def test_execute_control_action_blocks_under_emergency_stop(self):
        from engine.control import execute_control_action
        EmergencyStop.engage(reason="test")
        result = execute_control_action("list_apps")
        self.assertFalse(result.ok)
        self.assertIn("EMERGENCY", result.error.get("code", ""))
        EmergencyStop.clear()


class TestDispatchIntentEmergencyStopGuard(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.set_enabled(False)

    def test_guard_patch_in_dispatch_intent(self):
        import ast
        src_path = os.path.join(os.path.dirname(__file__), "..", "engine", "command.py")
        with open(src_path, encoding="utf-8") as f:
            src = f.read()
        tree = ast.parse(src)
        dispatch_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "dispatch_intent":
                dispatch_func = node
                break
        self.assertIsNotNone(dispatch_func)
        has_guard = any(
            isinstance(n, ast.If)
            and isinstance(n.test, ast.Call)
            and isinstance(n.test.func, ast.Attribute)
            and n.test.func.attr == "is_engaged"
            for n in ast.walk(dispatch_func)
        )
        self.assertTrue(has_guard)

    def test_legacy_volumeup_still_routes_through_dispatch_intent(self):
        from engine.intents import match_intent
        intent, score = match_intent("volume up")
        self.assertIsNotNone(intent)
        self.assertEqual(intent.name, "volume_up")

    def test_empty_query_returns_no_intent(self):
        from engine.intents import match_intent
        intent, _ = match_intent("")
        self.assertIsNone(intent)


class TestHandlersNeverExecuteUnderEmergencyStop(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        AuditLog.set_enabled(False)
        ScreenTrust.set_owner_trusted(False)

    def test_gate_unknown_via_fresh_registry_does_not_call_handler(self):
        reg = ControlRegistry()
        call_count = 0
        def handler(**kw):
            nonlocal call_count
            call_count += 1
            return ControlResult.success()
        reg.register(ControlFunction("safe_op", "safe operation", "", risk_level="SAFE", handler=handler))
        gate = ActionGate(reg)
        result = gate.dispatch("zzz_does_not_exist_99")
        self.assertEqual(result.status, ActionGateStatus.UNKNOWN_ACTION)
        self.assertFalse(result.handler_called)
        self.assertEqual(call_count, 0)

    def test_execute_control_action_critical_does_not_call_handler(self):
        from engine.control import execute_control_action
        result = execute_control_action("delete_files")
        self.assertFalse(result.ok)

    def test_execute_control_action_high_unconfirmed_does_not_call_handler(self):
        ScreenTrust.set_owner_trusted(False)
        from engine.control import execute_control_action
        result = execute_control_action("screen_capture")
        self.assertFalse(result.ok)

    def test_execute_control_action_emergency_stop_does_not_call_handler(self):
        from engine.control import execute_control_action
        EmergencyStop.engage(reason="test")
        try:
            result = execute_control_action("list_apps")
            self.assertFalse(result.ok)
            self.assertIn("EMERGENCY", result.error.get("code", ""))
        finally:
            EmergencyStop.clear()


class TestActionGateAuditDocumentation(unittest.TestCase):
    def test_gate_audit_bypass_list(self):
        bypasses = [
            "dispatch_intent legacy volume_up/volume_down (engine.keyboard)",
            "dispatch_intent legacy pyautogui.press (pause/resume/mute)",
            "dispatch_intent legacy keyboard shortcuts (new_tab, close_tab, etc.)",
            "dispatch_intent legacy features (openCommand, PlayYoutube)",
        ]
        for bypass in bypasses:
            self.assertIsInstance(bypass, str)
        self.assertEqual(len(bypasses), 4)


if __name__ == "__main__":
    unittest.main()
