import pyautogui
import time

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.01

_click_cooldown = 0.35
_scroll_cooldown = 0.05
_last_click_time = 0.0
_last_scroll_time = 0.0
_drag_active = False
_debug = False


def _reset_state():
    global _last_click_time, _last_scroll_time, _drag_active
    _last_click_time = 0.0
    _last_scroll_time = 0.0
    _drag_active = False


def set_debug(val: bool):
    global _debug
    _debug = val


def move_cursor(x: int, y: int):
    try:
        pyautogui.moveTo(int(x), int(y), duration=0)
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] move error: {e}")


def left_click() -> bool:
    global _last_click_time
    now = time.time()
    if now - _last_click_time < _click_cooldown:
        return False
    try:
        pyautogui.click(button="left")
        _last_click_time = now
        if _debug:
            print("[MOUSE] left_click")
        return True
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] left_click error: {e}")
        return False


def right_click() -> bool:
    global _last_click_time
    now = time.time()
    if now - _last_click_time < _click_cooldown:
        return False
    try:
        pyautogui.click(button="right")
        _last_click_time = now
        if _debug:
            print("[MOUSE] right_click")
        return True
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] right_click error: {e}")
        return False


def double_click() -> bool:
    global _last_click_time
    now = time.time()
    if now - _last_click_time < _click_cooldown:
        return False
    try:
        pyautogui.doubleClick(button="left")
        _last_click_time = now
        if _debug:
            print("[MOUSE] double_click")
        return True
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] double_click error: {e}")
        return False


def start_drag():
    global _drag_active
    if _drag_active:
        return
    try:
        pyautogui.mouseDown(button="left")
        _drag_active = True
        if _debug:
            print("[MOUSE] drag_started")
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] drag error: {e}")


def stop_drag():
    global _drag_active
    if not _drag_active:
        return
    try:
        pyautogui.mouseUp(button="left")
        _drag_active = False
        if _debug:
            print("[MOUSE] drag_stopped")
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] drag_stop error: {e}")


def is_dragging() -> bool:
    return _drag_active


def scroll(amount: int) -> bool:
    global _last_scroll_time
    now = time.time()
    if now - _last_scroll_time < _scroll_cooldown:
        return False
    try:
        pyautogui.scroll(int(amount))
        _last_scroll_time = now
        if _debug:
            print(f"[MOUSE] scroll amount={amount}")
        return True
    except pyautogui.FailSafeException:
        raise
    except Exception as e:
        if _debug:
            print(f"[MOUSE] scroll error: {e}")
        return False


def screenshot() -> str:
    try:
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = f"screenshot_{ts}.png"
        pyautogui.screenshot(path)
        if _debug:
            print(f"[MOUSE] screenshot saved: {path}")
        return path
    except Exception as e:
        if _debug:
            print(f"[MOUSE] screenshot error: {e}")
        return ""
