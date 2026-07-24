from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Any

import requests

from engine.intent_taxonomy import BRAIN_INTENTS, OUTPUT_INTENTS, empty_result, exact_schema
from engine.studio.commands import explicit_studio_action, issue_authorization, parse_studio_command, studio_command_body


def _norm(text: str) -> str:
    return " ".join(str(text or "").strip().lower().rstrip(".?!").split())


def _load_prompt() -> str:
    try:
        from engine.prompt_loader import load_prompt_file
        return load_prompt_file("nexi_groq_intent_system_prompt.txt", "You are Nexi Intent Router v2. Return strict JSON only.")
    except Exception:
        return "You are Nexi Intent Router v2. Return strict JSON only."


def _json_object(text: str) -> dict[str, Any]:
    value = str(text or "").strip()
    match = re.search(r"\{.*\}", value, flags=re.S)
    if match:
        value = match.group(0)
    data = json.loads(value)
    return data if isinstance(data, dict) else {}


# ── Rate limiter ────────────────────────────────────────────────────────────
_last_llm_call: dict[str, float] = {}
_llm_rate_lock = threading.Lock()

def _llm_rate_limited(scope: str = "default") -> bool:
    global _last_llm_call
    cooldown = float(os.getenv("GROQ_INTENT_COOLDOWN_SECONDS", "0.5"))
    now = time.time()
    with _llm_rate_lock:
        if not isinstance(_last_llm_call, dict):
            _last_llm_call = {}
        if now - _last_llm_call.get(scope, 0.0) < cooldown:
            return True
        _last_llm_call[scope] = now
        return False


def _intent_timeout_seconds() -> float:
    try:
        value = float(os.getenv("GROQ_INTENT_TIMEOUT_SECONDS", "3"))
    except (TypeError, ValueError):
        value = 3.0
    return max(0.1, min(value, 10.0))


def _intent_max_retries() -> int:
    try:
        value = int(os.getenv("GROQ_INTENT_MAX_RETRIES", "1"))
    except (TypeError, ValueError):
        value = 1
    return max(0, min(value, 2))


# ── Deterministic fallback ──────────────────────────────────────────────────
def _qa_like(q: str) -> bool:
    prefixes = (
        "what is ", "what are ", "what's ", "whats ", "who is ", "who was ",
        "how to ", "how do ", "how does ", "why ", "why is ", "why does ",
        "explain ", "tell me about ", "describe ", "summarize ", "define ",
        "write ", "translate ", "calculate ", "compute ", "solve ",
    )
    return any(q.startswith(prefix) for prefix in prefixes)


# Words that mark an utterance as conversation/planning rather than an action request.
# Used by the no-feature-matched fallback at the end of _deterministic_router: with a
# signal the brain answers, without one Nexi asks instead of guessing. See the comment
# there for why this is a conversational allowlist and not an action-verb blocklist.
_BRAIN_SIGNAL_RE = re.compile(
    r"\b(?:plan|planning|plans|idea|ideas|brainstorm|think|thought|thoughts|opinion|"
    r"advice|advise|suggest|suggestion|recommend|explain|explanation|discuss|help|"
    r"should|could|would|why|how|teach|learn|understand|summarise|summarize|summary|"
    r"compare|comparison|difference|meaning|means|about)\b",
    re.I,
)


def _react_like(q: str) -> bool:
    if any(phrase in q for phrase in (" and then ", " then ", " after that ")):
        verbs = sum(1 for token in ("find", "search", "open", "save", "create", "copy", "remember", "recall", "show") if token in q)
        return verbs >= 2
    return any(
        phrase in q
        for phrase in (
            "save my last note",
            "find my note",
            "recall my note",
            "search my memory and",
            "find in memory and",
        )
    )


def _is_multistep(text: str) -> bool:
    """True when the utterance is a compound command (>=2 executable steps).

    Reuses the Master Router's compound splitter, which splits on sequence markers
    (then / and then / after that / next / ; / "and <verb>") but keeps object-lists
    like "search for cats and dogs" as one command. Deterministic and offline, so
    multi-step routing never depends on the LLM. Falls back to the narrow
    _react_like heuristic if the splitter is unavailable.
    """
    try:
        from engine.router.compound import split_steps
        if len(split_steps(str(text or ""))) >= 2:
            return True
    except Exception:
        pass
    return _react_like(_norm(text))


# Zero-slot tools that can be matched by a simple alias/keyword in any position.
_SIMPLE_ALIAS_TOOLS = {
    "tell_time": ("system", ("what time is it", "what's the time", "whats the time", "current time", "time now", "tell me the time")),
    "tell_joke": ("conversation", ("tell me a joke", "tell a joke", "make me laugh", "crack a joke", "say a joke")),
    "internet_speed_test": ("system", ("internet speed", "speed test", "check internet speed", "check my internet", "network speed", "test internet")),
    "get_active_window": ("system", ("which app is active", "what app is active", "active window", "what app am i using", "current app", "what app is open", "what is the active app")),
    "what_am_i_working_on": ("system", ("what am i working on", "what am i doing", "what am i up to")),
    "get_system_state": ("system", ("system status", "pc status", "system state", "how is my pc", "computer status", "resource usage", "whats my system status", "what is my system status", "how is my computer")),
    "why_is_pc_slow": ("system", ("why is my pc slow", "why is my computer slow", "what is slowing my pc", "whats using my cpu", "what is using memory", "why is it lagging", "why is my pc lagging", "whats slowing my computer", "what is slowing my computer", "what's slowing my computer", "what's slowing my pc", "my pc is slow", "my computer is slow", "pc is slow", "computer is slow")),
    "am_i_online": ("system", ("am i online", "do i have internet", "are we connected", "am i connected", "is the internet working", "is the internet up", "have i got internet")),
    "get_network_status": ("system", ("network status", "wifi status", "wi-fi status", "what network am i on", "what wifi am i on", "what wi-fi am i on", "connection status", "am i on wifi", "am i on wi-fi")),
    "get_ip_address": ("system", ("what is my ip address", "whats my ip address", "what's my ip address", "my ip address", "whats my ip", "what's my ip", "what is my ip", "ip address", "show my ip")),
    "get_disk_space": ("system", ("how much disk space do i have", "disk space", "how much storage do i have", "how much space do i have", "free disk space", "storage space", "how much free space")),
    "is_disk_full": ("system", ("is my disk full", "is my drive full", "am i running out of space", "is my storage full", "is my disk almost full", "running low on space", "is my disk getting full")),
    "get_battery_status": ("system", ("battery status", "how much battery do i have", "am i charging", "battery level", "whats my battery", "what's my battery", "how is my battery", "how much battery is left")),
    "get_running_apps": ("system", ("what apps are running", "list running apps", "running apps", "what programs are open", "what programs are running", "show running apps", "whats running", "what is running", "what apps are open")),
    "get_idle_time": ("system", ("how long have i been idle", "idle time", "how long was i away", "am i idle", "how long have i been away", "how long was i idle", "how long have i been inactive")),
    "show_diagnostics": ("system", ("show diagnostics", "voice diagnostics", "show voice diagnostics", "diagnostics", "run diagnostics", "system diagnostics", "show your diagnostics")),
    "get_monitor_state": ("system", ("monitor state", "monitor status", "what are you monitoring", "show monitor", "world monitor", "dashboard state", "whats on the monitor")),
    "echo_guard_status": ("system", ("echo guard status", "are you in cooldown", "tts cooldown", "echo status", "cooldown status", "echo guard")),
    "get_hud_state": ("system", ("show hud", "hud state", "command center", "your current state", "what is your current state", "show your status", "whats your current state")),
    "what_did_you_learn": ("system", ("what did you learn", "what did you learn from that", "show your lessons", "what lessons do you have", "reflection memory", "what mistakes have you learned from", "what have you learned from your mistakes")),
    "list_skills": ("system", ("what can you do", "list your skills", "what are your skills", "show skills", "list skills", "what can you help with", "list capabilities", "what skills do you have", "show your skills", "what are you capable of")),
    "read_current_page": ("web", ("read this page", "read the page", "read current page", "summarize this page", "summarize the page", "whats on this page", "what is on this page", "read my browser", "read the browser")),
    "list_browser_tabs": ("web", ("list my tabs", "what tabs are open", "show my tabs", "list browser tabs", "what tabs do i have", "how many tabs", "what tabs do i have open")),
    "read_browser_console": ("web", ("read the console", "check console errors", "browser console", "console errors", "check the console", "any console errors", "read browser console")),
    "pending_approvals": ("system", ("pending approvals", "show approvals", "show pending approvals", "what needs approval", "pending actions", "approval queue", "whats pending")),
    "approve_action": ("system", ("approve", "approve action", "approve that", "approve it", "approve the action")),
    "reject_action": ("system", ("reject", "reject action", "reject that", "reject it", "deny action", "cancel the action")),
    "screen_read": ("desktop", ("read my screen", "read the screen", "read screen", "whats on my screen", "what is on my screen", "what is on the screen", "whats on the screen")),
    "list_feature_requests": ("system", ("list feature requests", "show feature requests", "pending features", "what features did i request", "feature requests")),
    "nexi_run_router_audit": ("workflow", ("run an agent audit of the router", "start an agent audit of the intent router", "run an agent audit of the intent router", "agent audit of the intent router", "audit the router with agents", "run router audit workflow")),
    "nexi_run_codebase_research": ("workflow", ("research this repo with agents", "run codebase research", "research the codebase with agents", "agent research workflow")),
    "nexi_run_test_generation": ("workflow", ("generate tests with agents", "run test generation workflow", "agent test generation")),
    "nexi_run_integration_plan": ("workflow", ("create an integration plan", "run integration plan workflow", "plan the integration with agents")),
    "nexi_workflow_status": ("workflow", ("workflow status", "show workflow status", "agent workflow status", "whats the workflow status")),
    "nexi_agent_activity": ("workflow", ("show current agent activity", "agent activity", "current agent activity", "show agent activity", "what are the agents doing")),
    "nexi_workflow_logs": ("workflow", ("workflow logs", "show workflow logs", "agent logs", "show agent logs", "agent workflow logs")),
    "nexi_workflow_artifacts": ("workflow", ("show the agent report", "latest agent report", "show latest agent report", "agent reports", "workflow artifacts", "workflow report")),
    "nexi_cancel_workflow": ("workflow", ("cancel workflow", "cancel the workflow", "cancel agent workflow", "stop the agent workflow")),
    "nexi_continue_workflow": ("workflow", ("continue workflow", "continue the agent workflow", "resume workflow", "resume the agent workflow")),
    "media_pause": ("desktop", ("pause the video", "pause video", "pause music", "pause media", "stop playing")),
    "media_resume": ("desktop", ("resume the video", "resume video", "play again", "resume media", "continue playing")),
    "media_mute": ("desktop", ("mute the video", "mute sound", "mute media")),
    "browser_new_tab": ("browser", ("open a new tab", "open new tab", "new tab")),
    "browser_close_tab": ("browser", ("close the tab", "close current tab", "close this tab", "close tab")),
    "browser_refresh": ("browser", ("refresh the page", "reload the page", "refresh page", "reload page")),
    "browser_back": ("browser", ("go back",)),
    "browser_forward": ("browser", ("go forward",)),
    "browser_history": ("browser", ("show my history", "open history", "browser history")),
    "browser_fullscreen": ("browser", ("go fullscreen", "toggle fullscreen", "full screen")),
}


