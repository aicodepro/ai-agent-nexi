"""Computer-Use Harness (Roadmap Feature #8) — observe → (gate) → act → verify.

Tool cards
----------
screen_read      role: computer use | risk: LOW      | confirm: never    | verifier: screen text captured  | memory: never store
click_ui_element role: computer use | risk: CRITICAL  | confirm: approval | verifier: click performed        | memory: never store
type_text        role: computer use | risk: HIGH      | confirm: approval | verifier: text typed             | memory: never store

`screen_read` is read-only. `click_ui_element` and `type_text` are ACTING tools and route
through the Human Approval Queue (#10): they queue and return a requires-approval result
unless the action carries an `approved` flag (set when the user approves). Real OS access is
isolated behind `_capture_screen_text` / `_perform_click` / `_perform_type`, which degrade
gracefully when the optional automation libraries (uiautomation / pyautogui) aren't present.
Per the roadmap card, this never clicks pay/send/delete without explicit approval.
"""

from __future__ import annotations

from typing import Any


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "computer_use"), "message": message, **extra}


def _fail(message: str, tool: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": False, "success": False, "verified": False,
            "tool": tool, "message": message, **extra}


def _capture_screen_text() -> str:
    """Best-effort visible UI text of the foreground window (read-only)."""
    try:
        import uiautomation as auto
        root = auto.GetForegroundControl()
        seen: list[str] = []

        def walk(ctrl, depth):
            if ctrl is None or depth < 0:
                return
            try:
                name = (ctrl.Name or "").strip()
                if name:
                    seen.append(name)
                for child in ctrl.GetChildren():
                    walk(child, depth - 1)
            except Exception:
                return

        walk(root, 3)
        if seen:
            return " | ".join(dict.fromkeys(seen))[:4000]
    except Exception:
        pass
    try:
        from engine.os_awareness import _read_active_window
        title, _proc = _read_active_window()
        return title or ""
    except Exception:
        return ""


def _perform_click(target: str) -> bool:
    """Click a UI element by visible name (uiautomation). False if unavailable/not found."""
    try:
        import uiautomation as auto
        for ctor in (auto.ButtonControl, auto.Control):
            ctrl = ctor(searchDepth=24, Name=target)
            if ctrl.Exists(2, 0.5):
                ctrl.Click(simulateMove=False)
                return True
    except Exception:
        pass
    return False


def _perform_type(text: str) -> bool:
    """Type text into the focused field. False if no backend available."""
    try:
        import pyautogui
        pyautogui.typewrite(text, interval=0.01)
        return True
    except Exception:
        pass
    try:
        import keyboard
        keyboard.write(text)
        return True
    except Exception:
        return False


def screen_read(slots: dict | None = None) -> dict[str, Any]:
    text = _capture_screen_text()
    if not text:
        return _ok("I couldn't read anything on the screen right now.", tool="screen_read",
                   available=False, text="")
    excerpt = " ".join(text.split())[:300]
    return _ok(f"On screen: {excerpt}", tool="screen_read", available=True, text=text)


def click_ui_element(slots: dict | None = None) -> dict[str, Any]:
    target = str((slots or {}).get("target") or (slots or {}).get("text") or "").strip()
    if not target:
        return _fail("What should I click?", "click_ui_element", expects_user_reply=True, missing_slot="target")
    from engine import approval_queue
    gated = approval_queue.gate("click_ui_element", slots, "critical", f"click '{target}'")
    if gated:
        return gated
    if _perform_click(target):
        return _ok(f"Clicked '{target}'.", tool="click_ui_element", target=target, performed=True)
    return _fail(f"I couldn't find or click '{target}'. (UI automation may be unavailable.)",
                 "click_ui_element", target=target, performed=False)


def type_text(slots: dict | None = None) -> dict[str, Any]:
    text = str((slots or {}).get("text") or "").strip()
    if not text:
        return _fail("What should I type?", "type_text", expects_user_reply=True, missing_slot="text")
    from engine import approval_queue
    gated = approval_queue.gate("type_text", slots, "high", f"type \"{text[:40]}\"")
    if gated:
        return gated
    if _perform_type(text):
        return _ok(f"Typed \"{text[:60]}\".", tool="type_text", performed=True)
    return _fail("I couldn't type that. (Keyboard automation may be unavailable.)",
                 "type_text", performed=False)
