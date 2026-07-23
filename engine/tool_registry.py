from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Callable, Any


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    examples: list[str]
    required_slots: list[str]
    optional_slots: list[str]
    safety: str
    requires_confirmation: bool
    handler: str
    aliases: tuple[str, ...] = ()
    category: str = "general"
    enabled: bool = True

    def to_openai_schema(self) -> dict[str, Any]:
        properties = {}
        for slot in self.required_slots:
            properties[slot] = {"type": "string", "description": f"Required: {slot}"}
        for slot in self.optional_slots:
            properties[slot] = {"type": "string", "description": f"Optional: {slot}"}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": list(self.required_slots),
                },
            },
        }


def _spec(name: str, description: str, required: list[str] | None = None, safety: str = "low", confirm: bool = False, handler: str = "", aliases: tuple[str, ...] = (), examples: list[str] | None = None, optional: list[str] | None = None, category: str = "general", enabled: bool = True) -> ToolSpec:
    return ToolSpec(name, description, examples or [], required or [], optional or [], safety, confirm or safety in {"high", "critical"}, handler, aliases, category, enabled)


_TOOLS: dict[str, ToolSpec] = {
    "open_app": _spec("open_app", "Open a Windows application", ["app_name"], handler="engine.local_skills.open_app"),
    "open_website": _spec("open_website", "Open a website", ["url"], handler="engine.local_skills.open_website"),
    "web_search": _spec("web_search", "Search the web", ["query"], handler="engine.local_skills.web_search"),
    "create_folder": _spec("create_folder", "Create a folder", ["folder_name"], safety="medium"),
    "create_project_folder": _spec("create_project_folder", "Create a project folder", ["folder_name"], safety="medium"),
    "create_file": _spec("create_file", "Create a file", ["file_name"], optional=["content"], safety="medium"),
    "take_screenshot": _spec("take_screenshot", "Take a screenshot"),
    "take_note": _spec("take_note", "Take a note", ["text"]),
    "show_notes": _spec("show_notes", "Show saved notes"),
    "remember": _spec("remember", "Remember a fact", ["text"]),
    "recall_memory": _spec("recall_memory", "Recall memory", optional=["query"]),
    "forget_memory": _spec("forget_memory", "Forget memory", ["text"], safety="medium", confirm=True),
    "open_output_workspace": _spec("open_output_workspace", "Open Nexi Output Workspace"),
    "close_output_workspace": _spec("close_output_workspace", "Close Nexi Output Workspace"),
    "minimize_output_workspace": _spec("minimize_output_workspace", "Minimize Nexi Output Workspace"),
    "pin_output_workspace": _spec("pin_output_workspace", "Pin Nexi Output Workspace"),
    "copy_latest_output": _spec("copy_latest_output", "Copy latest Nexi output"),
    "save_latest_output": _spec("save_latest_output", "Save latest Nexi output", ["file_name"], safety="medium"),
    "create_file_from_latest_output": _spec("create_file_from_latest_output", "Create a file from latest Nexi output", ["file_name"], safety="medium"),
    "show_latest_output": _spec("show_latest_output", "Show latest Nexi output"),
    "read_output_summary": _spec("read_output_summary", "Read latest output summary"),
    "shorten_latest_output": _spec("shorten_latest_output", "Shorten latest Nexi output"),
    "regenerate_latest_output": _spec("regenerate_latest_output", "Regenerate latest Nexi output"),
    "volume_up": _spec("volume_up", "Increase volume"),
    "volume_down": _spec("volume_down", "Decrease volume"),
    "mute": _spec("mute", "Mute audio"),
    "sleep": _spec("sleep", "Put Nexi to sleep"),
    "wake": _spec("wake", "Wake Nexi"),
    "repeat_last": _spec("repeat_last", "Repeat last answer"),
    "system_status": _spec("system_status", "Show Nexi system status"),
    "clipboard_read": _spec("clipboard_read", "Read clipboard", safety="medium"),
    "clipboard_write_safe": _spec("clipboard_write_safe", "Write clipboard", ["text"], safety="high", confirm=True),
    "camera_preview": _spec("camera_preview", "Start camera preview", handler="engine.camera_control.start_camera_preview"),
    "hand_gesture_control": _spec("hand_gesture_control", "Start hand gesture control", ["mode"], safety="high", confirm=True, handler="engine.camera_control.start_hand_gesture_control"),
    "eye_mouse_control": _spec("eye_mouse_control", "Start eye mouse control", ["mode"], safety="high", confirm=True, handler="engine.camera_control.start_eye_mouse_control"),
    "stop_camera_control": _spec("stop_camera_control", "Stop camera, hand, and eye control", handler="engine.camera_control.stop_all_controls"),
    "gesture_click_mode": _spec("gesture_click_mode", "Enable gesture click mode", safety="high", confirm=True),
    "gesture_scroll_mode": _spec("gesture_scroll_mode", "Enable gesture scroll mode", safety="medium"),
    "eye_mouse_calibrate": _spec("eye_mouse_calibrate", "Calibrate eye mouse", handler="engine.camera_control.calibrate_eye_mouse"),
    "face_recognition": _spec("face_recognition", "Start or check face recognition status", optional=["mode"], handler="engine.camera_control.start_face_recognition"),
    "face_register": _spec("face_register", "Register a new face for recognition", ["name"], safety="medium", handler="engine.camera_control.register_face"),
    # ── Browser / web / media features migrated from legacy dispatch_intent ──
    "search_youtube": _spec("search_youtube", "Search or play a video on YouTube", ["query"], handler="engine.features.PlayYoutube", aliases=("search youtube", "youtube search", "play on youtube", "play youtube", "youtube pe search karo", "youtube pe dhoondo"), examples=["play lofi on yt", "search youtube for python tutorial", "youtube pe search karo cats"], category="web"),
    "play_youtube": _spec("play_youtube", "Play media on YouTube", ["query"], handler="engine.features.PlayYoutube", aliases=("play youtube", "youtube play"), examples=["play despacito on youtube"], category="web"),
    # safety="high" (not medium): this generates and installs executable code. medium
    # never reaches approval_queue, so a single unconfirmed utterance could forge a tool.
    # Removing a forged tool already required confirm; creating one must too.
    "nexi_forge_tool": _spec("nexi_forge_tool", "Build Nexi a brand new tool for a capability she does not have yet", ["spec"], safety="high", handler="engine.forge.forge_engine.nexi_forge_tool", aliases=("build yourself a tool", "forge a tool", "make yourself a tool", "write yourself a tool", "create a new tool for yourself", "you dont have that tool build it"), examples=["build yourself a tool that converts celsius to fahrenheit", "forge a tool that counts words in a string"], category="system"),
    "nexi_list_forged_tools": _spec("nexi_list_forged_tools", "List the tools Nexi has built for herself", handler="engine.forge.forge_engine.nexi_list_forged_tools", aliases=("what tools have you built", "list your forged tools", "what tools did you make yourself", "show your forged tools"), examples=["what tools have you built for yourself"], category="system"),
    "nexi_remove_tool": _spec("nexi_remove_tool", "Remove a tool Nexi previously built for herself", ["name"], safety="medium", confirm=True, handler="engine.forge.forge_engine.nexi_remove_tool", aliases=("remove the forged tool", "delete the tool you built", "uninstall your tool"), examples=["remove the forged tool called add_numbers"], category="system"),
    "which_model": _spec("which_model", "Report which AI model Nexi picked for each task and why", optional=["live"], handler="engine.model_registry.which_model", aliases=("which model are you using", "what model do you use", "which ai model", "what models can you use", "research the models", "research the ai models", "what model are you using for that"), examples=["which model are you using", "what models can you use", "research the ai models"], category="system"),
    "tell_time": _spec("tell_time", "Tell the current time", aliases=("what time is it", "current time", "time now", "tell me the time"), examples=["what time is it", "tell me the time"], category="system"),
    "tell_joke": _spec("tell_joke", "Tell a joke", aliases=("tell a joke", "make me laugh", "crack a joke"), examples=["tell me a joke", "make me laugh"], category="conversation"),
    "weather_lookup": _spec("weather_lookup", "Look up the weather", optional=["location"], aliases=("weather", "whats the weather", "weather today", "temperature"), examples=["what's the weather", "weather in london"], category="web"),
    "internet_speed_test": _spec("internet_speed_test", "Run an internet speed test", aliases=("internet speed", "speed test", "check internet speed", "network speed"), examples=["check my internet speed", "run a speed test"], category="system"),
    "get_active_window": _spec("get_active_window", "Report the currently active app and window", handler="engine.os_awareness.get_active_window", aliases=("which app is active", "what app is active", "active window", "what app am i using", "current app", "what app is open"), examples=["which app is active", "what app is open"], category="system"),
    "what_am_i_working_on": _spec("what_am_i_working_on", "Describe what the user is currently working on", handler="engine.os_awareness.what_am_i_working_on", aliases=("what am i working on", "what am i doing", "what am i up to"), examples=["what am i working on", "what am i doing"], category="system"),
    "get_system_state": _spec("get_system_state", "Report CPU, memory, battery and uptime", handler="engine.os_awareness.get_system_state", aliases=("system status", "pc status", "system state", "how is my pc", "computer status", "resource usage", "how is my computer"), examples=["what's my system status", "how is my pc doing"], category="system"),
    "why_is_pc_slow": _spec("why_is_pc_slow", "Explain what is using the most CPU and memory", handler="engine.os_awareness.why_is_pc_slow", aliases=("why is my pc slow", "why is my computer slow", "what is slowing my pc", "whats using my cpu", "what is using memory", "why is it lagging", "why is my pc lagging"), examples=["why is my pc slow", "what's slowing my computer"], category="system"),
    "am_i_online": _spec("am_i_online", "Check whether the internet is reachable", handler="engine.net_awareness.am_i_online", aliases=("am i online", "do i have internet", "are we connected", "is the internet working", "is the internet up"), examples=["am i online", "do i have internet"], category="system"),
    "get_network_status": _spec("get_network_status", "Report online state, active interface and Wi-Fi network", handler="engine.net_awareness.get_network_status", aliases=("network status", "wifi status", "what network am i on", "what wifi am i on", "connection status", "am i on wifi"), examples=["network status", "what wifi am i on"], category="system"),
    "get_ip_address": _spec("get_ip_address", "Report the local IP address of this PC", handler="engine.net_awareness.get_ip_address", aliases=("what is my ip address", "my ip address", "whats my ip", "what is my ip", "ip address", "show my ip"), examples=["what is my ip address", "what's my ip"], category="system"),
    "get_disk_space": _spec("get_disk_space", "Report free and total disk space on the system drive", handler="engine.storage_awareness.get_disk_space", aliases=("how much disk space do i have", "disk space", "how much storage do i have", "how much space do i have", "free disk space", "storage space"), examples=["how much disk space do i have", "disk space"], category="system"),
    "is_disk_full": _spec("is_disk_full", "Check whether any fixed drive is running low on space", handler="engine.storage_awareness.is_disk_full", aliases=("is my disk full", "is my drive full", "am i running out of space", "is my storage full", "is my disk almost full", "running low on space"), examples=["is my disk full", "am i running out of space"], category="system"),
    "get_battery_status": _spec("get_battery_status", "Report battery percentage, charging state and time remaining", handler="engine.storage_awareness.get_battery_status", aliases=("battery status", "how much battery do i have", "am i charging", "battery level", "whats my battery", "how is my battery"), examples=["battery status", "how much battery do i have"], category="system"),
    "get_running_apps": _spec("get_running_apps", "List the user-facing apps currently running", handler="engine.os_awareness.get_running_apps", aliases=("what apps are running", "list running apps", "running apps", "what programs are open", "what is running", "show running apps", "whats running"), examples=["what apps are running", "list running apps"], category="system"),
    "get_idle_time": _spec("get_idle_time", "Report how long since the user last used the keyboard or mouse", handler="engine.os_awareness.get_idle_time", aliases=("how long have i been idle", "idle time", "how long was i away", "am i idle", "how long have i been away", "how long was i idle"), examples=["how long have i been idle", "idle time"], category="system"),
    "open_settings": _spec("open_settings", "Open the Windows Settings app", handler="engine.windows_settings.open_settings", aliases=("open settings", "open windows settings", "windows settings"), examples=["open settings", "open windows settings"], category="system"),
    "open_wifi_settings": _spec("open_wifi_settings", "Open Wi-Fi settings", handler="engine.windows_settings.open_wifi_settings", aliases=("open wifi settings", "wifi settings", "open wi-fi settings", "network settings"), examples=["open wifi settings"], category="system"),
    "open_bluetooth_settings": _spec("open_bluetooth_settings", "Open Bluetooth settings", handler="engine.windows_settings.open_bluetooth_settings", aliases=("open bluetooth settings", "bluetooth settings", "open bluetooth"), examples=["open bluetooth settings"], category="system"),
    "open_display_settings": _spec("open_display_settings", "Open display settings", handler="engine.windows_settings.open_display_settings", aliases=("open display settings", "display settings", "screen settings"), examples=["open display settings"], category="system"),
    "open_sound_settings": _spec("open_sound_settings", "Open sound settings", handler="engine.windows_settings.open_sound_settings", aliases=("open sound settings", "sound settings", "audio settings"), examples=["open sound settings"], category="system"),
    "open_microphone_settings": _spec("open_microphone_settings", "Open microphone privacy settings", handler="engine.windows_settings.open_microphone_settings", aliases=("open microphone settings", "microphone settings", "mic settings", "open mic settings"), examples=["open microphone settings"], category="system"),
    "open_camera_settings": _spec("open_camera_settings", "Open camera privacy settings", handler="engine.windows_settings.open_camera_settings", aliases=("open camera settings", "camera settings", "webcam settings"), examples=["open camera settings"], category="system"),
    "open_startup_settings": _spec("open_startup_settings", "Open startup apps settings", handler="engine.windows_settings.open_startup_settings", aliases=("open startup apps", "startup apps", "open startup settings", "startup settings"), examples=["open startup apps"], category="system"),
    "open_windows_update": _spec("open_windows_update", "Open Windows Update", handler="engine.windows_settings.open_windows_update", aliases=("open windows update", "windows update", "check for updates"), examples=["open windows update"], category="system"),
    "open_settings_page": _spec("open_settings_page", "Open a specific Windows Settings page by name", optional=["page"], handler="engine.windows_settings.open_settings_page", examples=["open the storage settings page"], category="system"),
    "show_diagnostics": _spec("show_diagnostics", "Show Nexi voice/runtime diagnostics", handler="engine.runtime_awareness.show_diagnostics", aliases=("show diagnostics", "voice diagnostics", "show voice diagnostics", "diagnostics", "run diagnostics", "system diagnostics"), examples=["show diagnostics", "voice diagnostics"], category="system"),
    "get_monitor_state": _spec("get_monitor_state", "Report what Nexi's background monitor is tracking", handler="engine.runtime_awareness.get_monitor_state", aliases=("monitor state", "monitor status", "what are you monitoring", "show monitor", "world monitor", "dashboard state"), examples=["monitor state", "what are you monitoring"], category="system"),
    "echo_guard_status": _spec("echo_guard_status", "Report the echo / self-TTS guard cooldown state", handler="engine.runtime_awareness.echo_guard_status", aliases=("echo guard status", "are you in cooldown", "tts cooldown", "echo status", "cooldown status"), examples=["echo guard status", "are you in cooldown"], category="system"),
    "get_hud_state": _spec("get_hud_state", "Report Nexi's HUD / presence state (mode, focus, goal)", handler="engine.runtime_awareness.get_hud_state", aliases=("show hud", "hud state", "command center", "your current state", "what is your current state", "show your status"), examples=["show hud", "hud state"], category="system"),
    "what_did_you_learn": _spec("what_did_you_learn", "Report lessons Nexi has learned from past failures", handler="engine.runtime_awareness.what_did_you_learn", aliases=("what did you learn", "what did you learn from that", "show your lessons", "what lessons do you have", "reflection memory", "what mistakes have you learned from"), examples=["what did you learn", "show your lessons"], category="system"),
    "list_skills": _spec("list_skills", "List what Nexi can do (capability catalog by area)", handler="engine.skill_library.list_skills", aliases=("what can you do", "list your skills", "what are your skills", "show skills", "list skills", "what can you help with", "list capabilities", "what skills do you have", "show your skills"), examples=["what can you do", "list your skills"], category="system"),
    "describe_skill": _spec("describe_skill", "Explain a specific Nexi skill (what it does, example, risk)", optional=["name"], handler="engine.skill_library.describe_skill", examples=["tool help battery", "describe the camera skill"], category="system"),
    "read_current_page": _spec("read_current_page", "Read the current browser page (title, URL, text)", handler="engine.browser_intelligence.read_current_page", aliases=("read this page", "read the page", "read current page", "summarize this page", "summarize the page", "whats on this page", "what is on this page", "read my browser"), examples=["read this page", "summarize this page"], category="web"),
    "list_browser_tabs": _spec("list_browser_tabs", "List the open browser tabs", handler="engine.browser_intelligence.list_browser_tabs", aliases=("list my tabs", "what tabs are open", "show my tabs", "list browser tabs", "what tabs do i have", "how many tabs"), examples=["list my tabs", "what tabs are open"], category="web"),
    "read_browser_console": _spec("read_browser_console", "Read the browser console messages/errors", handler="engine.browser_intelligence.read_browser_console", aliases=("read the console", "check console errors", "browser console", "console errors", "check the console", "any console errors"), examples=["check console errors", "read the console"], category="web"),
    "pending_approvals": _spec("pending_approvals", "List actions waiting for your approval", handler="engine.approval_queue.pending_approvals", aliases=("pending approvals", "show approvals", "show pending approvals", "what needs approval", "pending actions", "approval queue"), examples=["pending approvals", "what needs approval"], category="system"),
    "approve_action": _spec("approve_action", "Approve the pending action", optional=["id"], handler="engine.approval_queue.approve_action", aliases=("approve", "approve action", "approve that", "approve it", "yes approve", "approve the action"), examples=["approve", "approve action"], category="system"),
    "reject_action": _spec("reject_action", "Reject the pending action", optional=["id"], handler="engine.approval_queue.reject_action", aliases=("reject", "reject action", "reject that", "reject it", "deny action", "cancel the action"), examples=["reject", "reject action"], category="system"),
    "screen_read": _spec("screen_read", "Read visible text/UI on the screen", handler="engine.computer_use.screen_read", aliases=("read my screen", "read the screen", "read screen", "whats on my screen", "what is on my screen", "what is on the screen"), examples=["read my screen", "what's on my screen"], category="desktop"),
    "click_ui_element": _spec("click_ui_element", "Click a UI element by name (needs approval)", optional=["target"], safety="high", handler="engine.computer_use.click_ui_element", examples=["click the submit button"], category="desktop"),
    "type_text": _spec("type_text", "Type text into the focused field (needs approval)", optional=["text"], safety="high", handler="engine.computer_use.type_text", examples=["type out hello world"], category="desktop"),
    "browser_click": _spec("browser_click", "Click an element in the browser page (needs approval)", optional=["target"], safety="high", handler="engine.browser_intelligence.browser_click", examples=["click the login link"], category="web"),
    "browser_fill": _spec("browser_fill", "Fill a field in the browser page (needs approval)", optional=["field", "value"], safety="high", handler="engine.browser_intelligence.browser_fill", examples=["fill the search field with python"], category="web"),
    "request_feature": _spec("request_feature", "Log a request for a capability Nexi does not have yet", optional=["capability"], handler="engine.feature_requests.request_feature", examples=["build a tool that watches my downloads"], category="system"),
    "list_feature_requests": _spec("list_feature_requests", "List logged feature requests", handler="engine.feature_requests.list_feature_requests", aliases=("list feature requests", "show feature requests", "pending features", "what features did i request"), examples=["list feature requests"], category="system"),
    "nexi_run_router_audit": _spec("nexi_run_router_audit", "Run a background Nexi agent audit of the intent router", optional=["goal"], handler="engine.agency.nexi_run_router_audit", aliases=("run an agent audit of the router", "start an agent audit of the intent router", "agent audit of the intent router", "audit the router with agents", "run router audit workflow"), examples=["start an agent audit of the intent router"], category="workflow"),
    "nexi_run_codebase_research": _spec("nexi_run_codebase_research", "Run a background Nexi agent codebase-research workflow", optional=["goal"], handler="engine.agency.nexi_run_codebase_research", aliases=("research this repo with agents", "run codebase research", "research the codebase with agents", "agent research workflow"), examples=["research this repo with agents"], category="workflow"),
    "nexi_run_test_generation": _spec("nexi_run_test_generation", "Run a background Nexi agent test-generation workflow", optional=["goal"], handler="engine.agency.nexi_run_test_generation", aliases=("generate tests with agents", "run test generation workflow", "agent test generation"), examples=["generate tests with agents"], category="workflow"),
    "nexi_run_integration_plan": _spec("nexi_run_integration_plan", "Run a background Nexi agent integration-plan workflow", optional=["goal"], handler="engine.agency.nexi_run_integration_plan", aliases=("create an integration plan", "run integration plan workflow", "plan the integration with agents"), examples=["create an integration plan"], category="workflow"),
    "nexi_workflow_status": _spec("nexi_workflow_status", "Report the status of the current/last agent workflow", optional=["run_id"], handler="engine.agency.nexi_workflow_status", aliases=("workflow status", "show workflow status", "agent workflow status", "whats the workflow status"), examples=["workflow status"], category="workflow"),
    "nexi_agent_activity": _spec("nexi_agent_activity", "Show what the Nexi agents are doing right now", handler="engine.agency.nexi_agent_activity", aliases=("show current agent activity", "agent activity", "current agent activity", "show agent activity", "what are the agents doing"), examples=["show current agent activity"], category="workflow"),
    "nexi_workflow_logs": _spec("nexi_workflow_logs", "Show logs of the current/last agent workflow", optional=["run_id"], handler="engine.agency.nexi_workflow_logs", aliases=("workflow logs", "show workflow logs", "agent logs", "show agent logs", "agent workflow logs"), examples=["show agent logs"], category="workflow"),
    "nexi_workflow_artifacts": _spec("nexi_workflow_artifacts", "Show the latest agent report/artifacts", optional=["run_id"], handler="engine.agency.nexi_workflow_artifacts", aliases=("show the agent report", "latest agent report", "show latest agent report", "agent reports", "workflow artifacts", "workflow report"), examples=["show the latest agent report"], category="workflow"),
    "nexi_cancel_workflow": _spec("nexi_cancel_workflow", "Cancel the current/last agent workflow", optional=["run_id"], handler="engine.agency.nexi_cancel_workflow", aliases=("cancel workflow", "cancel the workflow", "cancel agent workflow", "stop the agent workflow"), examples=["cancel workflow"], category="workflow"),
    "nexi_continue_workflow": _spec("nexi_continue_workflow", "Resume a paused agent workflow", optional=["input", "run_id"], handler="engine.agency.nexi_continue_workflow", aliases=("continue workflow", "continue the agent workflow", "resume workflow", "resume the agent workflow"), examples=["continue the agent workflow"], category="workflow"),
    "nexi_start_studio_build": _spec("nexi_start_studio_build", "Start the opt-in Nexi Studio product team for an explicitly authorized build", ["command"], safety="high", optional=["goal", "project_dir"], handler="engine.agency.nexi_start_studio_build", aliases=("let's build", "lets build", "studio mode", "exotic mode"), examples=["let's build a coffee brand landing page", "studio mode: build a personal finance app"], category="workflow", enabled=False),
    "nexi_studio_status": _spec("nexi_studio_status", "Report the current or latest Nexi Studio build status", optional=["run_id"], handler="engine.agency.nexi_studio_status", aliases=("studio status", "studio build status"), examples=["studio status"], category="workflow"),
    "nexi_cancel_studio_build": _spec("nexi_cancel_studio_build", "Cancel the current Nexi Studio build", optional=["run_id"], handler="engine.agency.nexi_cancel_studio_build", aliases=("cancel studio", "stop studio build"), examples=["cancel studio"], category="workflow"),
    "nexi_continue_studio_build": _spec("nexi_continue_studio_build", "Answer the one blocking question and resume Nexi Studio", ["answer"], optional=["run_id"], handler="engine.agency.nexi_continue_studio_build", aliases=("continue studio", "resume studio build"), examples=["studio continue: use Stripe"], category="workflow", enabled=False),
    "nexi_agent_runtime_status": _spec("nexi_agent_runtime_status", "Report configured agent runtimes and connection capabilities", optional=["provider"], handler="engine.agent_runtime.tools.runtime_status_tool", aliases=("agent runtime status", "ai agent status", "which coding agent are you using", "show agent providers"), examples=["agent runtime status", "show agent providers"], category="workflow"),
    "resolve_app_for_task": _spec("resolve_app_for_task", "Pick the best app for a task (e.g. coding, presentation) with confidence", optional=["task"], handler="engine.app_intelligence.resolve_app_for_task", examples=["what's the best app for coding", "which app for presentation"], category="desktop"),
    "open_app_for_task": _spec("open_app_for_task", "Open the best app for a task", optional=["task"], handler="engine.app_intelligence.open_app_for_task", examples=["open the best app for coding"], category="desktop"),
    "media_pause": _spec("media_pause", "Pause media playback", aliases=("pause", "pause video", "pause music", "stop playing"), examples=["pause the video", "pause music"], category="desktop"),
    "media_resume": _spec("media_resume", "Resume media playback", aliases=("resume", "resume video", "play again", "continue playing"), examples=["resume the video", "play again"], category="desktop"),
    "media_mute": _spec("media_mute", "Mute or toggle media sound", aliases=("mute video", "mute sound", "silence"), examples=["mute the sound"], category="desktop"),
    "browser_new_tab": _spec("browser_new_tab", "Open a new browser tab", aliases=("new tab", "open new tab", "create tab"), examples=["open a new tab"], category="browser"),
    "browser_close_tab": _spec("browser_close_tab", "Close the current browser tab", aliases=("close tab", "close current tab", "close this tab"), examples=["close the tab"], category="browser"),
    "browser_refresh": _spec("browser_refresh", "Refresh the current page", aliases=("refresh", "reload", "refresh page", "reload page"), examples=["refresh the page"], category="browser"),
    "browser_back": _spec("browser_back", "Go back in the browser", aliases=("go back", "navigate back", "previous page"), examples=["go back"], category="browser"),
    "browser_forward": _spec("browser_forward", "Go forward in the browser", aliases=("go forward", "navigate forward", "next page"), examples=["go forward"], category="browser"),
    "browser_history": _spec("browser_history", "Open browser history", aliases=("open history", "show history", "browser history"), examples=["show my history"], category="browser"),
    "browser_fullscreen": _spec("browser_fullscreen", "Toggle browser fullscreen", aliases=("full screen", "fullscreen", "toggle fullscreen"), examples=["go fullscreen"], category="browser"),
}