# A question that merely CONTAINS a tool word is not a command. "why is the weather so
# unpredictable" wants an explanation; the specific matchers (_weather_match) already
# guard this, but the alias matcher below matched the bare word "weather" and hijacked
# the question into weather_lookup. Guard once here so every alias inherits it rather
# than each matcher re-implementing the check.
_QUESTION_PREFIX_RE = re.compile(
    r"^\s*(?:why|how\s+(?:does|do|did|is|are|can|would|should)|explain|"
    r"what\s+(?:is|are|causes|makes|does)|who\s+(?:is|are)|when\s+(?:is|did|was)|"
    r"tell\s+me\s+about|difference\s+between)\b", re.I)


# ...but a question about the user's OWN machine, or about Nexi itself, IS a command:
# "what is my system status", "what are you monitoring", "why is my pc slow", "what is my
# ip address" are exactly what the awareness tools exist to answer. Only general-knowledge
# questions that happen to contain a tool keyword should be vetoed.
#
# "me" and "i" are deliberately NOT here: "tell me about python and go" is a question, not
# a command, and including "me" would let it through.
_SELF_REFERENTIAL_RE = re.compile(r"\b(?:my|your|you)\b", re.I)


def _is_question_not_command(q: str) -> bool:
    """True when the utterance asks ABOUT something rather than asking for it."""
    text = str(q or "")
    if _QUESTION_PREFIX_RE.match(text) is None:
        return False
    return _SELF_REFERENTIAL_RE.search(text) is None


def _alias_tool_match(q: str) -> dict[str, Any] | None:
    """Match zero-slot tools by alias phrase. Longest phrase wins to avoid 'pause' eating 'pause and explain'."""
    # An explanatory question must never be executed as a tool, however many tool
    # keywords it happens to contain.
    if _is_question_not_command(q):
        return None
    best_intent = ""
    best_domain = ""
    best_len = 0
    for intent, (domain, phrases) in _SIMPLE_ALIAS_TOOLS.items():
        for phrase in phrases:
            if intent in {"approve_action", "reject_action"}:
                matched = q == phrase
            else:
                matched = q == phrase or f" {phrase} " in f" {q} " or q.startswith(phrase + " ") or q.endswith(" " + phrase)
            if matched and len(phrase) > best_len:
                best_intent, best_domain, best_len = intent, domain, len(phrase)
    # Registry aliases are authoritative for newly added zero-slot tools. The
    # static table above retains tuned legacy phrases, while this prevents a
    # registered capability from silently falling through to the brain.
    try:
        from engine.tool_registry import model_visible_tools

        for tool in model_visible_tools():
            if tool.required_slots:
                continue
            phrases = (tool.name.replace("_", " "), *tool.aliases)
            for raw_phrase in phrases:
                phrase = str(raw_phrase or "").strip().lower()
                if not phrase:
                    continue
                matched = q == phrase or f" {phrase} " in f" {q} " or q.startswith(phrase + " ") or q.endswith(" " + phrase)
                if matched and len(phrase) > best_len:
                    best_intent, best_domain, best_len = tool.name, tool.category, len(phrase)
    except Exception:
        pass
    if not best_intent:
        return None
    # Weather handled separately because it carries an optional location slot.
    return empty_result(route="tool", intent=best_intent, domain=best_domain, confidence=0.93, reason=f"alias_{best_intent}")


def _youtube_match(q: str, text: str) -> dict[str, Any] | None:
    """Route YouTube open vs play/search. Runs before generic open/search rules."""
    is_yt = ("youtube" in q) or (" yt" in f" {q}") or q.startswith("yt ") or ("yutub" in q) or ("you tube" in q)
    if not is_yt:
        return None
    if q in {"open youtube", "youtube kholo", "open yt", "yutub kholo", "you tube kholo", "go to youtube", "launch youtube", "start youtube"}:
        from engine.website_resolver import resolve_website
        return exact_schema(empty_result(route="tool", intent="open_website", domain="web", confidence=0.95, reason="open_youtube") | {"slots": {"url": resolve_website("youtube").get("url", "youtube.com")}})
    yt_query = re.sub(r"\b(on\s+)?(youtube|yt|yutub|you tube)\b", " ", str(text or ""), flags=re.I)
    yt_query = re.sub(r"\b(play|search|for|pe|karo|dhoondo|khojo|kholo|open)\b", " ", yt_query, flags=re.I)
    yt_query = " ".join(yt_query.split()).strip(" .?!")
    if yt_query:
        return exact_schema(empty_result(route="tool", intent="search_youtube", domain="web", confidence=0.92, reason="youtube_search") | {"slots": {"query": yt_query}})
    return exact_schema(empty_result(route="clarify", intent="search_youtube", domain="web", confidence=0.9, reason="missing_yt_query", clarification_question="What should I play on YouTube?") | {"missing_slots": ["query"]})


def _weather_match(q: str, text: str) -> dict[str, Any] | None:
    if not any(w in q for w in ("weather", "temperature", "how hot", "how cold")):
        return None
    # "how hot is the sun" / "how cold is space" are questions, not weather. Only
    # treat how-hot/how-cold as weather when it's clearly about ambient conditions.
    if ("how hot" in q or "how cold" in q) and "weather" not in q and "temperature" not in q:
        if not any(w in q for w in ("outside", "today", "tonight", "right now", " now", " here", " it ", "is it")):
            return None
    # "why is the weather so unpredictable" / "how does weather work" are questions.
    if q.startswith(("why ", "how does ", "how do ", "explain ", "what causes ", "what makes ")):
        return None
    location = ""
    m = re.search(r"(?:weather|temperature)\s+(?:in|at|for)\s+(.+)", q)
    if m:
        location = m.group(1).strip(" .?!")
    slots = {"location": location} if location else {}
    return exact_schema(empty_result(route="tool", intent="weather_lookup", domain="web", confidence=0.9, reason="weather_lookup") | {"slots": slots})


