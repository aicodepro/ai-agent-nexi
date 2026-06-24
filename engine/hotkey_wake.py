from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Optional


def _env_bool(key: str, default: bool = False) -> bool:
    value = (os.getenv(key, "true" if default else "false") or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def _display_hotkey(value: str) -> str:
    return (value or "win+j").strip().lower().replace("windows+", "win+")


def _keyboard_hotkey(value: str) -> str:
    return _display_hotkey(value).replace("win+", "windows+")


def _safe_reason(exc: Exception) -> str:
    return type(exc).__name__


def _on_detect(callback: Callable[[str], bool]) -> None:
    print("[HOTKEY] detected source=hotkey", flush=True)
    # If callback not provided, emit via InternalWakeSignalBus as a fallback
    try:
        callback("hotkey")
    except TypeError:
        callback()
    except Exception as e:
        print(f"[HOTKEY] callback_failed reason={type(e).__name__}", flush=True)


@dataclass
class HotkeyListener:
    keyboard_module: object = None
    handles: list = field(default_factory=list)
    pynput_listener: object = None

    @property
    def registered(self) -> bool:
        return bool(self.handles or self.pynput_listener)

    def stop(self) -> None:
        if self.keyboard_module is not None:
            for handle in self.handles:
                try:
                    self.keyboard_module.remove_hotkey(handle)
                except Exception:
                    pass
        self.handles.clear()
        if self.pynput_listener is not None:
            try:
                self.pynput_listener.stop()
            except Exception:
                pass
            self.pynput_listener = None


def _try_keyboard_add(listener: HotkeyListener, keyboard_module, hotkey: str, callback) -> bool:
    try:
        handle = keyboard_module.add_hotkey(_keyboard_hotkey(hotkey), lambda: _on_detect(callback))
        listener.keyboard_module = keyboard_module
        listener.handles.append(handle)
        return True
    except Exception as e:
        if _display_hotkey(hotkey) == "win+j":
            print(f"[HOTKEY] win+j unavailable reason={_safe_reason(e)}", flush=True)
        else:
            print(f"[HOTKEY] fallback unavailable reason={_safe_reason(e)}", flush=True)
        return False


def _try_pynput_fallback(listener: HotkeyListener, hotkey: str, callback) -> bool:
    try:
        from pynput import keyboard as pynput_keyboard
    except Exception as e:
        print(f"[HOTKEY] pynput unavailable reason={_safe_reason(e)}", flush=True)
        return False

    keys = {part.strip().lower() for part in _display_hotkey(hotkey).split("+") if part.strip()}
    pressed = set()

    def key_name(key) -> str:
        raw = getattr(key, "char", None) or str(key).replace("Key.", "")
        raw = raw.lower()
        if raw in {"ctrl_l", "ctrl_r"}:
            return "ctrl"
        if raw in {"alt_l", "alt_r"}:
            return "alt"
        if raw in {"cmd", "cmd_l", "cmd_r", "win"}:
            return "win"
        return raw

    def on_press(key):
        pressed.add(key_name(key))
        if keys and keys.issubset(pressed):
            _on_detect(callback)

    def on_release(key):
        pressed.discard(key_name(key))

    try:
        listener.pynput_listener = pynput_keyboard.Listener(on_press=on_press, on_release=on_release)
        listener.pynput_listener.start()
        return True
    except Exception as e:
        print(f"[HOTKEY] fallback unavailable reason={_safe_reason(e)}", flush=True)
        return False


def start_hotkey_listener(callback: Optional[Callable[[str], bool]] = None) -> Optional[HotkeyListener]:
    if os.getenv("NEXI_HOTKEY_WAKE_ENABLED") is not None:
        enabled = _env_bool("NEXI_HOTKEY_WAKE_ENABLED", False)
    else:
        enabled = _env_bool("NEXI_HOTKEY_ENABLED", False)
    if not enabled:
        print("[HOTKEY] disabled", flush=True)
        return None
    if callback is None:
        from engine.nexi_wake_controller import wake_nexi
        callback = wake_nexi

    primary = _display_hotkey(os.getenv("NEXI_HOTKEY", "win+j"))
    fallback = _display_hotkey(os.getenv("NEXI_HOTKEY_FALLBACK", "ctrl+alt+j"))
    listener = HotkeyListener()

    print(f"[HOTKEY] registering hotkey={primary}", flush=True)
    try:
        import keyboard as keyboard_module
    except Exception as e:
        print(f"[HOTKEY] win+j unavailable reason={_safe_reason(e)}", flush=True)
        keyboard_module = None

    primary_ok = False
    if keyboard_module is not None:
        primary_ok = _try_keyboard_add(listener, keyboard_module, primary, callback)
        print(f"[HOTKEY] registered={str(primary_ok).lower()}", flush=True)
        if fallback and fallback != primary:
            if _try_keyboard_add(listener, keyboard_module, fallback, callback):
                print(f"[HOTKEY] fallback registered hotkey={fallback}", flush=True)
    if not listener.registered and fallback:
        if _try_pynput_fallback(listener, fallback, callback):
            print(f"[HOTKEY] fallback registered hotkey={fallback}", flush=True)
    return listener if listener.registered else None


def stop_hotkey_listener(listener: Optional[HotkeyListener]) -> None:
    if listener is not None:
        listener.stop()