# These tools remain registered for exact deterministic human-command routing,
# but no model may discover or invoke them through a generated tool call.
MODEL_FORBIDDEN_TOOLS = frozenset({
    "approve_action",
    "reject_action",
    "nexi_start_studio_build",
    "nexi_cancel_studio_build",
    "nexi_continue_studio_build",
    "nexi_cancel_workflow",
    "nexi_continue_workflow",
})


def list_tools() -> list[dict[str, Any]]:
    return [asdict(tool) for tool in _TOOLS.values()]


def enabled_tools() -> list[ToolSpec]:
    return [tool for tool in _TOOLS.values() if tool.enabled]


def model_visible_tools() -> list[ToolSpec]:
    """Enabled tools safe to disclose at any model-facing boundary."""
    return [tool for tool in enabled_tools() if tool.name not in MODEL_FORBIDDEN_TOOLS]


def tools_openai_schema() -> list[dict[str, Any]]:
    return [tool.to_openai_schema() for tool in model_visible_tools()]


def router_tool_manifest() -> list[dict[str, Any]]:
    """Compact tool cards for every enabled tool — the LLM-facing capability list.

    This is the single source of truth the intent router shows the model so it
    can never be blind to a registered feature.
    """
    cards: list[dict[str, Any]] = []
    for tool in model_visible_tools():
        cards.append({
            "name": tool.name,
            "description": tool.description,
            "aliases": list(tool.aliases),
            "examples": list(tool.examples),
            "required_slots": list(tool.required_slots),
            "optional_slots": list(tool.optional_slots),
            "risk_level": tool.safety,
            "requires_confirmation": tool.requires_confirmation,
            "category": tool.category,
        })
    return cards