# Windows Settings phrases routed before the generic "open <app>" handler.
_SETTINGS_ROUTES = {
    "open_wifi_settings": ("open wifi settings", "open wi-fi settings", "wifi settings", "wi-fi settings", "network settings"),
    "open_bluetooth_settings": ("open bluetooth settings", "bluetooth settings", "open bluetooth"),
    "open_display_settings": ("open display settings", "display settings", "screen settings"),
    "open_sound_settings": ("open sound settings", "sound settings", "audio settings"),
    "open_microphone_settings": ("open microphone settings", "microphone settings", "open mic settings", "mic settings"),
    "open_camera_settings": ("open camera settings", "camera settings", "webcam settings"),
    "open_startup_settings": ("open startup apps", "open startup settings", "startup apps", "startup settings"),
    "open_windows_update": ("open windows update", "windows update", "check for updates"),
    "open_settings": ("open windows settings", "open settings", "windows settings"),
}


_FEATURE_NOUN = r"(?:feature|tool|workflow|integration|automation|bot|monitor|agent|skill)"
_FEATURE_GAP_RES = [
    re.compile(r"^(?:can you |please )?(?:create|build|make|add|set up|develop)(?: me)?(?: a| an)?\s+(?:new\s+)?(.*\b" + _FEATURE_NOUN + r"\b.*)$"),
    re.compile(r"^(?:i want|i need|i would like|i'd like)(?: a| an)?\s+(?:new\s+)?(.*\b" + _FEATURE_NOUN + r"\b.*)$"),
    re.compile(r"^feature request:?\s+(.+)$"),
]
_STUDIO_INTENTS = {
    "nexi_start_studio_build",
    "nexi_studio_status",
    "nexi_cancel_studio_build",
    "nexi_continue_studio_build",
}
_MODEL_FORBIDDEN_INTENTS = frozenset({
    "approve_action",
    "reject_action",
    "nexi_start_studio_build",
    "nexi_cancel_studio_build",
    "nexi_continue_studio_build",
    "nexi_cancel_workflow",
    "nexi_continue_workflow",
})


def _inferred_build_match(text: str, *, source: str = "unknown") -> dict[str, Any] | None:
    """Understand a build request that used no magic phrase.

    Darsh: "I will not issue 'studio mode'. Nexi should interpret the request through
    its own self-understanding." _studio_match above handles the explicit grammar; this
    catches "I want a python function that reverses a string".

    Deliberately routes to CLARIFY, never straight to a build:
      * an inferred reading can be wrong, and an 11-stage build is expensive to undo;
      * authorization must come from the CEO's own turn. The confirming reply IS that
        turn, so the token is minted from a real utterance rather than from an inference.
        This keeps `consume_authorization_audit` honest — a guess can never authorize.
    Any failure returns None so the normal router handles the turn as before.
    """
    if str(os.getenv("NEXI_INFER_BUILD_INTENT", "1")).strip().lower() in {"0", "false", "no", "off"}:
        return None
    # A registered command is not an inferred build. detect_smart escalates zero-signal
    # phrasing to the LLM on purpose ("the CSV thing is manual, sort it out for me"
    # scores 0.0 and IS a build), but that also let the model claim plain tool commands:
    # "start hand gesture control" came back confirm=0.9 on signals=['llm'] alone, with
    # no deterministic build evidence at all. Its own comment assumes routine commands
    # were "already rejected above" -- nothing actually checked that. Deterministic
    # evidence of a real tool outranks an inference, and skipping early also saves the
    # model call on the voice path.
    # Only when the deterministic build scorer found NO evidence at all. "can you make
    # me a tool that renames files" scores build_verb+software_artifact and must still
    # reach the build path even though a file tool matches its wording.
    try:
        from engine.studio.intent_detect import detect

        if not (detect(str(text or "")).get("signals") or []):
            known = _deterministic_router(str(text or ""), {})
            if _deterministic_is_confident(known) and str(known.get("route") or "") in {"tool", "output"}:
                return None
    except Exception:
        pass
    try:
        from engine.studio.intent_detect import confirmation_question, detect_smart
        verdict = detect_smart(text)
    except Exception as exc:
        print(f"[INTENT_V2] infer_build_skipped reason={type(exc).__name__}", flush=True)
        return None
    if verdict.get("action") != "confirm" or not verdict.get("goal"):
        return None
    print(f"[INTENT_V2] inferred_build confidence={verdict['confidence']} "
          f"signals={','.join(verdict.get('signals') or [])}", flush=True)
    return exact_schema(empty_result(
        route="clarify",
        intent="nexi_start_studio_build",
        domain="workflow",
        confidence=float(verdict["confidence"]),
        reason="inferred_build_intent",
    ) | {
        # `clarification_question` is the schema's field for what NEXI asks — a `speak`
        # key is silently dropped by exact_schema, so the confirmation would never be
        # voiced and the turn would look like a bug rather than a question.
        "clarification_question": confirmation_question(verdict),
        "expects_user_reply": True,
        "slots": {"goal": verdict["goal"], "command_source": source},
    })


def _studio_match(q: str, text: str, *, source: str = "unknown") -> dict[str, Any] | None:
    """Route only explicit Studio start/control phrases."""
    action = explicit_studio_action(text)
    if not action:
        return None
    body = studio_command_body(text)
    if action == "status":
        return empty_result(route="tool", intent="nexi_studio_status", domain="workflow", confidence=1.0, reason="studio_status")
    if action == "cancel":
        raw_text = str(text or "").strip()
        return exact_schema(empty_result(route="tool", intent="nexi_cancel_studio_build", domain="workflow", confidence=1.0, reason="studio_cancel") | {"slots": {
            "raw_text": raw_text,
            "command_source": source,
            "_studio_auth": issue_authorization(raw_text, "cancel", source=source),
        }})
    if action == "continue":
        match = re.match(r"^(?:studio continue|continue studio|resume studio build)\b(?:\s*:?\s*(.*))?$", body, flags=re.I | re.S)
        if match is None:
            return None
        answer = (match.group(1) or "").strip()
        if not answer:
            return exact_schema(empty_result(
                route="clarify",
                intent="nexi_continue_studio_build",
                domain="workflow",
                confidence=1.0,
                reason="studio_answer_required",
                clarification_question="What answer should I give the Studio team?",
            ) | {"missing_slots": ["answer"]})
        raw_text = str(text or "").strip()
        return exact_schema(empty_result(route="tool", intent="nexi_continue_studio_build", domain="workflow", confidence=1.0, reason="studio_continue") | {"slots": {
            "answer": answer,
            "raw_text": raw_text,
            "command_source": source,
            "_studio_auth": issue_authorization(raw_text, "continue", source=source),
        }})
    parsed = parse_studio_command(text)
    if not parsed:
        return None
    if not parsed["goal"]:
        return exact_schema(empty_result(
            route="clarify",
            intent="nexi_start_studio_build",
            domain="workflow",
            confidence=1.0,
            reason="studio_goal_required",
            clarification_question="What should we build now?",
        ) | {"missing_slots": ["goal"]})
    slots = {
        "command": parsed["raw_text"],
        "goal": parsed["goal"],
        "command_source": source,
        "_studio_auth": issue_authorization(parsed["raw_text"], "start", source=source),
    }
    if parsed.get("project_dir"):
        slots["project_dir"] = parsed["project_dir"]
    return exact_schema(empty_result(route="tool", intent="nexi_start_studio_build", domain="workflow", confidence=1.0, reason="explicit_studio_build") | {"slots": slots, "risk_level": "high"})


_FORGE_RES = [
    # "build yourself a tool that ..." / "write your own skill to ..."
    re.compile(r"^(?:can you |please )?(?:build|make|write|create|forge)\s+(?:yourself|your own)\s+(?:a |an )?(?:new )?(?:tool|skill|function)\s+(?:that |which |to |for |which can )?(.+)$"),
    # "forge a tool that ..." — 'forge' is unambiguous, no "yourself" needed
    re.compile(r"^(?:can you |please )?forge\s+(?:me )?(?:a |an )?(?:new )?(?:tool|skill|function)\s+(?:that |which |to |for )?(.+)$"),
]


def _forge_match(q: str, text: str) -> dict[str, Any] | None:
    """Route "build YOURSELF a tool that X" to the forge, which actually writes it.

    Distinct from _feature_gap_match below: "build a tool that watches my downloads"
    is a feature REQUEST for the roadmap, while "build yourself a tool that ..." is
    an instruction to write and install it now. The "yourself"/"forge" wording is the
    signal, so this must run before the feature-gap parser claims it.
    """
    for rx in _FORGE_RES:
        m = rx.match(q)
        if m and m.group(1).strip():
            spec = m.group(1).strip(" .?!")
            return exact_schema(empty_result(route="tool", intent="nexi_forge_tool", domain="system", confidence=0.95, reason="forge_tool") | {"slots": {"spec": spec}})
    return None


