import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import unittest
from datetime import datetime

from engine.control.safety import EmergencyStop
from engine.brain.task_state import (
    AutonomyTask, AutonomyStep, create_task, create_step,
    validate_status, validate_risk, normalize_status, normalize_risk,
    VALID_TASK_STATUSES, VALID_STEP_STATUSES, VALID_RISKS,
)
from engine.brain.self_reflection import (
    summarize_goal, detect_missing_context, should_ask_followup,
    generate_followup_question,
)
from engine.brain.recovery_planner import (
    create_recovery_plan, classify_failure, suggest_next_action,
)
from engine.brain.autonomy_loop import AutonomyLoop


class TestAutonomyTaskContracts(unittest.TestCase):
    def test_task_contract_has_required_keys(self):
        task = AutonomyTask(goal="test")
        d = task.to_dict()
        required = {"task_id", "goal", "status", "steps", "risk_level",
                     "requires_confirmation", "created_at", "updated_at"}
        for key in required:
            self.assertIn(key, d, f"Missing required key: {key}")

    def test_step_contract_has_required_keys(self):
        step = AutonomyStep(description="test step", action="test_action")
        d = step.to_dict()
        required = {"step_id", "description", "action", "status",
                     "risk_level", "requires_confirmation", "verification", "result"}
        for key in required:
            self.assertIn(key, d, f"Missing required key: {key}")

    def test_create_task_returns_valid_task(self):
        task = create_task(goal="test goal", risk_level="MEDIUM")
        self.assertIsInstance(task, AutonomyTask)
        self.assertEqual(task.goal, "test goal")

    def test_create_step_returns_valid_step(self):
        step = create_step(description="test", action="act", risk_level="HIGH")
        self.assertIsInstance(step, AutonomyStep)
        self.assertEqual(step.action, "act")

    def test_invalid_risk_normalized_to_safe(self):
        task = AutonomyTask(goal="test", risk_level="INVALID")
        self.assertEqual(task.risk_level, "SAFE")

    def test_invalid_step_status_normalized(self):
        self.assertFalse(validate_status("invalid_status", VALID_STEP_STATUSES))
        self.assertEqual(normalize_status("invalid_status", VALID_STEP_STATUSES, "pending"), "pending")


class TestAutonomyTaskStatusAndRisk(unittest.TestCase):
    def test_valid_statuses_are_accepted(self):
        for s in VALID_TASK_STATUSES:
            self.assertTrue(validate_status(s, VALID_TASK_STATUSES))

    def test_invalid_status_returns_false(self):
        self.assertFalse(validate_status("invalid_status", VALID_TASK_STATUSES))

    def test_valid_risks_are_accepted(self):
        for r in VALID_RISKS:
            self.assertTrue(validate_risk(r))

    def test_invalid_risk_returns_false(self):
        self.assertFalse(validate_risk("INVALID"))

    def test_high_risk_sets_requires_confirmation(self):
        task = AutonomyTask(goal="test", risk_level="HIGH")
        self.assertTrue(task.requires_confirmation)

    def test_critical_risk_sets_requires_confirmation(self):
        task = AutonomyTask(goal="test", risk_level="CRITICAL")
        self.assertTrue(task.requires_confirmation)

    def test_safe_risk_does_not_require_confirmation(self):
        task = AutonomyTask(goal="test", risk_level="SAFE")
        self.assertFalse(task.requires_confirmation)

    def test_medium_risk_does_not_require_confirmation(self):
        task = AutonomyTask(goal="test", risk_level="MEDIUM")
        self.assertFalse(task.requires_confirmation)

    def test_task_recalculates_risk_from_steps(self):
        task = AutonomyTask(goal="test", risk_level="SAFE")
        step = AutonomyStep(description="high step", action="screen", risk_level="HIGH")
        task.add_step(step)
        self.assertEqual(task.risk_level, "HIGH")
        self.assertTrue(task.requires_confirmation)

    def test_step_high_risk_sets_confirmation(self):
        step = AutonomyStep(description="test", action="screen", risk_level="HIGH")
        self.assertTrue(step.requires_confirmation)


