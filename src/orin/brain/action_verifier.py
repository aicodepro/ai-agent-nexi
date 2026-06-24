from src.orin.control.safety import EmergencyStop, SandboxPolicy


class ActionVerifier:
    @classmethod
    def verify(cls, intent_result):
        if not intent_result:
            return intent_result
        risk = intent_result.get("risk_level", "SAFE")
        action_name = intent_result.get("function", "")
        if EmergencyStop.is_engaged():
            intent_result["risk_level"] = "CRITICAL"
            intent_result["requires_confirmation"] = False
            intent_result["user_facing_summary"] = "Stopped. New actions are blocked."
            return intent_result
        allowed, reason = SandboxPolicy.is_allowed(risk, action_name)
        if not allowed:
            intent_result["risk_level"] = "CRITICAL"
            intent_result["requires_confirmation"] = False
            intent_result["user_facing_summary"] = f"Blocked: {reason}"
            return intent_result
        if risk == "HIGH":
            intent_result["requires_confirmation"] = True
            if not intent_result.get("follow_up_question"):
                intent_result["follow_up_question"] = "This is a high-risk action. Proceed?"
        if risk in ("SAFE", "MEDIUM"):
            intent_result["requires_confirmation"] = False
        return intent_result

    @classmethod
    def is_executable(cls, intent_result):
        if not intent_result:
            return False, "No intent result"
        if EmergencyStop.is_engaged():
            return False, "Emergency stop is engaged"
        risk = intent_result.get("risk_level", "SAFE")
        action_name = intent_result.get("function", "")
        allowed, reason = SandboxPolicy.is_allowed(risk, action_name)
        if not allowed:
            return False, reason
        if intent_result.get("requires_confirmation", False):
            return False, "Requires user confirmation"
        return True, ""