def _feature_gap_match(q: str, text: str) -> dict[str, Any] | None:
    """Route 'build a <tool/monitor/automation> that …' to the feature-request logger.

    Routed via the request_feature tool so it works end-to-end today (the feature_gap
    route type also exists in the taxonomy for the LLM router / future handler).
    """
    for rx in _FEATURE_GAP_RES:
        m = rx.match(q)
        if m and m.group(1).strip():
            cap = m.group(1).strip(" .?!")
            return exact_schema(empty_result(route="tool", intent="request_feature", domain="system", confidence=0.9, reason="feature_gap") | {"slots": {"capability": cap, "user_input": str(text or "")}})
    return None


_CLICK_RE = re.compile(r"^click(?: on| the)?\s+(.+?)(?:\s+button)?$")
_TYPE_RE = re.compile(r"^type(?: out| the text)?\s+(.+)$")


_BROWSER_FILL_RE = re.compile(r"^fill(?: in)?(?: the)?\s+(.+?)\s+(?:field\s+)?with\s+(.+)$")
_BROWSER_CLICK_LINK_RE = re.compile(r"^(?:browser click|click)(?: the| on)?\s+(.+?)\s+link$")
_BROWSER_CLICK_PAGE_RE = re.compile(r"^click(?: the| on)?\s+(.+?)\s+on the page$")


def _browser_write_match(q: str) -> dict[str, Any] | None:
    """Route browser-specific write actions (fill/click link) to the (gated) browser tools."""
    m = _BROWSER_FILL_RE.match(q)
    if m and m.group(1).strip() and m.group(2).strip():
        return exact_schema(empty_result(route="tool", intent="browser_fill", domain="web", confidence=0.88, reason="browser_fill") | {"slots": {"field": m.group(1).strip(), "value": m.group(2).strip(" .?!")}})
    for rx in (_BROWSER_CLICK_LINK_RE, _BROWSER_CLICK_PAGE_RE):
        m = rx.match(q)
        if m and m.group(1).strip():
            return exact_schema(empty_result(route="tool", intent="browser_click", domain="web", confidence=0.88, reason="browser_click") | {"slots": {"target": m.group(1).strip(" .?!")}})
    return None


def _computer_use_match(q: str) -> dict[str, Any] | None:
    """Route 'click <x>' / 'type <x>' to the (approval-gated) computer-use tools."""
    m = _CLICK_RE.match(q)
    if m and m.group(1).strip():
        return exact_schema(empty_result(route="tool", intent="click_ui_element", domain="desktop", confidence=0.88, reason="click_ui") | {"slots": {"target": m.group(1).strip(" .?!")}})
    m = _TYPE_RE.match(q)
    if m and m.group(1).strip():
        return exact_schema(empty_result(route="tool", intent="type_text", domain="desktop", confidence=0.85, reason="type_text") | {"slots": {"text": m.group(1).strip()}})
    return None


_TASK_APP_RE = re.compile(
    r"(open (?:the |an |a )?(?:best )?app for|best app for|what app (?:should i use )?for|which app (?:should i use )?for|app for)\s+(.+)$"
)


def _task_app_match(q: str, text: str) -> dict[str, Any] | None:
    """Route 'best app for <task>' / 'open the best app for <task>' before the generic open handler."""
    m = _TASK_APP_RE.search(q)
    if not m:
        return None
    task = m.group(2).strip(" .?!")
    if not task:
        return None
    intent = "open_app_for_task" if m.group(1).startswith("open") else "resolve_app_for_task"
    return exact_schema(empty_result(route="tool", intent=intent, domain="desktop", confidence=0.9, reason="task_app") | {"slots": {"task": task}})


_SKILL_HELP_RES = [
    re.compile(r"^tool help\s+(.+)$"),
    re.compile(r"^describe (?:the )?skill\s+(.+)$"),
    re.compile(r"^describe (?:the )?(.+?)\s+skill$"),
    re.compile(r"^(?:what does|tell me about) (?:the )?(.+?)\s+(?:skill|tool)(?:\s+do)?$"),
]


def _skill_help_match(q: str) -> dict[str, Any] | None:
    """Route 'tool help <x>' / 'describe the <x> skill' / 'what does the <x> tool do' to describe_skill."""
    for rx in _SKILL_HELP_RES:
        m = rx.match(q)
        if m:
            name = m.group(1).strip(" .?!")
            if name:
                return exact_schema(empty_result(route="tool", intent="describe_skill", domain="system", confidence=0.9, reason="skill_help") | {"slots": {"name": name}})
    return None


def _settings_match(q: str) -> dict[str, Any] | None:
    """Match Windows Settings phrases. Longest phrase wins so 'open wifi settings' beats 'settings'."""
    best_intent = ""
    best_len = 0
    for intent, phrases in _SETTINGS_ROUTES.items():
        for phrase in phrases:
            if (q == phrase or f" {phrase} " in f" {q} " or q.startswith(phrase + " ") or q.endswith(" " + phrase)) and len(phrase) > best_len:
                best_intent, best_len = intent, len(phrase)
    if best_intent:
        return empty_result(route="tool", intent=best_intent, domain="system", confidence=0.95, reason="settings_" + best_intent)
    return None


def _has_word(text: str, *words: str) -> bool:
    """Whole-word match, tolerating a trailing plural.

    Short common words must not match as substrings: "handle it" contains "hand"
    and used to start camera gesture control at 0.93 confidence, and "conveyed"
    contains "eye". Prefix matches that are deliberate (e.g. "recogni") stay as
    plain `in` checks.
    """
    return any(re.search(rf"\b{re.escape(word)}s?\b", text) for word in words)


def _spotify_match(q: str, text: str) -> dict[str, Any] | None:
    if "spotify" not in q:
        return None
    if q in {"connect spotify", "link spotify", "authorize spotify", "spotify connect"}:
        return empty_result(route="tool", intent="spotify_connect", domain="web", confidence=1.0, reason="spotify_connect")
    if any(phrase in q for phrase in ("what is playing", "what's playing", "whats playing", "now playing")):
        return empty_result(route="tool", intent="spotify_now_playing", domain="web", confidence=0.98, reason="spotify_now_playing")
    if "device" in q:
        return empty_result(route="tool", intent="spotify_devices", domain="web", confidence=0.98, reason="spotify_devices")
    controls = {
        "pause": "spotify_pause",
        "resume": "spotify_resume",
        "continue": "spotify_resume",
        "next": "spotify_next",
        "skip": "spotify_next",
        "previous": "spotify_previous",
        "back": "spotify_previous",
    }
    for word, intent in controls.items():
        if re.search(rf"\b{word}\b", q):
            return empty_result(route="tool", intent=intent, domain="web", confidence=0.98, reason=intent)
    if "play" not in q:
        return None
    raw = str(text or "").strip()
    kind = "track"
    for candidate in ("playlist", "album", "artist", "track"):
        if re.search(rf"\b{candidate}\b", q):
            kind = candidate
            break
    query = re.sub(r"^\s*(?:spotify\s+play|play)\s+", "", raw, flags=re.I)
    query = re.sub(r"\s+(?:on|in)\s+spotify\s*$", "", query, flags=re.I)
    query = re.sub(r"^\s*(?:a|the|my)?\s*(?:playlist|album|artist|track)\s+", "", query, flags=re.I).strip()
    query = re.sub(r"^spotify\s+", "", query, flags=re.I).strip()
    if not query:
        return exact_schema(empty_result(
            route="clarify",
            intent="spotify_play",
            domain="web",
            confidence=0.98,
            reason="spotify_missing_query",
            clarification_question="What should I play on Spotify?",
        ) | {"missing_slots": ["query"]})
    return exact_schema(empty_result(
        route="tool",
        intent="spotify_play",
        domain="web",
        confidence=0.98,
        reason="spotify_play",
    ) | {"slots": {"query": query, "kind": kind}})


