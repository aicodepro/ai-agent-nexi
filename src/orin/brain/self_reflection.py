_QUESTION_WORDS = {
    "what", "why", "how", "when", "where", "who", "which", "whose",
}
_AMBIGUOUS_GOAL_TRIGGERS = {
    "it", "that", "this", "there", "something", "anything",
}
_COMPLETE_SHORT_GOALS = {
    "diagnose jarvi", "diagnose nexi", "stop everything", "emergency stop",
    "freeze everything", "check project", "check status",
    "what do you remember", "show memories", "show preferences",
    "tell me about me", "project status",
}


def summarize_goal(goal):
    if not goal or not goal.strip():
        return "No goal provided."
    g = goal.strip().lower()
    if any(g.startswith(q) for q in ("diagnose", "check", "what is", "status")):
        return f"Analyze and report on: {goal.strip()}"
    if "remember" in g or "forget" in g:
        return f"Memory operation: {goal.strip()}"
    if "open" in g or "launch" in g or "start" in g:
        return f"Application action: {goal.strip()}"
    if "search" in g:
        return f"Search operation: {goal.strip()}"
    if "screen" in g or "dekho" in g or "dikhao" in g:
        return f"Screen observation: {goal.strip()}"
    if "stop" in g or "freeze" in g:
        return f"Emergency action: {goal.strip()}"
    if "delete" in g or "remove" in g:
        return f"Destructive action requires review: {goal.strip()}"
    return f"Process goal: {goal.strip()}"


def detect_missing_context(goal):
    if not goal or not goal.strip():
        return ["goal is empty"]
    g = goal.strip().lower()
    missing = []
    if "search" in g and "for" not in g and "search" not in g.split()[:-1]:
        if not any(q in g for q in ("youtube", "google", "web")):
            missing.append("search platform or query")
    if ("open" in g or "launch" in g) and not any(
        a in g for a in ("chrome", "browser", "app", "youtube", "folder", "file")
    ):
        missing.append("which application to open")
    if "remember" in g:
        if "is" not in g and "=" not in g:
            missing.append("what value to remember")
    if "forget" in g and not any(
        w in g for w in ("preference", "memory", "all", "everything")
    ):
        missing.append("which specific memory to forget")
    if "send" in g and "what" not in g:
        missing.append("what to send")
    if ("screen" in g or "dekho" in g) and "capture" not in g:
        pass
    return missing


def should_ask_followup(goal):
    if not goal or not goal.strip():
        return True
    g = goal.strip().lower()
    if g in _COMPLETE_SHORT_GOALS:
        return False
    missing = detect_missing_context(goal)
    if missing:
        return True
    words = g.split()
    if len(words) <= 2:
        return True
    for word in _AMBIGUOUS_GOAL_TRIGGERS:
        if word in words:
            return True
    return False


def generate_followup_question(goal):
    if not goal or not goal.strip():
        return "What would you like me to do?"
    missing = detect_missing_context(goal)
    if missing:
        return f"Could you clarify: {missing[0]}?"
    g = goal.strip().lower()
    if len(g.split()) <= 2:
        return "Could you provide more detail?"
    for word in _AMBIGUOUS_GOAL_TRIGGERS:
        if word in g.split():
            return f"What exactly do you mean by \"{goal.strip()}\"?"
    return "Is there anything else you'd like to specify?"