class TestSelfReflection(unittest.TestCase):
    def test_summarize_diagnose_goal(self):
        s = summarize_goal("diagnose Jarvi")
        self.assertIn("Analyze", s)

    def test_summarize_memory_goal(self):
        s = summarize_goal("remember my preferred browser is Chrome")
        self.assertIn("Memory", s)

    def test_summarize_search_goal(self):
        s = summarize_goal("search youtube for AI tools")
        self.assertIn("Search", s)

    def test_detect_missing_context_empty(self):
        missing = detect_missing_context("")
        self.assertTrue(len(missing) > 0)

    def test_detect_missing_context_for_open(self):
        missing = detect_missing_context("open")
        self.assertTrue(len(missing) > 0)

    def test_detect_missing_context_for_remember(self):
        missing = detect_missing_context("remember")
        self.assertIn("what value", " ".join(missing).lower())

    def test_should_ask_followup_for_short_goal(self):
        self.assertTrue(should_ask_followup("hi"))

    def test_should_ask_followup_false_for_complete(self):
        self.assertFalse(should_ask_followup("diagnose Jarvi"))

    def test_generate_followup_question_empty(self):
        q = generate_followup_question("")
        self.assertIn("What", q)

    def test_generate_followup_question_missing(self):
        q = generate_followup_question("open")
        self.assertIn("clarify", q.lower())


class TestRecoveryPlanner(unittest.TestCase):
    def test_classify_transient_failure(self):
        self.assertEqual(classify_failure("connection timeout"), "transient")

    def test_classify_permission_failure(self):
        self.assertEqual(classify_failure("access denied"), "permission")

    def test_classify_invalid_input(self):
        self.assertEqual(classify_failure("invalid request"), "invalid_input")

    def test_classify_unknown_failure(self):
        self.assertEqual(classify_failure("something weird"), "unknown")

    def test_classify_empty_failure(self):
        self.assertEqual(classify_failure(""), "unknown")

    def test_create_recovery_plan_no_step(self):
        plan = create_recovery_plan(None, "timeout")
        self.assertEqual(plan["strategy"], "noop")

    def test_create_recovery_plan_transient(self):
        plan = create_recovery_plan({"action": "test"}, "connection timeout")
        self.assertEqual(plan["strategy"], "transient")
        self.assertGreater(len(plan["steps"]), 0)

    def test_suggest_next_action_transient(self):
        suggestion = suggest_next_action("timeout")
        self.assertIn("Retry", suggestion)

    def test_suggest_next_action_permission(self):
        suggestion = suggest_next_action("denied")
        self.assertIn("permission", suggestion.lower())