def _deterministic_router(text: str, context: dict | None = None) -> dict[str, Any]:
    q = _norm(text)
    if not q:
        return empty_result(route="clarify", intent="unknown", confidence=1.0, reason="empty_input")

    try:
        from engine.smart_followup_engine import resolve_followup
        followup = resolve_followup(text, context)
        if followup:
            return followup
    except Exception:
        pass

    if q in {"hello", "hi", "hey", "hello there", "hi there"}:
        return empty_result(route="system", intent="greeting", domain="conversation", confidence=1.0, reason="greeting")
    if q in {"bye", "goodbye", "good bye", "see you", "see ya", "see you later", "farewell", "good night", "goodnight"}:
        return empty_result(route="brain", intent="social_close", domain="conversation", confidence=0.97, reason="conversational")
    if q in {"thanks", "thank you", "thank you so much", "thanks a lot", "thankyou", "appreciate it"}:
        return empty_result(route="brain", intent="social_reply", domain="conversation", confidence=0.97, reason="conversational")
    if q in {"who are you", "what is your name", "what's your name", "introduce yourself"}:
        return empty_result(route="system", intent="identity", domain="conversation", confidence=1.0, reason="identity")
    if q in {"repeat", "repeat that", "say that again", "can you repeat that"}:
        return empty_result(route="system", intent="repeat_last", domain="conversation", confidence=1.0, reason="repeat")
    if q in {"what did you understand", "why did you do that", "what rule did you use", "what tool did you choose"}:
        return empty_result(route="system", intent="what_did_you_understand" if q.startswith("what") else "why_did_you_do_that", domain="system", confidence=1.0, reason="intent_explain")

    # ── Early guards: media providers + browser-tab beat generic open/search ─
    _spotify = _spotify_match(q, str(text or ""))
    if _spotify:
        return _spotify
    _yt = _youtube_match(q, str(text or ""))
    if _yt:
        return _yt
    if q in {"open a new tab", "open new tab", "new tab"}:
        return empty_result(route="tool", intent="browser_new_tab", domain="browser", confidence=0.95, reason="browser_new_tab")

    # Explicit Studio authorization must beat the propose-only feature-gap path.
    _studio = _studio_match(q, str(text or ""), source=str((context or {}).get("source") or "unknown"))
    if _studio:
        return _studio

    # Compound executable requests need the ReAct loop before one-action parsers.
    if _react_like(q):
        return empty_result(route="react", intent="react_multi_step", domain="workflow", confidence=0.88, reason="multi_step_task")

    # "build yourself a tool that X" -> actually forge it (must beat the feature-gap
    # parser, which would otherwise log it as a roadmap request instead of building it).
    _forge = _forge_match(q, str(text or ""))
    if _forge:
        return _forge

    # ── Feature-gap, browser write, computer-use, task->app, skill-help and Settings beat the generic open handler ─
    _fg = _feature_gap_match(q, str(text or ""))
    if _fg:
        return _fg
    _bw = _browser_write_match(q)
    if _bw:
        return _bw
    _cu = _computer_use_match(q)
    if _cu:
        return _cu
    _skill_help = _skill_help_match(q)
    if _skill_help:
        return _skill_help
    _task_app = _task_app_match(q, str(text or ""))
    if _task_app:
        return _task_app
    _settings = _settings_match(q)
    if _settings:
        return _settings

    if q in {"open", "launch", "start"}:
        return exact_schema(empty_result(route="clarify", intent="open_app", domain="desktop", confidence=0.92, reason="missing_app", clarification_question="Which app should I open?") | {"missing_slots": ["app_name"]})
    if q.startswith(("open ", "launch ")):
        target = re.sub(r"^(open|launch)\s+", "", str(text or "").strip(), flags=re.I).strip()
        from engine.website_resolver import looks_like_website, resolve_website
        if looks_like_website(target):
            url = target if re.match(r"^[a-z][a-z0-9+.-]*://", target, flags=re.I) else resolve_website(target).get("url", target)
            return exact_schema(empty_result(route="tool", intent="open_website", domain="web", confidence=0.95, reason="open_website") | {"slots": {"url": url}})
        from engine.app_resolver import resolve_app_name
        return exact_schema(empty_result(route="tool", intent="open_app", domain="desktop", confidence=0.95, reason="open_app") | {"slots": {"app_name": resolve_app_name(target).get("app_name", target)}})

    if q in {"search", "google", "search web", "search the web"}:
        return exact_schema(empty_result(route="clarify", intent="web_search", domain="web", confidence=0.92, reason="missing_query", clarification_question="What should I search for?") | {"missing_slots": ["query"]})
    if q.startswith(("search ", "google ")):
        query = re.sub(r"^(search|google)\s+", "", str(text or "").strip(), flags=re.I).strip()
        return exact_schema(empty_result(route="tool", intent="web_search", domain="web", confidence=0.95, reason="web_search") | {"slots": {"query": query}})

    if q.startswith(("remember ", "remember that ")) or q in {"show memory", "what do you remember"}:
        return empty_result(route="memory", intent="remember" if q.startswith("remember") else "recall_memory", domain="memory", confidence=0.94, reason="memory_phrase")

    if q in {"train nexi", "start training", "start training mode", "training mode"}:
        return empty_result(route="training", intent="train_nexi", domain="training", confidence=1.0, reason="training_phrase")
    if q.startswith("train nexi deeply for ") or q.startswith("start ultra training for "):
        return empty_result(route="training", intent="start_ultra_training", domain="training", confidence=1.0, reason="ultra_training_phrase")
    if q.startswith("train nexi for "):
        return empty_result(route="training", intent="train_need_profile", domain="training", confidence=1.0, reason="need_training_phrase")
    if q.startswith(("create training dataset", "simulate training", "run training evaluation", "show training score", "show weak areas", "show training curriculum")):
        return empty_result(route="training", intent="deep_training_command", domain="training", confidence=1.0, reason="deep_training_phrase")
    if q in {"show training rules", "what have you learned", "show training profiles", "show need profiles"}:
        return empty_result(route="memory", intent="show_training_rules" if "rules" in q or "learned" in q else "show_training_profiles", domain="training", confidence=1.0, reason="training_summary")

    if q.startswith(("create folder", "create a folder", "make folder", "new folder")):
        return empty_result(route="workflow", intent="create_folder", domain="workflow", confidence=0.92, reason="folder_workflow")
    if q.startswith(("create file", "create a file", "create text file", "create python file")):
        return empty_result(route="workflow", intent="create_file", domain="workflow", confidence=0.92, reason="file_workflow")

    # ── YouTube play/search handled early via _youtube_match() ───────────────

    # ── Hinglish browser open (chrome/browser kholo) ─────────────────────────
    if q in {"chrome kholo", "browser kholo", "krom kholo", "browzer kholo"}:
        from engine.app_resolver import resolve_app_name
        return exact_schema(empty_result(route="tool", intent="open_app", domain="desktop", confidence=0.95, reason="open_chrome_hi") | {"slots": {"app_name": resolve_app_name("chrome").get("app_name", "chrome")}})
    if q.startswith(("google pe search karo", "google pe dhoondo", "google search karo", "google pe khojo")):
        gq = re.sub(r"^google\s+(pe\s+)?(search karo|dhoondo|khojo|search)\s*", "", q).strip()
        if gq:
            return exact_schema(empty_result(route="tool", intent="web_search", domain="web", confidence=0.93, reason="google_search_hi") | {"slots": {"query": gq}})
        return exact_schema(empty_result(route="clarify", intent="web_search", domain="web", confidence=0.9, reason="missing_query", clarification_question="What should I search for?") | {"missing_slots": ["query"]})

    # ── Simple alias-driven tools (time/joke/weather/media/browser) ──────────
    _weather = _weather_match(q, str(text or ""))
    if _weather:
        return _weather
    _alias_hit = _alias_tool_match(q)
    if _alias_hit:
        return _alias_hit

    if "stop" in q and _has_word(q, "camera", "gesture", "eye", "control"):
        return empty_result(route="tool", intent="stop_camera_control", domain="desktop", confidence=0.95, reason="stop_camera_control")
    if "calibrate" in q and _has_word(q, "eye"):
        return empty_result(route="tool", intent="eye_mouse_calibrate", domain="desktop", confidence=0.95, reason="eye_calibration")
    if _has_word(q, "eye") and ("mouse" in q or "control" in q or "tracking" in q):
        mode = "control" if ("enable" in q or "eye control" in q) and "preview" not in q else "preview"
        return exact_schema(empty_result(route="tool", intent="eye_mouse_control", domain="desktop", confidence=0.93, reason="eye_mouse_control") | {"slots": {"mode": mode}, "risk_level": "high" if mode == "control" else "low", "requires_confirmation": mode == "control"})
    # "gesture" alone is a strong signal; bare "hand" is not ("hand me", "on the
    # other hand"), so it needs gesture/control/tracking context like the eye branch.
    if _has_word(q, "gesture") or (_has_word(q, "hand") and any(w in q for w in ("gesture", "control", "tracking"))):
        mode = "preview" if "preview" in q else "control"
        return exact_schema(empty_result(route="tool", intent="hand_gesture_control", domain="desktop", confidence=0.93, reason="hand_gesture_control") | {"slots": {"mode": mode}, "risk_level": "high" if mode == "control" else "low", "requires_confirmation": mode == "control"})
    if "camera" in q and "preview" in q:
        return empty_result(route="tool", intent="camera_preview", domain="desktop", confidence=0.93, reason="camera_preview")

    if "face" in q and any(word in q for word in ("recogni", "detect", "identify", "who is")):
        mode = "start"
        if any(w in q for w in ("stop", "disable", "off")):
            mode = "stop"
        return exact_schema(empty_result(route="tool", intent="face_recognition", domain="desktop", confidence=0.93, reason="face_recognition") | {"slots": {"mode": mode}})
    if "face" in q and any(word in q for word in ("register", "train", "new face", "add face", "learn face", "teach")):
        name_match = re.search(r"(?:register|train|add|learn|teach)\s+(?:face\s+)?(?:for|as|named?|called?)?\s+(.+)", q)
        name = name_match.group(1).strip(" .?!") if name_match else "User"
        return exact_schema(empty_result(route="tool", intent="face_register", domain="desktop", confidence=0.93, reason="face_register") | {"slots": {"name": name}})

    if _qa_like(q):
        intent = "essay_request" if q.startswith("write ") and "essay" in q else "general_qa"
        return empty_result(route="brain", intent=intent, domain="conversation", confidence=0.86, reason="qa_prefix")

    # NO FEATURE MATCHED. Hand off to the BRAIN only when the input actually reads as
    # conversation or planning ("lets plan something", "help me plan the fix") — the brain
    # is good at those and asks a better question than any canned string.
    #
    # Everything else clarifies. HEAD sent all 2+ word input to the brain, which meant an
    # unmatched ACTION request ("delete that old thing", "install the missing plugin")
    # reached a model that will happily answer as though it had done the thing — Nexi
    # claiming a deletion it never performed. Gibberish ("flibbertigibbet plover") has no
    # signal either and must not be answered as if it meant something. Keying on a
    # conversational signal rather than an action-verb blocklist covers both without a
    # verb list to maintain.
    #
    # Confidence must stay above confidence_manager.should_clarify's 0.65 floor, or
    # route_intent_v2 flips brain back to clarify and this rule does nothing.
    if len(q.split()) > 1 and _BRAIN_SIGNAL_RE.search(q):
        return empty_result(
            route="brain",
            intent="general_qa",
            domain="conversation",
            confidence=0.75,
            reason="no_feature_fallback",
        )

    return empty_result(
        route="clarify",
        intent="unknown",
        domain="unknown",
        confidence=0.6,
        reason="unknown_input",
        clarification_question="I'm not sure what action or answer you want. Could you clarify?",
    )


