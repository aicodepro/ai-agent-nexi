from src.orin.voice.response_style import ResponseStyle
from src.orin.voice.voice_personality import VoicePersonality


class VoiceOrchestrator:
    @classmethod
    def compose(cls, intent_result):
        if not intent_result:
            return "Hmm, I didn't get that."
        function = intent_result.get("function", "")
        risk = intent_result.get("risk_level", "SAFE")
        requires_confirm = intent_result.get("requires_confirmation", False)
        summary = intent_result.get("user_facing_summary", "")
        follow_up = intent_result.get("follow_up_question", "")
        language = intent_result.get("language", "en")
        if EmergencyStop_active():
            return VoicePersonality.style("blocked", "Stopped. New actions are blocked.", language)
        if risk == "CRITICAL":
            return VoicePersonality.style("blocked", summary or "That action is blocked for safety.", language)
        if requires_confirm:
            msg = summary or f"About to {function.replace('_', ' ')}."
            if follow_up:
                msg += f" {follow_up}"
            else:
                msg += " Should I proceed?"
            return VoicePersonality.style("confirmation", msg, language)
        if intent_result.get("missing_fields"):
            return VoicePersonality.style("thinking", follow_up or "I need a bit more info.", language)
        return VoicePersonality.style("success", summary or "Done.", language)

    @classmethod
    def compose_error(cls, error_message, language="en"):
        return VoicePersonality.style("error", error_message or "Something went wrong.", language)

    @classmethod
    def compose_acknowledgement(cls, message, language="en"):
        return VoicePersonality.style("acknowledgement", message, language)


def EmergencyStop_active():
    from src.orin.control.safety import EmergencyStop
    return EmergencyStop.is_engaged()
