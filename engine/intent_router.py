# intent_router.py
# Deterministic intent router for Nexi.
#
# Priority order:
#   1. Active workflow         -> route="workflow"
#   2. Hard local exact/prefix -> route="local_action"
#   3. Q&A patterns reserved   -> route="local_action"  (e.g. "what is the time")
#      for local intents
#   4. Identity (exact only)   -> route="identity"
#   5. Greeting (exact only)   -> route="greeting"
#   6. Pure math expressions   -> route="brain"
#   7. General Q&A prefixes    -> route="brain"
#   8. Default                 -> route="unknown"  (caller may fallback to brain chain)
#
# Route "brain" means "general Q&A — use provider chain (HugChat primary,
# Lightning fallback)". The router itself does not pick a provider.
#
# This module is pure logic. No speak(), no eel, no I/O, no network calls.
# Caller (engine.command.allCommands) decides what to do with the route.

from dataclasses import dataclass
import re


@dataclass
class IntentResult:
    route: str          # workflow | local_action | greeting | identity | brain | unknown
    intent: str         # short label (e.g. "open_app", "hello", "general_qa")
    confidence: float   # 0.0 - 1.0
    reason: str         # short debug reason (no secrets)


# --- Greeting (exact only) ----------------------------------------------------
_GREETINGS_EXACT = {
    "hello", "hi", "hey", "hola", "hiya", "howdy", "yo",
    "namaste", "hello there", "hi there",
}
_GREETINGS_TIME_PREFIX = ("good morning", "good afternoon", "good evening", "good night")

# --- Identity (exact only) ----------------------------------------------------
_IDENTITY_EXACT = {
    "who are you", "introduce yourself", "what is your name",
    "what's your name", "whats your name", "tell me about yourself",
    "who r u", "your name", "say your name", "what are you",
    "are you nexi", "who is nexi",
}

# --- Workflow cancel words (used when a workflow is active) -------------------
_WORKFLOW_CANCEL = {
    "cancel", "stop", "never mind", "nevermind", "exit",
    "leave it", "quit", "forget it",
}

# --- Hard local command prefixes ---------------------------------------------
# Anything starting with these must NEVER reach Lightning. Order: longest first
# is not required because we use startswith on each.
_LOCAL_PREFIXES = (
    "open ", "launch ", "start ", "run app", "run application",
    "close ", "exit ", "quit ", "kill ",
    "create folder", "create a folder", "make folder", "make a folder", "new folder",
    "create file", "create a file", "make file", "make a file", "new file",
    "play ", "pause ", "resume ", "mute ",
    "volume up", "volume down", "increase volume", "decrease volume",
    "search google", "google search", "search youtube", "youtube search",
    "search the web",
    "go to ", "navigate to ", "take me to ",
    "send ", "call ", "message ", "video call", "phone call",
    "minimize", "fullscreen", "full screen", "zoom in", "zoom out",
    "new tab", "close tab", "next tab", "previous tab", "back tab",
    "open history", "open bookmarks", "show bookmarks", "show history",
    "go back", "go forward",
    "refresh", "reload",
    "private window", "incognito",
    "set alarm", "create alarm", "alarm for",
    "remind me", "set reminder", "schedule",
    "read selected", "read selection", "read my clipboard",
    "tell joke", "tell a joke", "crack a joke",
    "generate image", "create image", "make image",
    "internet speed", "speed test", "check speed",
    "object detection",
    "eye mouse", "hand gesture",
    "auto type", "automatic typing",
)

# --- Hard local commands (whole-string exact match) --------------------------
_LOCAL_EXACT = {
    "stop speaking", "stop talking", "shut up", "enough", "cancel speech",
    "emergency stop", "stop everything", "halt", "abort", "freeze",
    "stop all actions", "cancel everything",
    "what time", "current time", "time now", "time please",
    "pause", "resume", "mute",
    "weather", "todays weather", "weather today",
    "minimize", "fullscreen", "refresh", "reload", "go back", "go forward",
    "what can you do", "what can you control",
    "joke", "tell joke", "tell a joke",
}