# ── LLM router (Groq by default; optional xAI Grok) ──────────────────────────
_ROUTE_DESCRIPTIONS: dict[str, str] = {
    "tool": "Execute a PC action via a registered tool (open app, search, create file, etc.). should_call_tool=true.",
    "brain": "Answer a conversation or question via the Gemini brain. should_call_gemini=true.",
    "system": "Internal lifecycle: greeting, identity, status, diagnostics, battery, disk, skills.",
    "memory": "Remember, recall, forget, or manage notes and facts.",
    "training": "Enter or manage Nexi training mode.",
    "output": "Manage the output workspace (pin, copy, save, show, read, shorten, regenerate).",
    "workflow": "Start a multi-step or agent workflow (create folder/file, agent audit, codebase research, test gen, integration plan).",
    "react": "Multi-step reactive task combining several actions.",
    "clarify": "Ask user for missing information when input is ambiguous.",
    "followup": "Continue a previous interaction with context awareness.",
    "sleep": "Put Nexi to sleep.",
    "wake": "Wake Nexi up.",
    "interrupt": "Stop current action immediately.",
    "reject": "Reject a request for safety reasons.",
    "cancel": "Cancel a pending action.",
}

_DOMAIN_DESCRIPTIONS: dict[str, str] = {
    "desktop": "Local PC actions: open app, file ops, camera, eye/hand/gesture control, screen read, click, type.",
    "browser": "Browser tab management: new tab, close, refresh, back, forward, history, fullscreen.",
    "web": "Internet actions: search, open website, YouTube, weather, speed test.",
    "memory": "Remember, recall, forget, notes.",
    "training": "Training mode operations.",
    "output": "Output workspace management.",
    "workflow": "Agent workflows and multi-step tasks.",
    "conversation": "Chat, Q&A, social responses (greeting, thanks, bye, identity).",
    "system": "Internal system queries (diagnostics, battery, disk, skills, HUD, active window, running apps, network).",
    "unknown": "Not yet classified.",
}


def _rag_filter_capabilities(text: str, capabilities: list, k: int = 0) -> list:
    """Tool-RAG (idea #59, RAG-MCP): give the model only the tools that are
    semantically plausible for THIS utterance instead of all 113 (~35KB of JSON).

    Reuses the e5 index the semantic router already built — no new infrastructure.
    Published result: ~3.2x tool-selection accuracy and ~50% fewer prompt tokens,
    because a model asked to pick 1-of-113 picks badly.
    https://arxiv.org/abs/2505.03275

    Degrades to the FULL list whenever the index isn't warm or anything fails —
    a narrowed list that omits the right tool is worse than a long one, and the
    warm check keeps this off the ~83s cold-build path.
    """
    k = k or int(os.getenv("NEXI_TOOL_RAG_TOPK", "12") or 12)
    if not capabilities or k <= 0:
        return capabilities
    try:
        import engine.router as _router_pkg

        router = getattr(_router_pkg, "_ROUTER", None)
        if router is None:
            return capabilities  # not warm — never block a turn to build it
        from engine.router.normalize import normalize

        match = router.semantic.match(normalize(text).canonical)
        wanted = {getattr(c, "intent", "") for c in (match.candidates or [])[:k]}
        wanted.discard("")
        if not wanted:
            return capabilities
        picked = [c for c in capabilities if c.get("name") in wanted]
        if not picked:
            return capabilities
        print(f"[TOOL_RAG] {len(capabilities)} -> {len(picked)} candidates", flush=True)
        return picked
    except Exception:
        return capabilities


def _route_with_llm(text: str, context: dict) -> dict[str, Any] | None:
    if (os.getenv("GROQ_INTENT_V2_ENABLED", "true") or "").strip().lower() in {"0", "false", "no", "off"}:
        return None
    scope = str((context or {}).get("session_id") or (context or {}).get("source") or "default")
    if _llm_rate_limited(scope):
        return None
    try:
        from engine.providers import get_intent_provider

        provider = get_intent_provider()
    except Exception as exc:
        print(f"[INTENT_V2] provider_init_failed reason={type(exc).__name__}", flush=True)
        provider = None
    if provider is None or not provider.is_available():
        return None

    try:
        from engine.tool_manifest_loader import router_capability_manifest

        # Tool-RAG: narrow 113 tools to the semantically plausible few before the
        # model ever sees them (idea #59).
        capabilities = _rag_filter_capabilities(text, router_capability_manifest())
    except Exception:
        capabilities = []

    llm_payload = {
        "text": text,
        "context": context,
        "capabilities": capabilities,
        "route_taxonomy": _ROUTE_DESCRIPTIONS,
        "domain_taxonomy": _DOMAIN_DESCRIPTIONS,
    }

    messages = [
        {"role": "system", "content": _load_prompt()},
        {"role": "user", "content": json.dumps(llm_payload)},
    ]

    from engine.intent_taxonomy import router_decision_schema

    result = None
    timeout = _intent_timeout_seconds()
    for attempt in range(_intent_max_retries() + 1):
        try:
            result = provider.route_with_schema(messages, router_decision_schema(), timeout=timeout)
        except Exception as exc:
            if attempt == _intent_max_retries():
                print(f"[INTENT_V2] provider_failed reason={type(exc).__name__}", flush=True)
                return None
            continue
        if result.ok or result.error_code == "invalid_json" or attempt == _intent_max_retries():
            break
    if result is None:
        return None
    if not result.ok:
        if result.error_code == "invalid_json":
            return empty_result(route="clarify", intent="unknown", confidence=0.0, reason="invalid_json", clarification_question="The routing response was invalid. Could you rephrase your request?")
        # On provider failure, optionally fall back to a secondary provider.
        fallback_name = (os.getenv("INTENT_ROUTER_FALLBACK_PROVIDER", "") or "").strip().lower()
        if fallback_name:
            try:
                from engine.providers import get_intent_provider as _gip

                fb = _gip(fallback_name)
                if fb is not None and fb.is_available():
                    fb_result = fb.route_with_schema(messages, router_decision_schema(), timeout=timeout)
                    if fb_result.ok and fb_result.decision is not None:
                        print(f"[INTENT_V2] fallback_provider={fb.name} used", flush=True)
                        return fb_result.decision
            except Exception:
                pass
        return None
    if result.decision is not None:
        print(f"[INTENT_V2] provider={result.provider} model={result.model} routed", flush=True)
        return result.decision
    return None


