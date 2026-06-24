_SCREEN_COMMANDS = [
    "screen dekho",
    "screen dekhao",
    "look at this screen",
    "look at this code",
    "kya error hai screen pe",
    "check this terminal error",
    "screen pe kya hai",
    "error dikhao",
    "what do you see",
    "what is on my screen",
    "screen read karo",
    "screen check karo",
]


def detect_screen_command(text):
    if not text:
        return False
    t = text.lower().strip()
    for cmd in _SCREEN_COMMANDS:
        if cmd in t:
            return True
    if "see" in t and "screen" in t:
        return True
    if "check" in t and "error" in t:
        return True
    return False


_CONTEXT_LABELS = {
    "code": "Code Editor",
    "terminal": "Terminal / Command Prompt",
    "browser": "Web Browser",
    "app": "Application Window",
    "unknown": "Unknown Content",
}


def get_context_label(detected_context):
    return _CONTEXT_LABELS.get(detected_context, "Unknown Content")


def create_safe_summary(analysis_result):
    if not analysis_result or not analysis_result.get("ok"):
        return "Could not analyze the screen."
    summary = analysis_result.get("summary", "")
    sensitive = analysis_result.get("sensitive_content_detected", False)
    if sensitive:
        return f"{summary} Note: Sensitive content was detected."
    context = analysis_result.get("detected_context", "unknown")
    label = get_context_label(context)
    return f"{summary} Context: {label}"
