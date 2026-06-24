import re
from datetime import datetime

from src.orin.control.safety import EmergencyStop, SandboxPolicy
from src.orin.brain.task_state import (
    AutonomyTask, AutonomyStep, create_step,
    VALID_RISKS, VALID_TASK_STATUSES, VALID_STEP_STATUSES,
    validate_risk, validate_status,
)
from src.orin.brain.self_reflection import (
    summarize_goal, should_ask_followup, generate_followup_question,
)
from src.orin.brain.recovery_planner import (
    create_recovery_plan, classify_failure, suggest_next_action,
)

_GOAL_RISK_RULES = [
    ("CRITICAL", [
        r"\bdelete\b", r"\bremove\b", r"\brun\s+(shell|command|cmd|terminal)\b",
        r"\binstall\b", r"\bchange\s+system\s+setting",
        r"\bpassword\b", r"\bcookie\b", r"\bapi[_-]?key\b",
        r"\bsend\s+\w+\s+automatically\b", r"\bexec(?:ute)?\b",
        r"\bsystem\s+setting", r"\bterminal\b", r"\bpowershell\b",
    ]),
    ("HIGH", [
        r"\bscreen\b", r"\bscreenshot\b", r"\bdekho\b", r"\bdikhao\b",
        r"\bclipboard\b", r"\bwhatsapp\b", r"\bdraft\b", r"\bcamera\b",
        r"\bemail\b(?!.*(?:read|check))",
        r"\bfile\s+read\b", r"\barbitrary\s+file\b",
    ]),
    ("MEDIUM", [
        r"\bopen\b", r"\blaunch\b", r"\bstart\b", r"\bclose\b",
        r"\bsearch\b", r"\bbrowse\b", r"\byoutube\b", r"\bgoogle\b",
        r"\bremember\b", r"\bforget\b",
        r"\bpreference\b", r"\bprefer\b",
    ]),
]

_KNOWN_GOAL_PATTERNS = {
    "diagnose_jarvi": [
        r"\bdiagnose\s+(jarvi|me|system)\b", r"\brun\s+diagnostics\b",
        r"\bcheck\s+(jarvi|health)\b",
    ],
    "check_project": [
        r"\bcheck\s+(this\s+)?project\b", r"\bproject\s+status\b",
    ],
    "what_do_you_remember": [
        r"\bwhat\s+do\s+you\s+remember\b", r"\bshow\s+(memories|preferences)\b",
        r"\btell\s+me\s+about\s+me\b",
    ],
    "stop_everything": [
        r"\bstop\s+everything\b", r"\bemergency\s+stop\b",
        r"\bfreeze\s+everything\b",
    ],
}

_BLOCKED_ACTIONS = SandboxPolicy.BLOCKED_ACTIONS.copy()