# Backwards-compatible alias for older imports/tests.
def _route_with_groq(text: str, context: dict) -> dict[str, Any] | None:
    return _route_with_llm(text, context)


_MASTER_WARMING = False


def _warm_master_router() -> None:
    """Build the tiered Master Router in the BACKGROUND, once.

    Building it loads the e5 embedder, which takes ~83s on first use (and touches
    the HF hub). That must never happen inside a voice turn — it stalled the whole
    dispatch and NEXI sat in "thinking" until the session timed out.
    """
    global _MASTER_WARMING
    if _MASTER_WARMING:
        return
    _MASTER_WARMING = True

    def _build() -> None:
        try:
            import time as _time
            from engine.router import get_router
            started = _time.time()
            get_router()
            print(f"[INTENT_V2] master_router warm in {_time.time() - started:.1f}s", flush=True)
        except Exception as exc:
            print(f"[INTENT_V2] master_warm_failed reason={type(exc).__name__}", flush=True)

    try:
        threading.Thread(target=_build, name="nexi-master-router-warm", daemon=True).start()
    except Exception:
        _MASTER_WARMING = False


def _route_with_master(text: str, context: dict) -> dict[str, Any] | None:
    """Hybrid stage — consult the tiered Master Router (local semantic layer +
    compound splitter + gpt-oss escalation) and return its decision ONLY when it
    is confident enough to act, or it found a multi-step plan.

    Otherwise return None so the legacy Groq seam + deterministic fallback below
    stay in charge. This is the "tiered router is primary, legacy is the automatic
    fallback when the tiered router is unsure" contract. Never raises — any failure
    (missing embedder, import error, provider down) degrades to the legacy router.
    """
    if (os.getenv("NEXI_ROUTER_HYBRID", "1") or "").strip().lower() in {"0", "false", "no", "off"}:
        return None
    try:
        import engine.router as _router_pkg

        # NEVER block the turn on the embedder build (~83s cold). If the router is not
        # warm yet, start warming in the background and let the legacy path answer THIS
        # turn. Once warm, subsequent turns get the semantic tier for free.
        if getattr(_router_pkg, "_ROUTER", None) is None:
            _warm_master_router()
            return None
        decision = _router_pkg.route(text, {"source": str((context or {}).get("source") or "ui")})
        route = decision.route
        intent = decision.intent
        band = getattr(decision, "band", "")
    except Exception as exc:
        print(f"[INTENT_V2] master_unavailable reason={type(exc).__name__}", flush=True)
        return None

    # Human-approval and workflow-control authority never come from a model or a
    # semantic guess — only the deterministic command matchers above may mint them.
    if intent in _MODEL_FORBIDDEN_INTENTS:
        return None
    if route == "react":
        result = dict(decision.result)
        result["confidence"] = max(float(result.get("confidence") or 0.0), 0.9)
        print(f"[INTENT_V2] master route=react tier={getattr(decision, 'tier', '?')} steps={len(getattr(decision, 'plan', []) or [])}", flush=True)
        return result
    if band in {"act", "confirm"} and route in {"tool", "output", "workflow", "memory", "system"}:
        # Guard against low-confidence semantic false positives ("make my screen
        # brighter" -> screen_read): only override the legacy router when the match
        # is strong. Weaker matches fall through so the legacy brain/clarify path
        # handles them gracefully. Floor is on the numpy-fallback sim scale; retune
        # via env when the e5 embedder is enabled (see engine/router/confidence.py).
        sim = float(getattr(decision, "sim", 0.0) or 0.0)
        floor = float(os.getenv("NEXI_ROUTER_HYBRID_MIN_SIM", "0.62") or 0.62)
        tier = int(getattr(decision, "tier", 0) or 0)
        if sim < floor and tier == 0:
            return None
        result = dict(decision.result)
        # Trust the tiered router's calibrated band: it already decided this is an
        # action, so don't let _finalize re-clarify a match on the sim scale.
        result["confidence"] = max(float(result.get("confidence") or 0.0), 0.9)
        print(f"[INTENT_V2] master route={route} intent={intent} band={band} tier={tier} sim={sim}", flush=True)
        return result
    return None


# ── Slot enrichment for deterministic fallback ───────────────────────────────
def _enrich_slots_with_llm(result: dict, text: str) -> dict:
    intent = result.get("intent", "")
    if result.get("route") not in {"tool", "workflow"}:
        return result
    if result.get("slots") and not result.get("missing_slots"):
        return result
    try:
        from engine.llm_parameter_extractor import extract_parameters
        params = extract_parameters(text, intent)
    except Exception:
        return result
    if not params.get("slots") and not params.get("missing"):
        return result
    slots = dict(result.get("slots", {}))
    missing = list(result.get("missing_slots", []))
    existing_slot_names = set(slots.keys())
    for k, v in params.get("slots", {}).items():
        if v is not None and k not in existing_slot_names:
            slots[k] = v
    llm_missing = params.get("missing", [])
    for m in llm_missing:
        if m not in existing_slot_names and m not in slots:
            if m not in missing:
                missing.append(m)
    result = dict(result)
    result["slots"] = slots
    result["missing_slots"] = missing
    return result


# ── Finalize ─────────────────────────────────────────────────────────────────
def _finalize(raw: dict[str, Any], text: str, *, selected_rule: str = "") -> dict[str, Any]:
    from engine.intent_validator import validate_router_result, validate_tool_slots
    from engine.slot_normalizer import normalize_router_result

    result = validate_router_result(raw)
    result = normalize_router_result(result, text=text)
    result = validate_tool_slots(result)

    try:
        from engine.confidence_manager import score_intent_confidence, should_clarify
        missing = bool(result.get("missing_slots"))
        score = score_intent_confidence({
            "base_confidence": result.get("confidence", 0.0),
            "route": result.get("route", ""),
            "missing_slot": missing,
            "tool_slots_complete": result.get("route") == "tool" and not missing,
            "learned_rule_match": bool(selected_rule),
        })
        result["confidence"] = score
        if should_clarify(score, result.get("route", ""), pending_state=result.get("route") in {"followup", "workflow"}) and result.get("route") not in {"reject"}:
            result["route"] = "clarify"
            result["expects_user_reply"] = True
            if not result.get("clarification_question"):
                from engine.confidence_manager import build_clarification_question
                result["clarification_question"] = build_clarification_question(text, intent=result.get("intent", ""), missing_slot=((result.get("missing_slots") or [""])[0] if result.get("missing_slots") else ""))
            result["should_call_tool"] = False
            result["should_call_gemini"] = False
    except Exception:
        pass

    result = validate_router_result(result)
    selected_tool = result.get("intent", "") if result.get("route") == "tool" else ""
    missing_slot = (result.get("missing_slots") or [""])[0] if result.get("missing_slots") else ""
    try:
        from engine.intent_explainer import record_intent_decision
        record_intent_decision(result, selected_tool=selected_tool, selected_rule=selected_rule, missing_slot=missing_slot)
    except Exception:
        pass
    try:
        from engine.presence_state import get_presence
        get_presence().update_mode(
            "thinking",
            attention="tool" if result.get("route") in {"tool", "workflow", "react"} else "user",
            confidence=float(result.get("confidence") or 0.0),
            current_goal=f"route={result.get('route', '')} intent={result.get('intent', '')}",
            last_event="intent_routed",
        )
    except Exception:
        pass
    print(f"[INTENT_V2] route={result.get('route')} intent={result.get('intent')} confidence={result.get('confidence'):.2f}", flush=True)
    return exact_schema(result)


# ── Public entry point ───────────────────────────────────────────────────────
def _deterministic_is_confident(result: dict[str, Any]) -> bool:
    """A deterministic match we trust enough to skip the LLM entirely."""
    route = result.get("route")
    if route in {"clarify", "reject"} or result.get("intent") in {"unknown"}:
        return False
    if route in {"system", "memory", "training", "workflow", "react"}:
        return True
    if route in {"tool", "output"}:
        # Confident only when no slots are missing (e.g. "open chrome", not bare "open").
        return not result.get("missing_slots")
    if route == "brain":
        # general_qa is a soft guess: "what is my battery" LOOKS like a question but
        # is really a tool call. Never let a general_qa guess short-circuit the tiered
        # middle — give it a chance to find the real tool. Social/identity brain
        # replies (social_close, social_reply, …) stay authoritative.
        if result.get("intent") == "general_qa":
            return False
        return float(result.get("confidence") or 0.0) >= 0.85
    return False