def xai_tools_schema() -> list[dict[str, Any]]:
    """Provider-native schemas with human-only trust-boundary tools removed."""
    return [tool.to_openai_schema() for tool in model_visible_tools()]


def alias_index() -> dict[str, str]:
    """Map every alias and tool name to its canonical tool name (longest-first usage at call site)."""
    index: dict[str, str] = {}
    for tool in enabled_tools():
        index[tool.name.replace("_", " ")] = tool.name
        for alias in tool.aliases:
            index[alias.strip().lower()] = tool.name
    return index


def registered_tool_names() -> list[str]:
    return sorted(_TOOLS.keys())


def get_tool(name: str) -> dict[str, Any] | None:
    tool = _TOOLS.get((name or "").strip())
    return asdict(tool) if tool else None


def missing_slots(name: str, slots: dict[str, Any] | None = None) -> list[str]:
    tool = _TOOLS.get(name)
    values = slots or {}
    if name == "open_website" and values.get("site") and not values.get("url"):
        values = {**values, "url": values.get("site")}
    return [slot for slot in (tool.required_slots if tool else []) if not values.get(slot)]


def clarification_for_missing_slot(tool_name: str, slot: str) -> str:
    if slot == "app_name":
        return "Which app should I open?"
    if slot == "query":
        return "What should I search for?"
    if slot == "url":
        return "Which website should I open?"
    if slot == "file_name":
        return "What should I name the file?"
    if slot == "folder_name":
        return "What should I name the folder?"
    if slot == "text":
        return "What should I write in the note?"
    if slot == "mode" and tool_name in {"hand_gesture_control", "eye_mouse_control"}:
        return "Preview or control mode?"
    return f"What should I use for {slot}?"