class TestAutonomyLoopSafeGoals(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_diagnose_jarvi_planned_safe(self):
        task = self.loop.plan_task("diagnose Jarvi")
        self.assertEqual(task.risk_level, "SAFE")
        self.assertGreater(len(task.steps), 0)

    def test_memory_preference_planned_medium(self):
        task = self.loop.plan_task("remember my preferred browser is Chrome")
        self.assertEqual(task.risk_level, "MEDIUM")

    def test_what_do_you_remember_planned_safe(self):
        task = self.loop.plan_task("what do you remember about me")
        self.assertEqual(task.risk_level, "SAFE")

    def test_check_project_planned_safe(self):
        task = self.loop.plan_task("check this project")
        self.assertEqual(task.risk_level, "SAFE")


class TestAutonomyLoopMediumGoals(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_open_chrome_planned_medium(self):
        task = self.loop.plan_task("open chrome")
        self.assertEqual(task.risk_level, "MEDIUM")
        self.assertFalse(task.requires_confirmation)

    def test_search_youtube_planned_medium(self):
        task = self.loop.plan_task("search youtube for AI tools")
        self.assertEqual(task.risk_level, "MEDIUM")
        self.assertFalse(task.requires_confirmation)

    def test_remember_preference_medium(self):
        task = self.loop.plan_task("remember my preferred browser is Chrome")
        self.assertFalse(task.requires_confirmation)


class TestAutonomyLoopHighGoals(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_screen_dekho_planned_high(self):
        task = self.loop.plan_task("screen dekho")
        self.assertEqual(task.risk_level, "HIGH")
        self.assertTrue(task.requires_confirmation)

    def test_screenshot_planned_high(self):
        task = self.loop.plan_task("take a screenshot")
        self.assertEqual(task.risk_level, "HIGH")
        self.assertTrue(task.requires_confirmation)

    def test_evaluate_screen_step_requires_confirmation(self):
        task = self.loop.plan_task("screen dekho")
        evaluated = self.loop.evaluate_task(task)
        for s in evaluated["steps"]:
            if s["action"] == "screen_capture":
                self.assertTrue(s["requires_confirmation"])


class TestAutonomyLoopCriticalBlocked(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_delete_files_blocked(self):
        task = self.loop.plan_task("delete files")
        self.assertEqual(task.risk_level, "CRITICAL")
        evaluated = self.loop.evaluate_task(task)
        for s in evaluated["steps"]:
            self.assertEqual(s["status"], "blocked")

    def test_run_shell_blocked(self):
        task = self.loop.plan_task("run shell command")
        self.assertEqual(task.risk_level, "CRITICAL")
        evaluated = self.loop.evaluate_task(task)
        for s in evaluated["steps"]:
            self.assertEqual(s["status"], "blocked")

    def test_send_automatically_blocked(self):
        task = self.loop.plan_task("send message automatically")
        evaluated = self.loop.evaluate_task(task)
        has_blocked = any(s["status"] == "blocked" for s in evaluated["steps"])
        self.assertTrue(has_blocked)

    def test_install_software_blocked(self):
        task = self.loop.plan_task("install software")
        self.assertEqual(task.risk_level, "CRITICAL")
        evaluated = self.loop.evaluate_task(task)
        for s in evaluated["steps"]:
            self.assertEqual(s["status"], "blocked")


class TestAutonomyLoopEmergencyStop(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def tearDown(self):
        EmergencyStop.clear()

    def test_emergency_stop_blocks_evaluation(self):
        task = self.loop.plan_task("open chrome")
        EmergencyStop.engage("User requested stop")
        evaluated = self.loop.evaluate_task(task)
        self.assertEqual(evaluated["status"], "blocked")
        for s in evaluated["steps"]:
            self.assertEqual(s["status"], "blocked")

    def test_emergency_stop_detected(self):
        self.assertFalse(self.loop.block_if_emergency_stop())
        EmergencyStop.engage("test")
        self.assertTrue(self.loop.block_if_emergency_stop())

    def test_stop_everything_planned_safe(self):
        task = self.loop.plan_task("stop everything")
        self.assertEqual(task.risk_level, "SAFE")

    def test_stop_everything_contains_emergency_step(self):
        task = self.loop.plan_task("stop everything")
        actions = [s.action for s in task.steps]
        self.assertIn("emergency_stop", actions)


class TestAutonomyLoopStepManagement(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_mark_step_result_completed(self):
        task = self.loop.plan_task("diagnose Jarvi")
        step_id = task.steps[0].step_id
        result = self.loop.mark_step_result(task, step_id, True, {"output": "ok"})
        self.assertEqual(result["status"], "completed")

    def test_mark_step_result_failed(self):
        task = self.loop.plan_task("diagnose Jarvi")
        step_id = task.steps[0].step_id
        result = self.loop.mark_step_result(task, step_id, False, {"error": "error"})
        self.assertEqual(result["status"], "failed")

    def test_mark_step_invalid_id(self):
        task = self.loop.plan_task("diagnose Jarvi")
        result = self.loop.mark_step_result(task, "invalid_id", True)
        self.assertIn("error", result)

    def test_recover_from_failure_creates_plan(self):
        task = self.loop.plan_task("open chrome")
        step_id = task.steps[0].step_id
        self.loop.mark_step_result(task, step_id, False, {"error": "connection timeout"})
        recovery = self.loop.recover_from_failure(task, step_id, "connection timeout")
        self.assertIn("recovery", recovery)
        self.assertIn("task", recovery)
        self.assertGreater(len(recovery["recovery"]["steps"]), 0)

    def test_recover_from_failure_adds_recovery_steps_to_task(self):
        task = self.loop.plan_task("open chrome")
        step_id = task.steps[0].step_id
        before = len(task.steps)
        self.loop.recover_from_failure(task, step_id, "timeout error")
        self.assertGreater(len(task.steps), before)


class TestAutonomyLoopSummarize(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_summarize_task_returns_string(self):
        task = self.loop.plan_task("diagnose Jarvi")
        summary = self.loop.summarize_task(task)
        self.assertIsInstance(summary, str)
        self.assertIn("diagnose", summary.lower())

    def test_summarize_invalid_task_returns_error(self):
        summary = self.loop.summarize_task(None)
        self.assertIsInstance(summary, str)

    def test_summary_includes_goal_and_status(self):
        task = self.loop.plan_task("open chrome")
        summary = self.loop.summarize_task(task)
        self.assertIn("Task:", summary)
        self.assertIn("Status:", summary)
        self.assertIn("Steps", summary)


class TestAutonomyLoopModelOutputSafety(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_plan_task_does_not_execute(self):
        task = self.loop.plan_task("delete files")
        self.assertEqual(task.status, "planned")
        self.assertEqual(task.risk_level, "CRITICAL")

    def test_evaluate_task_does_not_execute(self):
        task = self.loop.plan_task("open chrome")
        evaluated = self.loop.evaluate_task(task)
        self.assertIn("status", evaluated)

    def test_plan_returns_task_not_raw_dict_action(self):
        task = self.loop.plan_task("open chrome")
        self.assertIsInstance(task, AutonomyTask)
        self.assertNotIn("executed", task.to_dict())


class TestAutonomyLoopEmptyAndInvalid(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_empty_goal_blocked(self):
        task = self.loop.plan_task("")
        self.assertEqual(task.status, "blocked")

    def test_none_goal_blocked(self):
        task = self.loop.plan_task(None)
        self.assertEqual(task.status, "blocked")

    def test_evaluate_non_task_returns_error(self):
        result = self.loop.evaluate_task("not a task")
        self.assertIn("error", result)
        self.assertTrue(result["blocked"])

    def test_recover_non_task_returns_error(self):
        result = self.loop.recover_from_failure("not a task", "id", "reason")
        self.assertIn("error", result)


class TestAutonomyLoopForgetPreference(unittest.TestCase):
    def setUp(self):
        EmergencyStop.clear()
        self.loop = AutonomyLoop()

    def test_forget_preference_planned_medium(self):
        task = self.loop.plan_task("forget my preferred browser")
        self.assertEqual(task.risk_level, "MEDIUM")

    def test_forget_step_has_key(self):
        task = self.loop.plan_task("forget my preferred browser")
        if len(task.steps) > 0:
            step = task.steps[0]
            if step.result and "key" in step.result:
                self.assertIn("preferred", step.result.get("key", ""))


class TestAutonomyLoopExistingTestsStillPass(unittest.TestCase):
    def test_model_router_importable(self):
        import engine.brain.model_router as mr
        self.assertTrue(hasattr(mr, "route"))

    def test_model_client_importable(self):
        import engine.brain.model_client as mc
        self.assertTrue(hasattr(mc, "MockModelClient"))


if __name__ == "__main__":
    unittest.main()
