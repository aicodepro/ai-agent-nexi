"""Master-flow routing acceptance dataset.

Proves the Unified-Intent-Orchestrator contract on a curated command set:
feature / brain / clarify / approval_required / reject / feature_gap / workflow / interrupt.

Route mapping (router value -> canonical category):
  tool      -> feature  (or feature_gap when intent == request_feature)
  brain     -> brain
  clarify   -> clarify / noise
  workflow  -> workflow
  interrupt/sleep/wake/cancel -> interrupt (handled by intent_pre_router)
Approval-required is enforced at EXECUTION (gated tools queue), tested separately.
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

from engine.groq_intent_router_v2 import _deterministic_router
from engine.intent_pre_router import pre_route
from engine.tool_registry import execute_tool
from engine import approval_queue as aq


def _route(p):
    return _deterministic_router(p, {})


# (phrase, expected_route, expected_intent_or_None)
DATASET = [
    # chat / goodbye -> brain
    ("bye", "brain", "social_close"),
    ("goodbye", "brain", "social_close"),
    ("see you later", "brain", "social_close"),
    ("good night", "brain", "social_close"),
    ("thanks", "brain", "social_reply"),
    ("thank you", "brain", "social_reply"),
    # planning / debugging / explanation (long) -> brain
    ("the intent system is broken help me plan the fix", "brain", "general_qa"),
    ("explain why intent routing keeps failing", "brain", "general_qa"),
    ("what is docker and how does it work", "brain", "general_qa"),
    # read-only features -> tool
    ("what apps are running", "tool", "get_running_apps"),
    ("how long have i been idle", "tool", "get_idle_time"),
    ("show hud", "tool", "get_hud_state"),
    ("read my screen", "tool", "screen_read"),
    ("am i online", "tool", "am_i_online"),
    ("whats my ip", "tool", "get_ip_address"),
    ("what wifi am i on", "tool", "get_network_status"),
    ("how much battery do i have", "tool", "get_battery_status"),
    ("how much disk space do i have", "tool", "get_disk_space"),
    ("what is my system status", "tool", "get_system_state"),
    ("why is my pc slow", "tool", "why_is_pc_slow"),
    ("show diagnostics", "tool", "show_diagnostics"),
    ("what are you monitoring", "tool", "get_monitor_state"),
    ("are you in cooldown", "tool", "echo_guard_status"),
    ("what did you learn", "tool", "what_did_you_learn"),
    ("list my tabs", "tool", "list_browser_tabs"),
    ("read this page", "tool", "read_current_page"),
    ("check console errors", "tool", "read_browser_console"),
    ("what can you do", "tool", "list_skills"),
    ("tool help battery", "tool", "describe_skill"),
    ("best app for coding", "tool", "resolve_app_for_task"),
    # write / approval features -> tool (approval enforced at exec)
    ("click the submit button", "tool", "click_ui_element"),
    ("type out hello world", "tool", "type_text"),
    ("click the login link", "tool", "browser_click"),
    ("fill the search field with python", "tool", "browser_fill"),
    # settings / app / workflow
    ("open wifi settings", "tool", "open_wifi_settings"),
    ("open camera settings", "tool", "open_camera_settings"),
    ("windows update", "tool", "open_windows_update"),
    ("open the best app for coding", "tool", "open_app_for_task"),
    ("create folder on desktop", "workflow", "create_folder"),
    ("create a file called notes", "workflow", "create_file"),
    # feature_gap -> request_feature
    ("build a tool that watches my downloads", "tool", "request_feature"),
    ("create a github issue monitor", "tool", "request_feature"),
    ("i need an automation that backs up my files", "tool", "request_feature"),
    # no feature matched: hand to the brain ONLY when it reads as conversation/planning.
    # A bare action request with no matching tool must clarify -- routed to the brain, Nexi
    # answers as though it performed an action it never performed ("close this" -> "closed
    # it"). See _BRAIN_SIGNAL_RE in groq_intent_router_v2.
    ("close this", "clarify", "unknown"),
    ("do that thing", "clarify", "unknown"),
    ("lets plan something", "brain", "general_qa"),
    # lone unmatched token = ASR noise -> clarify; explicit missing-slot -> clarify
    ("blorp", "clarify", "unknown"),
    ("open", "clarify", "open_app"),
    ("search", "clarify", "web_search"),
]

FEATURE_PHRASES = [p for p, r, i in DATASET if r in ("tool", "workflow")]
BRAIN_PHRASES = [p for p, r, i in DATASET if r == "brain"]


@pytest.mark.parametrize("phrase,route,intent", DATASET, ids=[d[0] for d in DATASET])
def test_route_matches(phrase, route, intent):
    r = _route(phrase)
    assert r.get("route") == route, f"{phrase!r}: route {r.get('route')} != {route}"
    if intent is not None:
        assert r.get("intent") == intent, f"{phrase!r}: intent {r.get('intent')} != {intent}"


def test_accuracy_target():
    correct = sum(1 for p, route, intent in DATASET
                  if _route(p).get("route") == route
                  and (intent is None or _route(p).get("intent") == intent))
    acc = correct / len(DATASET)
    assert acc >= 0.95, f"routing accuracy {acc:.2%} < 95%"


def test_no_feature_command_leaks_to_brain():
    for p in FEATURE_PHRASES:
        assert _route(p).get("route") != "brain", f"feature {p!r} leaked to brain"


def test_no_brain_query_goes_to_clarify():
    for p in BRAIN_PHRASES:
        assert _route(p).get("route") != "clarify", f"brain {p!r} went to clarify"


@pytest.mark.parametrize("phrase,expected", [
    ("stop", "interrupt"), ("sleep", "sleep"), ("go to sleep", "sleep"),
    ("cancel", "cancel"), ("wake up", "wake"),
])
def test_interrupts_handled_by_pre_router(phrase, expected):
    r = pre_route(phrase, {})
    assert r is not None and r.get("route") == expected, f"{phrase!r} -> {r}"


@pytest.mark.parametrize("name,slots", [
    ("click_ui_element", {"target": "Submit"}),
    ("type_text", {"text": "hello"}),
    ("browser_click", {"target": "Login"}),
    ("browser_fill", {"field": "q", "value": "x"}),
])
def test_critical_actions_require_approval(monkeypatch, name, slots):
    # Disable the LLM safety gate so this tests the APPROVAL contract only. The gate calls
    # the Groq safety model over the network and fails closed without GROQ_API_KEY, which
    # blocks the action before it ever reaches the approval queue. This test used to pass
    # only because engine/command.py's import-time load_dotenv() leaked the real key into
    # os.environ — i.e. it was making a live safety-API call on every run.
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "false")
    aq.clear()
    r = execute_tool(name, slots)
    assert r.get("requires_approval") is True, f"{name} executed without approval: {r}"
    assert r.get("verified") is not True
    aq.clear()


def test_safety_gate_fails_closed_without_a_provider(monkeypatch):
    """No key must mean blocked, never silently allowed."""
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setenv("SAFETY_GATE_ENABLED", "true")
    from engine.safety_gate import execution_is_safe

    decision = execution_is_safe("click_ui_element", {"target": "OK"}, user_text="click ok")
    assert decision["allowed"] is False
    assert decision["category"] == "safety_unavailable"


def test_feature_gap_creates_request_not_refusal():
    for p in ("build a tool that watches my downloads", "create a github issue monitor"):
        assert _route(p).get("intent") == "request_feature", f"{p!r} not routed to feature request"