def select_tool(text: str) -> dict[str, Any]:
    q = (text or "").strip().lower().rstrip(".?!")
    try:
        from engine.tool_usage_intelligence import resolve_tool_alias
        alias = resolve_tool_alias(q)
        if alias.get("handled"):
            name = alias.get("name", "")
            return {
                "handled": True,
                "name": name,
                "slots": alias.get("slots", {}),
                "tool": get_tool(name),
                "confidence": alias.get("confidence", 0.95),
                "learned_rules_used": alias.get("learned_rules_used", []),
            }
    except Exception:
        pass
    intent = ""
    slots: dict[str, Any] = {}
    if q in {"open", "open app", "launch"}:
        intent = "open_app"
    elif q.startswith(("open ", "launch ")):
        target = q.split(" ", 1)[1].strip()
        try:
            from engine.local_skills import SITES
            is_site = target in SITES or "." in target
        except Exception:
            is_site = "." in target
        if is_site:
            intent = "open_website"
            slots["url"] = "youtube.com" if target == "youtube" else target
        else:
            intent = "open_app"
            slots["app_name"] = target
    elif q in {"search", "google", "search web", "search the web"}:
        intent = "web_search"
    elif q.startswith(("search ", "google ")):
        intent = "web_search"
        slots["query"] = q.split(" ", 1)[1]
    elif "stop" in q and any(word in q for word in ("camera", "gesture", "eye", "control")):
        intent = "stop_camera_control"
    elif "calibrate" in q and "eye" in q:
        intent = "eye_mouse_calibrate"
    elif "eye" in q and ("mouse" in q or "control" in q or "tracking" in q):
        intent = "eye_mouse_control"
        if "enable" in q or "eye control" in q:
            slots["mode"] = "control"
        elif "preview" in q or "start" in q:
            slots["mode"] = "preview"
    elif "hand" in q or "gesture" in q:
        intent = "hand_gesture_control"
        if "preview" in q:
            slots["mode"] = "preview"
        elif "enable" in q or "hand mouse" in q or "gesture mouse" in q or "mouse control" in q:
            slots["mode"] = "control"
    elif "camera" in q and "preview" in q:
        intent = "camera_preview"
    if not intent:
        return {"handled": False}
    print(f"[TOOL] selected name={intent} confidence=0.90", flush=True)
    return {"handled": True, "name": intent, "slots": slots, "tool": get_tool(intent), "confidence": 0.90}