def _route_intent_v2_inner(text: str, *, source: str = "ui", context: dict | None = None) -> dict[str, Any]:
    # Kick the tiered router's ~83s embedder build off on the FIRST command so it is
    # ready for later turns. No-op after the first call, and never blocks this turn.
    if (os.getenv("NEXI_ROUTER_HYBRID", "1") or "").strip().lower() not in {"0", "false", "no", "off"}:
        _warm_master_router()

    # Studio commands are explicit authorization and must never be reinterpreted
    # by an LLM or swallowed by an unrelated pending workflow.
    studio = _studio_match(_norm(text), str(text or ""), source=source)
    if studio:
        return _finalize(studio, text)

    inferred = _inferred_build_match(str(text or ""), source=source)
    if inferred:
        return _finalize(inferred, text)

    from engine.intent_context_builder import build_intent_context
    from engine.intent_pre_router import pre_route

    ctx = context or build_intent_context(text, source=source)

    # Stage 1: Pre-route (learned corrections, immediate commands)
    pre = pre_route(text, ctx)
    if pre:
        return _finalize(pre, text)

    # Stage 2: Check for learned corrections
    try:
        from engine.correction_learner import apply_correction
        correction = apply_correction(text)
        if correction.get("matched"):
            action_text = str(correction.get("action_text") or "")
            if action_text:
                routed = _deterministic_router(action_text, ctx)
                if routed.get("intent") not in _STUDIO_INTENTS:
                    return _finalize(routed, action_text, selected_rule=str((correction.get("rule") or {}).get("id") or "correction"))
    except Exception:
        pass

    # Stage 3: Compound / multi-step commands go to the ReAct loop BEFORE any
    # single-action parser can truncate them ("open notepad and type hello" must
    # not collapse into one open_app call). Deterministic + offline — no LLM.
    # Explicit Studio builds are single authorized commands, never react plans.
    if _is_multistep(text) and not explicit_studio_action(str(text or "")):
        return _finalize(empty_result(route="react", intent="react_multi_step", domain="workflow", confidence=0.9, reason="multi_step_task"), text)

    # Stage 4: Confident deterministic matches are authoritative and skip the LLM.
    deterministic = _deterministic_router(text, ctx)
    if _deterministic_is_confident(deterministic):
        return _finalize(deterministic, text)

    # Stage 4b: a deterministic clarify that already knows the exact missing slot
    # (bare "open" / "search") keeps its precise question — it is not handed to
    # the tiered/LLM middle.
    if deterministic.get("route") == "clarify" and deterministic.get("missing_slots") and deterministic.get("intent") not in {"unknown"}:
        return _finalize(deterministic, text)

    # Stage 5: HYBRID — the tiered Master Router (local semantic layer + gpt-oss
    # escalation) is primary for fuzzy language. It takes the wheel only when it is
    # confident enough to act or found a multi-step plan; otherwise the legacy Groq
    # seam + deterministic fallback below stay in charge.
    master = _route_with_master(text, ctx)
    if master is not None:
        return _finalize(master, text)

    # Stage 6: Legacy Groq single-call seam (fallback for the fuzzy middle).
    # It receives the user text, prior context, the complete tool catalog, and
    # route/domain taxonomy, and returns a route/intent/slots in one call.
    llm_raw = _route_with_groq(text, ctx)
    if llm_raw is not None:
        llm_route = llm_raw.get("route", "")
        llm_intent = llm_raw.get("intent", "")
        llm_confidence = float(llm_raw.get("confidence") or 0.0)

        # Human approval and workflow-control authority can only come from exact
        # deterministic command routing above. A model decision is never consent.
        if llm_intent in _MODEL_FORBIDDEN_INTENTS:
            return _finalize(deterministic, text)

        # LLM returned a clear, confident result — return it directly.
        if llm_route not in {"clarify", "unknown", ""} and llm_intent not in {"unknown", "clarify", ""}:
            if llm_confidence >= 0.6:
                return _finalize(llm_raw, text)
            # Low confidence LLM result — check deterministic fallback.
            if _deterministic_is_confident(deterministic):
                return _finalize(deterministic, text)
            # Return LLM's result even if low confidence — brain handles it.
            return _finalize(llm_raw, text)

        # LLM returned clarify/unknown — check deterministic.
        if _deterministic_is_confident(deterministic):
            return _finalize(deterministic, text)
        # Pass LLM's clarify through so the brain gets context.
        return _finalize(llm_raw, text)

    # Stage 7: everything unavailable (rate limit, provider error, disabled) —
    # fall back to deterministic rules, then enrich slots with the LLM if needed.
    enriched = _enrich_slots_with_llm(deterministic, text)
    return _finalize(enriched, text)


_REASONING_PROVIDER_KEYS = ("GROQ_API_KEY", "XAI_API_KEY", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "OLLAMA_HOST")


def _reasoning_available() -> bool:
    """True when a model is actually reachable for the ReAct loop.

    Escalating to react with no provider promises reasoning Nexi cannot deliver:
    the loop would burn the turn and fail. Offline, a precise clarify is the better
    answer, so this fails closed to the pre-existing behaviour.
    """
    if (os.getenv("INTENT_ROUTER_PROVIDER", "") or "").strip().lower() == "none":
        return False
    return any((os.getenv(key) or "").strip() for key in _REASONING_PROVIDER_KEYS)


def _escalate_unknown_to_react(result: dict[str, Any], text: str) -> dict[str, Any]:
    """Admit an unresolved utterance to reasoning -- but only when it is bounded.

    Every path above that finds no confident single action terminates in
    clarify/unknown. That is the router reporting it has no one-shot answer --
    often exactly when the ReAct loop (reason -> act -> observe -> verify) should
    take over. But "unknown + a provider exists" is too blunt a licence: live
    evaluation showed it escalating noise ("zzxq camera blue whatever") and
    handing the loop all ~120 tools. The Cognitive Admission Gate makes that
    decision instead, and returns the capability allowlist the loop may use.

    Deliberately narrow. A precise missing-slot clarify keeps its question
    (bare "open" still asks "open what?"), because those carry a KNOWN intent;
    only a genuine `unknown` is considered. Applied at the public entry point,
    not in _finalize, so react_planner's direct _finalize calls cannot re-enter.
    """
    if (os.getenv("NEXI_REACT_ON_UNKNOWN", "1") or "").strip().lower() in {"0", "false", "no", "off"}:
        return result
    if str(result.get("route") or "") != "clarify" or str(result.get("intent") or "") != "unknown":
        return result
    # A short answer to a pending question must not spawn a reasoning loop.
    try:
        from engine.clarification_manager import has_pending_clarification
        from engine.followup_manager import has_pending_followup

        if has_pending_clarification() or has_pending_followup():
            return result
    except Exception:
        pass

    try:
        from engine.admission_gate import admit, set_admission

        admission = admit(text, reasoning_available=_reasoning_available())
    except Exception:
        return result  # fail closed: any gate failure keeps the clarify
    print(
        f"[ADMISSION] mode={admission.mode} reason={admission.reason} "
        f"allowed={len(admission.allowed_capabilities)} blocked={len(admission.blocked_capabilities)}",
        flush=True,
    )
    if not admission.admits_reasoning:
        # REJECT_UNUSABLE_INPUT / ASK_TARGETED_QUESTION / REQUEST_APPROVAL all
        # keep the existing clarify, which already asks the user something.
        return result
    # Hand the loop its bounded capability set.
    set_admission(text, admission.allowed_capabilities)

    escalated = exact_schema(empty_result(
        route="react",
        intent="react_multi_step",
        domain="workflow",
        confidence=0.7,
        reason="unknown_escalated_to_react",
    ))
    print("[INTENT_V2] escalate unknown -> react", flush=True)
    try:
        from engine.intent_explainer import record_intent_decision

        record_intent_decision(escalated, selected_tool="", selected_rule="", missing_slot="")
    except Exception:
        pass
    return escalated


def route_intent_v2(text: str, *, source: str = "ui", context: dict | None = None) -> dict[str, Any]:
    return _escalate_unknown_to_react(
        _route_intent_v2_inner(text, source=source, context=context), text
    )


def classify_intent_v2(text: str, *, source: str = "ui", context: dict | None = None) -> dict[str, Any]:
    return route_intent_v2(text, source=source, context=context)
