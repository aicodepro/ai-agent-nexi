"""Skill dispatcher — routes intents to skill handlers."""

from skills import apps, web, files, browser, system, communication, games, scheduler, vision_control
from skills import jarvis as jarvis_skill

SKILL_MAP = {
    # Apps
    "open_app": lambda e: apps.open_app(e),
    "close_app": lambda e: apps.close_app(e),

    # Web
    "open_website": lambda e: web.open_website(e),
    "web_search": lambda e: web.web_search(e),
    "google_search": lambda e: web.web_search(e),
    "youtube_search": lambda e: web.youtube_search(e),

    # Files
    "create_folder": lambda e: files.create_folder(e),
    "create_file": lambda e: files.create_file(e),
    "create_project": lambda e: files.create_project(e),
    "take_screenshot": lambda _: files.take_screenshot(),

    # Browser
    "volume_up": lambda _: _browser_action(browser.volume_up, "Volume up."),
    "volume_down": lambda _: _browser_action(browser.volume_down, "Volume down."),
    "zoom_in": lambda _: _browser_action(browser.zoom_in, "Zoomed in."),
    "zoom_out": lambda _: _browser_action(browser.zoom_out, "Zoomed out."),
    "new_tab": lambda _: _browser_action(browser.new_tab, "New tab opened."),
    "close_tab": lambda _: _browser_action(browser.close_tab, "Tab closed."),
    "next_tab": lambda _: _browser_action(browser.next_tab, "Switched to next tab."),
    "prev_tab": lambda _: _browser_action(browser.prev_tab, "Switched to previous tab."),
    "fullscreen": lambda _: _browser_action(browser.fullscreen, "Toggled fullscreen."),
    "minimize": lambda _: _browser_action(browser.minimize, "Window minimized."),
    "refresh": lambda _: _browser_action(browser.refresh, "Page refreshed."),
    "go_back": lambda _: _browser_action(browser.go_back, "Went back."),
    "go_forward": lambda _: _browser_action(browser.go_forward, "Went forward."),
    "history": lambda _: _browser_action(browser.history, "Opened history."),
    "bookmarks": lambda _: _browser_action(browser.bookmarks, "Opened bookmarks."),
    "dev_tools": lambda _: _browser_action(browser.dev_tools, "Opened developer tools."),
    "private_window": lambda _: _browser_action(browser.private_window, "Opened private window."),

    # System
    "get_time": lambda _: system.get_time(),
    "get_weather": lambda e: system.get_weather(e),
    "read_clipboard": lambda _: system.read_clipboard(),
    "play_music": lambda e: system.play_music(e),

    # Communication
    "send_email": lambda e: communication.send_email(e, "From Nexi", ""),
    "find_places": lambda e: communication.find_places(e),

    # Games
    "play_game": lambda _: games.start_rps(),

    # Scheduler
    "set_reminder": lambda e: scheduler.set_reminder(e),
    "set_alarm": lambda e: scheduler.set_alarm(e),
    "show_reminders": lambda _: scheduler.show_reminders(),

    # Vision
    "start_hand_control": lambda _: vision_control.start_hand_control(),
    "start_eye_control": lambda _: vision_control.start_eye_control(),
    "stop_camera": lambda _: vision_control.stop_camera(),

    # Jarvis agent skills
    "run_agent":           lambda e: _jarvis_action(jarvis_skill.run_agent, e),
    "execute_tool":        lambda e: _jarvis_action(jarvis_skill.execute_tool, e),
    "train_on_correction": lambda e: _jarvis_action(jarvis_skill.train_on_correction, e),
    "add_rule":            lambda e: _jarvis_action(jarvis_skill.add_rule, e),
    "remove_rule":         lambda e: _jarvis_action(jarvis_skill.remove_rule, e),
    "agent_status":        lambda _: _jarvis_action(jarvis_skill.agent_status),
    "reflect":             lambda _: _jarvis_action(jarvis_skill.reflect),
    "tool_help":           lambda e: _jarvis_action(jarvis_skill.tool_help, e),
    "cancel_agent":        lambda _: _jarvis_action(jarvis_skill.cancel_agent),
}


def _jarvis_action(fn, *args) -> dict:
    try:
        return {"handled": True, "message": fn(*args)}
    except Exception as e:
        return {"handled": False, "message": f"Jarvis error: {e}"}


def _browser_action(fn, message: str) -> dict:
    try:
        fn()
        return {"handled": True, "message": message}
    except Exception as e:
        return {"handled": False, "message": f"Action failed: {e}"}


def handle_skill(intent: str, entity: str = "") -> dict:
    handler = SKILL_MAP.get(intent)
    if handler:
        try:
            return handler(entity)
        except Exception as e:
            return {"handled": False, "message": f"Skill error: {e}"}
    return {"handled": False, "message": f"Unknown skill: {intent}"}