# Tools whose "preview" mode is read-only by design: they open a viewer and never move the
# mouse or click. Only their "control" mode needs confirmation.
PREVIEW_SAFE_TOOLS = {"hand_gesture_control", "eye_mouse_control", "camera_preview"}

# Studio tools carry their own, stronger gate: an authorization token minted only by the
# owner's explicit confirming turn (see engine/studio/commands.issue_authorization). A
# model cannot mint one. The generic "say confirm" prompt must not intercept them, or the
# authorized build can never start.
STUDIO_AUTH_TOOLS = {
    "nexi_start_studio_build",
    "nexi_cancel_studio_build",
    "nexi_continue_studio_build",
}


def execute_tool(name: str, slots: dict[str, Any] | None = None, *, confirmed: bool = False) -> dict[str, Any]:
    values = dict(slots or {})
    tool = _TOOLS.get(name)
    if not tool:
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": name, "error_code": "UNKNOWN_TOOL", "expects_user_reply": False, "message": "That tool is not available."}
    declared_values = {slot: values[slot] for slot in tool.required_slots + tool.optional_slots if slot in values}
    studio_auth = values.get("_studio_auth") if name in STUDIO_AUTH_TOOLS else None
    # approval_queue.approve() (the ONLY legitimate approval path for gated computer-use
    # tools) re-invokes execute_tool with a private, unguessable sentinel under
    # _approval_token — never a value a model/router could produce. Capture it before
    # stripping so a genuinely-approved action still proceeds; any other value (or the
    # key from any other caller) is stripped below exactly as before.
    internal_approval_key = None
    internal_approval_value = None
    try:
        from engine.approval_queue import _APPROVAL_TOKEN_KEY, _INTERNAL_APPROVAL
        if values.get(_APPROVAL_TOKEN_KEY) == _INTERNAL_APPROVAL:
            internal_approval_key, internal_approval_value = _APPROVAL_TOKEN_KEY, _INTERNAL_APPROVAL
    except Exception:
        pass
    # Strip model-supplied authorization/approval/confirmation claims BEFORE anything
    # reads them. The ReAct planner already does this, but the direct dispatch path
    # (command.py -> execute_tool) did not, so a model could bypass approval_queue.gate
    # by emitting _approval_token / _studio_auth / confirmed. Approval is granted only
    # by the explicit `confirmed=` kwarg (set by Nexi from a real user confirmation),
    # never by a slot the model wrote. Applied first so the kwarg still works.
    try:
        from engine.react_planner import _strip_reserved_arguments
        values = dict(_strip_reserved_arguments(values))
    except Exception:
        for _k in ("_approval_token", "_studio_auth", "approval_token", "authorization", "confirmed"):
            values.pop(_k, None)
    values.update(declared_values)
    if isinstance(studio_auth, str) and studio_auth:
        values["_studio_auth"] = studio_auth
    if internal_approval_key:
        values[internal_approval_key] = internal_approval_value
    if confirmed:
        values["confirmed"] = True
    missing = missing_slots(name, values)
    if missing:
        slot = missing[0]
        print(f"[TOOL] missing_slot name={slot}", flush=True)
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": name, "expects_user_reply": True, "message": clarification_for_missing_slot(name, slot), "missing_slot": slot}
    # The blanket confirm gate exists because most confirm=True tools have no `mode` slot,
    # so the narrower control-mode check further down never fired for them and they ran
    # unconfirmed. It must not also block `preview`, which is the deliberately SAFE branch
    # of the camera tools — it opens a viewer and never moves the mouse or clicks, and the
    # router already marks it risk_level=low / requires_confirmation=false. Demanding
    # confirmation for preview both contradicts that and trains the user to confirm
    # reflexively, which is how the real control-mode prompt stops being read.
    safe_preview = name in PREVIEW_SAFE_TOOLS and values.get("mode") == "preview"
    # Tools that gate through approval_queue are exempt — that queue is their confirmation
    # step. See approval_queue.QUEUE_GATED_HANDLER_PREFIXES for why.
    try:
        from engine.approval_queue import is_queue_gated
        queue_gated = is_queue_gated(tool.handler)
    except Exception:
        queue_gated = False
    if tool.requires_confirmation and not (confirmed or internal_approval_key) and not safe_preview and not queue_gated and name not in STUDIO_AUTH_TOOLS:
        return {"handled": True, "ok": False, "success": False, "verified": False, "tool": name, "requires_confirmation": True, "expects_user_reply": True, "message": "This action requires confirmation. Say confirm to continue."}
    try:
        from engine.safety_gate import execution_is_safe
        safety = execution_is_safe(name, values, user_text=name)
        if not safety.get("allowed"):
            return {
                "handled": True,
                "ok": False,
                "success": False,
                "verified": False,
                "tool": name,
                "requires_confirmation": bool(safety.get("requires_confirmation")),
                "message": str(safety.get("reason") or "This action is blocked by the safety gate."),
            }
    except Exception as exc:
        print(f"[SAFETY] fail_closed tool={name} reason={type(exc).__name__}", flush=True)
        return {
            "handled": True,
            "ok": False,
            "success": False,
            "verified": False,
            "tool": name,
            "error_code": "SAFETY_GATE_ERROR",
            "message": "I couldn't verify that this action is safe, so I did not run it.",
        }
    print(f"[TOOL] executing name={name}", flush=True)
    try:
        result = _execute_handler(name, values, confirmed=confirmed)
        from engine.tool_result_verifier import verify_tool_result
        final = verify_tool_result(name, result)
        success = bool(final.get("success") is True and final.get("verified") is True)
        if success:
            print(f"[TOOL] success name={name}", flush=True)
        else:
            print(f"[TOOL] failed name={name} reason={final.get('verification_reason', 'unverified')}", flush=True)
        try:
            from engine.tool_usage_intelligence import record_tool_result
            record_tool_result(name, values, final)
        except Exception:
            pass
        try:
            # Tool name only, never `values` — slots carry file paths and query text,
            # and the world block is injected into prompts.
            from engine.world_model import update_world
            update_world(last_action=name, last_result="verified" if success else "unverified")
        except Exception:
            pass
        return final
    except Exception as e:
        print(f"[TOOL] failed name={name} reason={type(e).__name__}", flush=True)
        final = {"handled": True, "ok": False, "success": False, "verified": False, "tool": name, "message": "I couldn't run that tool safely."}
        try:
            from engine.tool_usage_intelligence import record_tool_result
            record_tool_result(name, values, final)
        except Exception:
            pass
        try:
            from engine.world_model import update_world
            update_world(last_action=name, last_result="failed")
        except Exception:
            pass
        return final


