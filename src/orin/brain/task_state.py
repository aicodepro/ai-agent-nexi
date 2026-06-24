import uuid
from datetime import datetime

VALID_TASK_STATUSES = {"planned", "running", "blocked", "completed", "failed"}
VALID_STEP_STATUSES = {"pending", "running", "blocked", "completed", "failed"}
VALID_RISKS = {"SAFE", "MEDIUM", "HIGH", "CRITICAL"}


def validate_status(status, valid_set):
    return status in valid_set


def validate_risk(risk):
    return risk in VALID_RISKS


_DEFAULT_TASK_STATUS = "planned"
_DEFAULT_STEP_STATUS = "pending"


def normalize_status(status, valid_set, default="pending"):
    if status in valid_set:
        return status
    return default


def normalize_risk(risk):
    if risk in VALID_RISKS:
        return risk
    return "SAFE"


class AutonomyStep:
    def __init__(self, description="", action="", risk_level="SAFE",
                 requires_confirmation=False, verification="", result=None):
        self.step_id = str(uuid.uuid4())
        self.description = description
        self.action = action
        self.status = "pending"
        self.risk_level = normalize_risk(risk_level)
        self.requires_confirmation = requires_confirmation or self.risk_level == "HIGH"
        self.verification = verification
        self.result = result or {}

    def to_dict(self):
        return {
            "step_id": self.step_id,
            "description": self.description,
            "action": self.action,
            "status": self.status,
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "verification": self.verification,
            "result": self.result,
        }


class AutonomyTask:
    def __init__(self, goal="", risk_level="SAFE"):
        self.task_id = str(uuid.uuid4())
        self.goal = goal
        self.status = "planned"
        self.steps = []
        self.risk_level = normalize_risk(risk_level)
        self.requires_confirmation = self.risk_level in ("HIGH", "CRITICAL")
        self.created_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "goal": self.goal,
            "status": self.status,
            "steps": [s.to_dict() for s in self.steps],
            "risk_level": self.risk_level,
            "requires_confirmation": self.requires_confirmation,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def add_step(self, step):
        self.steps.append(step)
        self.updated_at = datetime.now().isoformat()
        self._recalculate_risk()

    def update_status(self, status):
        if validate_status(status, VALID_TASK_STATUSES):
            self.status = status
            self.updated_at = datetime.now().isoformat()

    def _recalculate_risk(self):
        max_risk = "SAFE"
        order = ["SAFE", "MEDIUM", "HIGH", "CRITICAL"]
        for s in self.steps:
            if order.index(s.risk_level) > order.index(max_risk):
                max_risk = s.risk_level
        self.risk_level = max_risk
        self.requires_confirmation = max_risk in ("HIGH", "CRITICAL")


def create_task(goal="", risk_level="SAFE"):
    return AutonomyTask(goal=goal, risk_level=risk_level)


def create_step(description="", action="", risk_level="SAFE",
                requires_confirmation=False, verification="", result=None):
    return AutonomyStep(
        description=description,
        action=action,
        risk_level=risk_level,
        requires_confirmation=requires_confirmation,
        verification=verification,
        result=result or {},
    )