class AutonomyLoop:
    def plan_task(self, goal):
        if not goal or not goal.strip():
            task = AutonomyTask(goal="", risk_level="SAFE")
            task.update_status("blocked")
            return task
        g = goal.strip()
        risk = self._classify_goal_risk(g)
        task = AutonomyTask(goal=g, risk_level=risk)
        steps = self._build_steps(g, risk)
        for s in steps:
            task.add_step(s)
        return task

    def evaluate_task(self, task):
        if not isinstance(task, AutonomyTask):
            return {"error": "Expected AutonomyTask", "blocked": True}
        if EmergencyStop.is_engaged():
            task.update_status("blocked")
            for s in task.steps:
                s.status = "blocked"
            return task.to_dict()
        for s in task.steps:
            allowed, reason = SandboxPolicy.is_allowed(s.risk_level, s.action)
            if not allowed:
                s.status = "blocked"
                s.result = {"block_reason": reason, "blocked": True}
            elif s.risk_level == "CRITICAL":
                s.status = "blocked"
                s.result = {"block_reason": "CRITICAL risk level blocked by policy", "blocked": True}
            elif s.risk_level == "HIGH":
                s.requires_confirmation = True
                s.result = {"requires_confirmation": True}
            elif s.risk_level in ("SAFE", "MEDIUM"):
                s.requires_confirmation = False
        task._recalculate_risk()
        return task.to_dict()

    def mark_step_result(self, task, step_id, ok, result=None):
        if not isinstance(task, AutonomyTask):
            return {"error": "Expected AutonomyTask"}
        target = None
        for s in task.steps:
            if s.step_id == step_id:
                target = s
                break
        if target is None:
            return {"error": f"Step {step_id} not found"}
        target.status = "completed" if ok else "failed"
        target.result = result or {}
        self._update_task_status(task)
        return task.to_dict()

    def recover_from_failure(self, task, failed_step_id, reason):
        if not isinstance(task, AutonomyTask):
            return {"error": "Expected AutonomyTask"}
        target = None
        for s in task.steps:
            if s.step_id == failed_step_id:
                target = s
                break
        if target is None:
            recovery = create_recovery_plan(None, reason)
            return {
                "task": task.to_dict(),
                "recovery": recovery,
            }
        plan = create_recovery_plan(target.to_dict(), reason)
        for rs in plan["steps"]:
            step = AutonomyStep(
                description=rs.get("description", ""),
                action=rs.get("action", ""),
                risk_level="SAFE",
            )
            task.add_step(step)
        task.update_status("running")
        return {
            "task": task.to_dict(),
            "recovery": plan,
        }

    def summarize_task(self, task):
        if not isinstance(task, AutonomyTask):
            return "Invalid task"
        d = task.to_dict()
        step_summaries = []
        for s in d["steps"]:
            step_summaries.append(f"  [{s['status']}] {s['description']} ({s['risk_level']})")
        summary = f"Task: {d['goal']}\n"
        summary += f"Status: {d['status']} | Risk: {d['risk_level']}\n"
        summary += f"Steps ({len(d['steps'])}):\n"
        summary += "\n".join(step_summaries)
        return summary

    def block_if_emergency_stop(self):
        if EmergencyStop.is_engaged():
            return True
        return False

    def _classify_goal_risk(self, goal):
        g = goal.strip().lower()
        for risk, patterns in _GOAL_RISK_RULES:
            for pat in patterns:
                if re.search(pat, g):
                    return risk
        return "SAFE"

    def _build_steps(self, goal, risk):
        g = goal.strip().lower()
        matched = self._match_known_goal(g)
        if matched:
            return self._steps_for_known(matched, goal)
        if "open" in g or "launch" in g:
            return self._steps_for_open(g)
        if "search" in g:
            return self._steps_for_search(g)
        if "remember" in g:
            return self._steps_for_remember(g)
        if "forget" in g:
            return self._steps_for_forget(g)
        if "screen" in g or "dekho" in g or "dikhao" in g:
            return self._steps_for_screen(goal)
        if "delete" in g or "remove" in g:
            return [create_step(
                description=f"Destructive action: {goal}",
                action="delete_files",
                risk_level="CRITICAL",
            )]
        if "send" in g:
            return self._steps_for_send(g)
        if "stop" in g or "freeze" in g:
            return [create_step(
                description="Engage emergency stop",
                action="emergency_stop",
                risk_level="SAFE",
            )]
        return [create_step(
            description=f"Unknown goal: {goal}",
            action="unknown",
            risk_level=risk,
        )]

    def _match_known_goal(self, goal_lower):
        for name, patterns in _KNOWN_GOAL_PATTERNS.items():
            for pat in patterns:
                if re.search(pat, goal_lower):
                    return name
        return None

    def _steps_for_known(self, name, goal):
        mapping = {
            "diagnose_jarvi": [
                create_step("Run Nexi diagnostics", "run_diagnostics", "SAFE"),
            ],
            "check_project": [
                create_step("Check project status", "check_project_status", "SAFE"),
            ],
            "what_do_you_remember": [
                create_step("Retrieve stored preferences", "retrieve_preferences", "SAFE"),
            ],
            "stop_everything": [
                create_step("Engage emergency stop", "emergency_stop", "SAFE"),
            ],
        }
        return mapping.get(name, [
            create_step(f"Process: {goal}", "unknown", "SAFE"),
        ])

    def _steps_for_open(self, g):
        app_names = ["chrome", "browser", "youtube", "firefox", "edge",
                     "notepad", "calculator", "explorer", "terminal", "cmd"]
        found = None
        for a in app_names:
            if a in g:
                found = a
                break
        if found:
            return [create_step(
                description=f"Open {found}",
                action="open_application",
                risk_level="MEDIUM",
                verification=f"Verify {found} opened",
                result={"app_name": found},
            )]
        if "folder" in g or "file" in g:
            return [create_step(
                description=f"Open file/folder: {g}",
                action="open_file",
                risk_level="MEDIUM",
            )]
        return [create_step(
            description=f"Open: {g}",
            action="open_application",
            risk_level="MEDIUM",
        )]

    def _steps_for_search(self, g):
        query = ""
        for prefix in ["search youtube for ", "search google for ", "search for "]:
            if prefix in g:
                query = g.split(prefix, 1)[-1].strip()
                break
        if not query and " for " in g:
            query = g.split(" for ", 1)[-1].strip()
        is_youtube = "youtube" in g or "yt" in g.replace(" ", "")
        platform = "youtube" if is_youtube else "google"
        if query:
            return [create_step(
                description=f"Search {platform} for: {query}",
                action="web_search",
                risk_level="MEDIUM",
                verification=f"Verify search results for {query}",
                result={"query": query, "platform": platform},
            )]
        return [create_step(
            description=f"Search {platform}",
            action="web_search",
            risk_level="MEDIUM",
        )]

    def _steps_for_remember(self, g):
        key, value = self._extract_key_value(g)
        if key and value:
            return [create_step(
                description=f"Remember: {key} = {value}",
                action="remember_preference",
                risk_level="MEDIUM",
                result={"key": key, "value": value},
            )]
        if key and not value:
            return [create_step(
                description=f"What value to remember for {key}?",
                action="request_input",
                risk_level="SAFE",
                result={"missing": "value", "key": key},
            )]
        return [create_step(
            description="Remember a preference",
            action="remember_preference",
            risk_level="MEDIUM",
        )]

    def _steps_for_forget(self, g):
        key = self._extract_key(g)
        if key:
            return [create_step(
                description=f"Forget: {key}",
                action="forget_preference",
                risk_level="MEDIUM",
                result={"key": key},
            )]
        return [create_step(
            description="Specify which preference to forget",
            action="request_input",
            risk_level="SAFE",
            result={"missing": "key"},
        )]

    def _steps_for_screen(self, goal):
        return [create_step(
            description=f"Capture and analyze screen: {goal}",
            action="screen_capture",
            risk_level="HIGH",
            requires_confirmation=True,
            verification="Verify screen capture result",
        )]

    def _steps_for_send(self, g):
        if "auto" in g or "automatically" in g:
            return [create_step(
                description="Send message automatically — blocked",
                action="send_message_auto",
                risk_level="CRITICAL",
            )]
        if "email" in g:
            return [create_step(
                description="Draft email",
                action="draft_email",
                risk_level="HIGH",
                requires_confirmation=True,
            )]
        if "whatsapp" in g:
            return [create_step(
                description="Draft WhatsApp message",
                action="draft_whatsapp",
                risk_level="HIGH",
                requires_confirmation=True,
            )]
        return [create_step(
            description="Send message — requires details",
            action="send_message",
            risk_level="HIGH",
            requires_confirmation=True,
        )]

    def _extract_key_value(self, g):
        m = re.search(r'(?:preferred\s+)?(\w[\w\s]{0,30}?)\s+is\s+(.+)', g)
        if m:
            key = m.group(1).strip().replace(" ", "_")
            value = m.group(2).strip()
            return key, value
        return None, None

    def _extract_key(self, g):
        m = re.search(r'(?:forget|remove|delete)\s+(?:my\s+)?(preferred\s+)?(\w[\w\s]{0,30})', g)
        if m:
            key = (m.group(1) or "") + m.group(2)
            return key.strip().replace(" ", "_")
        return None

    def _update_task_status(self, task):
        all_completed = all(s.status == "completed" for s in task.steps)
        any_failed = any(s.status == "failed" for s in task.steps)
        any_blocked = any(s.status == "blocked" for s in task.steps)
        if all_completed:
            task.update_status("completed")
        elif any_failed:
            task.update_status("failed")
        elif any_blocked:
            task.update_status("blocked")
