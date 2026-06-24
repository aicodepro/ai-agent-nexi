from src.orin.voice.response_style import ResponseStyle

PERSONALITY_MAP = {
    "acknowledgement": "concise",
    "thinking": "thoughtful",
    "executing": "active",
    "success": "warm",
    "blocked": "firm",
    "error": "helpful",
    "confirmation": "careful",
}

NATURAL_REPLACEMENTS = {
    "Opening Chrome.": "Opening Chrome.",
    "Searching YouTube.": "Searching YouTube.",
    "Searching Google.": "Searching Google.",
    "Showing running apps.": "Here are your running apps.",
    "Getting active window.": "Your active window is ready.",
    "Creating folder.": "Creating that folder for you.",
    "Opening folder.": "Opening that folder.",
    "Stopped. New actions are blocked.": "Stopped. New actions are blocked.",
    "Running diagnostics.": "Running a check on myself.",
}


class VoicePersonality:
    @classmethod
    def style(cls, style_name, message, language="en"):
        formatted = ResponseStyle.format(style_name, message, language)
        if language == "en":
            for formal, natural in NATURAL_REPLACEMENTS.items():
                if formal in formatted:
                    formatted = formatted.replace(formal, natural)
        return formatted

    @classmethod
    def get_personality(cls, style_name):
        return PERSONALITY_MAP.get(style_name, "neutral")