# --- Q&A patterns that should stay LOCAL (override Lightning routing) --------
_QA_LOCAL_PATTERNS = (
    "what is the time", "what's the time", "whats the time",
    "what is the weather", "what's the weather", "whats the weather",
    "what is on my screen", "what window is active",
    "what is this tab", "what tab am i on",
    "what apps are open", "what's running", "whats running",
    "what can you do", "what can you control",
)

# --- Pure math expression ----------------------------------------------------
_MATH_RE = re.compile(r"^[\d\s\+\-\*\/\=\(\)\.x%]+$")

# --- Q&A prefixes that mean general knowledge -> Lightning -------------------
_QA_PREFIXES = (
    "what is ", "what are ", "what's ", "whats ",
    "what was ", "what were ",
    "how to ", "how do ", "how does ", "how can ", "how is ", "how are ",
    "how should ", "how would ",
    "why is ", "why does ", "why do ", "why are ", "why was ",
    "why should ", "why would ", "why can ",
    "explain ", "tell me about ", "describe ", "summarize ",
    "calculate ", "compute ", "solve ",
    "define ", "definition of ",
    "who is ", "who was ", "who were ",
    "where is ", "where are ", "where was ",
    "when is ", "when was ", "when did ", "when will ",
    "write ", "translate ",
)


def _norm(text: str) -> str:
    return (text or "").strip().lower().rstrip(".!?").strip()


def route_intent(text: str, workflow_active: bool = False) -> IntentResult:
    """Deterministically classify `text` into a route.

    Pure function. Does not speak, log secrets, or touch I/O.
    """
    q = _norm(text)

    if not q:
        return IntentResult("unknown", "", 0.0, "empty_query")

    # 1. Active workflow has top priority. Cancel words clear it.
    if workflow_active:
        if q in _WORKFLOW_CANCEL:
            return IntentResult("workflow", "cancel", 1.0, "workflow_cancel")
        return IntentResult("workflow", "reply", 1.0, "workflow_active_reply")

    # 2. Local exact matches (whole-string)
    if q in _LOCAL_EXACT:
        return IntentResult("local_action", q.replace(" ", "_"), 1.0, "local_exact")

    # 3. Q&A patterns that map to existing local intents (time, weather, tab info)
    for excl in _QA_LOCAL_PATTERNS:
        if q == excl or q.startswith(excl):
            return IntentResult(
                "local_action", "local_qa_pattern", 0.95,
                f"qa_local_pattern={excl!r}",
            )

    # 4. Local command prefixes
    for prefix in _LOCAL_PREFIXES:
        p = prefix.rstrip()
        if q == p or q.startswith(p + " ") or q.startswith(prefix):
            return IntentResult(
                "local_action", "local_prefix", 1.0,
                f"local_prefix={p!r}",
            )

    # 5. Identity intents (exact only)
    if q in _IDENTITY_EXACT:
        return IntentResult("identity", "who_are_you", 1.0, "identity_exact")

    # 6. Greeting intents (exact only)
    if q in _GREETINGS_EXACT:
        return IntentResult("greeting", "hello", 1.0, "greeting_exact")
    for g in _GREETINGS_TIME_PREFIX:
        if q == g or q.startswith(g + " ") or q == g + "!":
            return IntentResult("greeting", "good_time", 1.0, "greeting_time")

    # 7. Pure math expressions -> brain provider chain
    if _MATH_RE.match(q):
        return IntentResult("brain", "general_qa", 1.0, "math_expression")

    # 8. General Q&A prefixes -> brain provider chain
    for pref in _QA_PREFIXES:
        if q.startswith(pref):
            return IntentResult(
                "brain", "general_qa", 0.9,
                f"qa_prefix={pref.strip()!r}",
            )

    # 9. Default — caller may try dispatch_intent, then brain chain
    return IntentResult("unknown", "", 0.0, "no_match")