def _execute_handler(name: str, slots: dict[str, Any], *, confirmed: bool) -> Any:
    if name == "open_app":
        from engine.local_skills import open_app
        return open_app(str(slots.get("app_name") or ""))
    if name == "open_website":
        from engine.local_skills import open_website
        return open_website(url=str(slots.get("url") or slots.get("site") or ""))
    if name == "web_search":
        from engine.local_skills import web_search
        return web_search(str(slots.get("query") or ""))
    if name == "remember":
        from engine.memory_store import remember_fact
        return {"success": True, "message": remember_fact(str(slots.get("text") or "")), "tool": name, "verified": True}
    if name == "recall_memory":
        # Recall must read every store Nexi actually WRITES to. command.py writes
        # learned facts to memory.semantic_memory and past turns to
        # memory.episodic_memory, but this tool used to read only the legacy
        # nexi_memory.json — so "what do you remember about X" never saw anything
        # Nexi had learned. Each store is optional and degrades independently.
        from engine.memory_store import recall_summary
        query = str(slots.get("query") or slots.get("text") or "")
        parts: list[str] = []

        explicit = str(recall_summary(query) or "").strip()
        if explicit and "nothing" not in explicit.lower():
            parts.append(explicit)

        try:
            from engine.memory.semantic_memory import recall as recall_semantic
            facts = [f"{f.subject} {f.predicate} {f.object}".strip()
                     for f in recall_semantic(query, limit=5) if str(f.object or "").strip()]
            if facts:
                parts.append("I've learned: " + "; ".join(facts[:5]) + ".")
        except Exception:
            pass

        try:
            from engine.memory.episodic_memory import recall_similar
            episodes = [e.user_input for e in recall_similar(query, n=3) if str(e.user_input or "").strip()]
            if episodes:
                parts.append("You previously asked: " + "; ".join(f'"{e}"' for e in episodes[:3]) + ".")
        except Exception:
            pass

        message = " ".join(parts) if parts else (explicit or "I don't have anything about that yet.")
        return {"success": True, "message": message, "tool": name, "verified": True}
    if name == "forget_memory":
        from engine.memory_store import forget
        return {"success": True, "message": forget(str(slots.get("text") or "")), "tool": name, "verified": True}
    if name == "take_note":
        from engine.memory_store import add_note
        return {"success": True, "message": add_note(str(slots.get("text") or "")), "tool": name, "verified": True}
    if name == "show_notes":
        from engine.memory_store import show_notes
        return {"success": True, "message": show_notes(), "tool": name, "verified": True}
    if name in {"copy_latest_output", "save_latest_output", "create_file_from_latest_output", "show_latest_output", "read_output_summary", "shorten_latest_output", "regenerate_latest_output"}:
        from engine.smart_followup_engine import execute_output_action
        return execute_output_action(name, slots)
    if name == "camera_preview":
        from engine.camera_control import start_camera_preview
        ok = bool(start_camera_preview())
        return {"success": ok, "message": "Camera preview started." if ok else "Camera preview did not start.", "tool": name, "verified": ok}
    if name == "hand_gesture_control":
        from engine.camera_control import start_hand_gesture_control
        mode = str(slots.get("mode") or "control")
        ok = bool(start_hand_gesture_control(mode=mode, explicit=True))
        return {"success": ok, "message": "Hand gesture control started." if ok else "Hand gesture control did not start.", "tool": name, "verified": ok}
    if name == "eye_mouse_control":
        from engine.camera_control import start_eye_mouse_control
        mode = str(slots.get("mode") or "preview")
        ok = bool(start_eye_mouse_control(mode=mode, explicit=True))
        return {"success": ok, "message": "Eye mouse control started." if ok else "Eye mouse control requires calibration.", "tool": name, "verified": ok}
    if name == "eye_mouse_calibrate":
        from engine.camera_control import calibrate_eye_mouse
        ok = bool(calibrate_eye_mouse())
        return {"success": ok, "message": "Eye mouse calibration complete." if ok else "Eye mouse calibration did not complete.", "tool": name, "verified": ok}
    if name == "stop_camera_control":
        from engine.camera_control import stop_all_controls
        stop_all_controls()
        return {"success": True, "message": "Camera controls stopped.", "tool": name, "verified": True}
    if name == "face_recognition":
        from engine.camera_control import start_face_recognition, is_face_recognition_running
        mode = str(slots.get("mode") or "start")
        if mode == "stop":
            from engine.camera_control import stop_face_recognition
            ok = bool(stop_face_recognition())
            return {"success": ok, "message": "Face recognition stopped." if ok else "Face recognition was not running.", "tool": name, "verified": ok}
        if is_face_recognition_running():
            return {"success": True, "message": "Face recognition is already running.", "tool": name, "verified": True}
        ok = bool(start_face_recognition())
        return {"success": ok, "message": "Face recognition started." if ok else "Face recognition did not start.", "tool": name, "verified": ok}
    if name == "face_register":
        from engine.camera_control import register_face
        person = str(slots.get("name") or "User")
        duration = int(slots.get("duration_s", 10))
        ok = bool(register_face(name=person, duration_s=duration))
        return {"success": ok, "message": f"Face registered for '{person}'." if ok else "Face registration failed.", "tool": name, "verified": ok}
    if name == "create_folder" or name == "create_project_folder":
        from pathlib import Path
        folder = str(slots.get("folder_name") or slots.get("name") or "")
        if not folder:
            return {"success": False, "message": "What should I name the folder?", "tool": name, "expects_user_reply": True}
        safe_root = (Path.home() / "Desktop").resolve()
        target = (safe_root / folder).resolve()
        try:
            target.relative_to(safe_root)
        except ValueError:
            return {"success": False, "error_code": "PATH_OUTSIDE_SAFE_ROOT", "message": "I can only create folders inside your Desktop.", "tool": name}
        target.mkdir(parents=True, exist_ok=True)
        return {"success": True, "message": f"Folder created: {target.name}", "path": str(target), "tool": name}
    if name == "create_file":
        filename = str(slots.get("file_name") or slots.get("name") or "")
        if not filename:
            return {"success": False, "message": "What should I name the file?", "tool": name, "expects_user_reply": True}
        from pathlib import Path
        safe_root = (Path.home() / "Desktop").resolve()
        target = (safe_root / filename).resolve()
        try:
            target.relative_to(safe_root)
        except ValueError:
            return {"success": False, "error_code": "PATH_OUTSIDE_SAFE_ROOT", "message": "I can only create files inside your Desktop.", "tool": name}
        if not target.suffix:
            target = target.with_suffix(".txt")
        content = slots.get("content")
        target.write_text("" if content is None else str(content), encoding="utf-8")
        return {"success": True, "message": f"File created: {target.name}", "path": str(target), "tool": name}
    if name == "take_screenshot":
        try:
            import pyautogui
            from pathlib import Path
            out = Path.home() / "Desktop" / f"screenshot_{int(time.time())}.png"
            pyautogui.screenshot(str(out))
            return {"success": True, "message": f"Screenshot saved: {out.name}", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Screenshot requires pyautogui which is not installed.", "tool": name}
    if name == "system_status":
        try:
            from engine.diagnostics import Diagnostics, check_all_dict
            checks = check_all_dict(force=True)
            uptime = Diagnostics.get_uptime()
            ok = sum(1 for c in checks.values() if c.get("status") == "ready" or c.get("status") == "active")
            total = len(checks)
            return {"success": True, "message": f"System status: {ok}/{total} components ready. Uptime: {uptime}.", "tool": name, "verified": True}
        except Exception as exc:
            return {"success": False, "message": f"Status check failed: {type(exc).__name__}", "tool": name}
    if name == "clipboard_read":
        try:
            import pyperclip
            text = pyperclip.paste()
            return {"success": True, "message": f"Clipboard: {text[:200]}", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Clipboard access requires pyperclip which is not installed.", "tool": name}
    if name == "clipboard_write_safe":
        text = str(slots.get("text") or "")
        if not text:
            return {"success": False, "message": "What should I write to the clipboard?", "tool": name, "expects_user_reply": True}
        try:
            import pyperclip
            pyperclip.copy(text)
            return {"success": True, "message": "Copied to clipboard.", "tool": name, "verified": True}
        except Exception:
            try:
                import tkinter as tk
                root = tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(text)
                root.update()
                root.destroy()
                return {"success": True, "message": "Copied to clipboard.", "tool": name, "verified": True}
            except Exception:
                return {"success": False, "message": "Could not access clipboard.", "tool": name}
    if name == "repeat_last":
        try:
            from engine.command import _last_spoken
            if _last_spoken:
                return {"success": True, "message": _last_spoken, "tool": name, "verified": True}
            return {"success": False, "message": "Nothing to repeat.", "tool": name}
        except Exception:
            return {"success": False, "message": "Could not repeat last message.", "tool": name}
    if name == "sleep":
        try:
            from engine.command import do_sleep
            do_sleep()
            return {"success": True, "message": "Nexi is going to sleep.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Could not enter sleep mode.", "tool": name}
    if name == "wake":
        try:
            from engine.command import do_wake
            do_wake()
            return {"success": True, "message": "Nexi is awake.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Could not wake.", "tool": name}
    if name in {"open_output_workspace", "close_output_workspace", "minimize_output_workspace", "pin_output_workspace"}:
        try:
            eel_func = {"open_output_workspace": "showOutputWorkspace", "close_output_workspace": "closeOutputWorkspace", "minimize_output_workspace": "minimizeOutputWorkspace", "pin_output_workspace": "pinOutputWorkspace"}[name]
            from engine.command import safe_eel_call
            safe_eel_call(eel_func, json.dumps({"show_workspace": True}) if name == "open_output_workspace" else "")
            return {"success": True, "message": f"Output workspace: {name.replace('_', ' ')}.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Could not control output workspace.", "tool": name}
    if name == "volume_up":
        try:
            from engine.control.audio import volume_up as ctrl
            ctrl()
            return {"success": True, "message": "Volume increased.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Volume control is not available.", "tool": name}
    if name == "volume_down":
        try:
            from engine.control.audio import volume_down as ctrl
            ctrl()
            return {"success": True, "message": "Volume decreased.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Volume control is not available.", "tool": name}
    if name == "mute":
        try:
            from engine.control.audio import mute as ctrl
            ctrl()
            return {"success": True, "message": "Audio muted.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Volume control is not available.", "tool": name}
    if name in {"gesture_click_mode", "gesture_scroll_mode"}:
        try:
            from engine.camera_control import set_gesture_mode
            mode_name = name.replace("gesture_", "").replace("_mode", "")
            ok = set_gesture_mode(mode_name)
            return {"success": ok, "message": f"Gesture {mode_name} mode {'enabled' if ok else 'not available'}.", "tool": name, "verified": ok}
        except Exception:
            return {"success": False, "message": "Gesture control is not available.", "tool": name}
    if name in {"search_youtube", "play_youtube"}:
        query = str(slots.get("query") or slots.get("text") or "")
        if not query:
            return {"success": False, "message": "What should I play on YouTube?", "tool": name, "expects_user_reply": True}
        try:
            from engine.features import PlayYoutube
            PlayYoutube(query)
            return {"success": True, "message": f"Playing {query} on YouTube.", "tool": name, "verified": True}
        except Exception:
            import webbrowser
            from urllib.parse import quote_plus
            webbrowser.open(f"https://www.youtube.com/results?search_query={quote_plus(query)}")
            return {"success": True, "message": f"Searching YouTube for {query}.", "tool": name, "verified": True}
    if name == "tell_time":
        import datetime
        now = datetime.datetime.now().strftime("%I:%M %p")
        return {"success": True, "message": f"The time is {now}.", "tool": name, "verified": True}
    if name in {"get_active_window", "what_am_i_working_on", "get_system_state", "why_is_pc_slow", "get_running_apps", "get_idle_time"}:
        from engine import os_awareness
        return getattr(os_awareness, name)(slots)
    if name in {"am_i_online", "get_network_status", "get_ip_address"}:
        from engine import net_awareness
        return getattr(net_awareness, name)(slots)
    if name in {"get_disk_space", "is_disk_full", "get_battery_status"}:
        from engine import storage_awareness
        return getattr(storage_awareness, name)(slots)
    if name in {"open_settings", "open_wifi_settings", "open_bluetooth_settings",
                "open_display_settings", "open_sound_settings", "open_microphone_settings",
                "open_camera_settings", "open_startup_settings", "open_windows_update",
                "open_settings_page"}:
        from engine import windows_settings
        return getattr(windows_settings, name)(slots)
    if name in {"show_diagnostics", "get_monitor_state", "echo_guard_status", "get_hud_state", "what_did_you_learn"}:
        from engine import runtime_awareness
        return getattr(runtime_awareness, name)(slots)
    if name in {"resolve_app_for_task", "open_app_for_task"}:
        from engine import app_intelligence
        return getattr(app_intelligence, name)(slots)
    if name in {"list_skills", "describe_skill"}:
        from engine import skill_library
        return getattr(skill_library, name)(slots)
    if name in {"read_current_page", "list_browser_tabs", "read_browser_console", "browser_click", "browser_fill"}:
        from engine import browser_intelligence
        return getattr(browser_intelligence, name)(slots)
    if name in {"pending_approvals", "approve_action", "reject_action"}:
        from engine import approval_queue
        return getattr(approval_queue, name)(slots)
    if name in {"request_feature", "list_feature_requests"}:
        from engine import feature_requests
        return getattr(feature_requests, name)(slots)
    if name == "nexi_agent_runtime_status":
        from engine.agent_runtime.tools import runtime_status_tool
        return runtime_status_tool(slots)
    if name.startswith("nexi_") and name not in {"nexi"}:
        from engine import agency
        if hasattr(agency, name):
            return getattr(agency, name)(slots)
    if name in {"screen_read", "click_ui_element", "type_text"}:
        from engine import computer_use
        return getattr(computer_use, name)(slots)
    if name == "tell_joke":
        return {"success": True, "message": "Why don't scientists trust atoms? Because they make up everything!", "tool": name, "verified": True}
    if name == "weather_lookup":
        location = str(slots.get("location") or "").strip()
        try:
            import requests
            from bs4 import BeautifulSoup
            q = f"weather {location}".strip()
            r = requests.get(f"https://www.google.com/search?q={q}", headers={"User-Agent": "Mozilla/5.0"}, timeout=8)
            temp = BeautifulSoup(r.text, "html.parser").find("div", class_="BNeawe")
            if temp and temp.text:
                return {"success": True, "message": f"The weather is {temp.text}.", "tool": name, "verified": True}
            return {"success": False, "message": "I couldn't fetch the weather information.", "tool": name}
        except Exception:
            return {"success": False, "message": "I couldn't fetch the weather information.", "tool": name}
    if name == "internet_speed_test":
        try:
            import speedtest
            st = speedtest.Speedtest()
            down = st.download() / 1_000_000
            up = st.upload() / 1_000_000
            return {"success": True, "message": f"Download {down:.1f} Mbps, upload {up:.1f} Mbps.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "Internet speed test is not available.", "tool": name}
    if name in {"media_pause", "media_resume", "media_mute", "browser_new_tab", "browser_close_tab", "browser_refresh", "browser_back", "browser_forward", "browser_history", "browser_fullscreen"}:
        hotkeys = {
            "media_pause": ("playpause",), "media_resume": ("playpause",), "media_mute": ("volumemute",),
            "browser_new_tab": ("ctrl", "t"), "browser_close_tab": ("ctrl", "w"), "browser_refresh": ("f5",),
            "browser_back": ("alt", "left"), "browser_forward": ("alt", "right"), "browser_history": ("ctrl", "h"),
            "browser_fullscreen": ("f11",),
        }
        try:
            import pyautogui
            pyautogui.hotkey(*hotkeys[name])
            label = name.replace("media_", "").replace("browser_", "").replace("_", " ")
            return {"success": True, "message": f"Done: {label}.", "tool": name, "verified": True}
        except Exception:
            return {"success": False, "message": "That control requires pyautogui which is not available.", "tool": name}
    if name in {"nexi_forge_tool", "nexi_list_forged_tools", "nexi_remove_tool"}:
        # Nexi writing her own tools. The forge wrappers take real arguments and
        # return {ok,...}, so adapt slots -> args and ok -> the tool contract.
        # Safety lives in forge_engine: anything touching fs/network/subprocess is
        # gated to needs_approval and is never executed or installed.
        from engine.forge import forge_engine
        data = slots or {}
        if name == "nexi_forge_tool":
            out = forge_engine.nexi_forge_tool(spec=str(data.get("spec") or data.get("capability") or ""))
        elif name == "nexi_remove_tool":
            out = forge_engine.nexi_remove_tool(name=str(data.get("name") or ""))
        else:
            out = forge_engine.nexi_list_forged_tools()
        ok = bool(out.get("ok"))
        result = {"success": ok, "verified": ok, "tool": name, "message": str(out.get("message") or "")}
        if out.get("status") == "needs_approval":
            result["requires_approval"] = True
        return result
    if name == "which_model":
        from engine.model_registry import which_model
        return which_model(slots)
    return {"success": False, "message": "That tool is registered but not available yet.", "tool": name, "verified": False}
