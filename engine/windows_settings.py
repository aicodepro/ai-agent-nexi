"""Windows Settings Controller (Roadmap Feature #3) — open Windows Settings pages.

Tool cards
----------
open_settings           role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_wifi_settings      role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_bluetooth_settings role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_display_settings   role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_sound_settings     role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_microphone_settings role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_camera_settings    role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_startup_settings   role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_windows_update     role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store
open_settings_page      role: PC control | risk: LOW | confirm: never | verifier: settings launch issued | memory: never store

Every tool OPENS a Settings page via the documented ms-settings: URI scheme. Opening a
page is low-risk: it shows the page but never changes a setting. Changing settings would
be a separate, confirmation-gated feature (not implemented here).
ms-settings: URI reference: https://learn.microsoft.com/windows/apps/develop/launch/launch-settings-app
"""

from __future__ import annotations

import os
from typing import Any


# page keyword -> ms-settings: sub-path ("" means the Settings home page)
_SETTINGS_PAGES: dict[str, str] = {
    "home": "",
    "settings": "",
    "windows": "",
    "wifi": "network-wifi",
    "wi-fi": "network-wifi",
    "network": "network-status",
    "internet": "network-status",
    "bluetooth": "bluetooth",
    "display": "display",
    "screen": "display",
    "sound": "sound",
    "audio": "sound",
    "volume": "sound",
    "microphone": "privacy-microphone",
    "mic": "privacy-microphone",
    "camera": "privacy-webcam",
    "webcam": "privacy-webcam",
    "startup": "startupapps",
    "startup apps": "startupapps",
    "update": "windowsupdate",
    "windows update": "windowsupdate",
    "updates": "windowsupdate",
    "battery": "batterysaver",
    "storage": "storagesense",
    "default apps": "defaultapps",
    "notifications": "notifications",
    "power": "powersleep",
    "sleep": "powersleep",
    "personalization": "personalization",
    "about": "about",
}


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "windows_settings"), "message": message, **extra}


def _fail(message: str, tool: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": False, "success": False, "verified": False,
            "tool": tool, "message": message, **extra}


def settings_uri(page: str) -> str:
    """Resolve a free-text page name to its ms-settings: URI, or '' if unknown."""
    key = (page or "").strip().lower()
    if not key:
        return ""
    if key in _SETTINGS_PAGES:
        return "ms-settings:" + _SETTINGS_PAGES[key]
    for known, sub in _SETTINGS_PAGES.items():
        if known and (known in key or key in known):
            return "ms-settings:" + sub
    return ""


def _open_uri(uri: str) -> bool:
    """Launch a settings URI via the Windows shell. Isolated for testability."""
    os.startfile(uri)  # type: ignore[attr-defined]  # Windows-only
    return True


def _open(label: str, uri: str, tool: str) -> dict[str, Any]:
    if not uri:
        return _fail(f"I don't know how to open {label} settings.", tool)
    try:
        _open_uri(uri)
    except Exception:
        return _fail(f"I couldn't open {label} settings.", tool, uri=uri)
    return _ok(f"Opening {label} settings.", tool=tool, uri=uri, opened=True)


def open_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("Windows", "ms-settings:", "open_settings")


def open_wifi_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("Wi-Fi", "ms-settings:network-wifi", "open_wifi_settings")


def open_bluetooth_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("Bluetooth", "ms-settings:bluetooth", "open_bluetooth_settings")


def open_display_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("display", "ms-settings:display", "open_display_settings")


def open_sound_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("sound", "ms-settings:sound", "open_sound_settings")


def open_microphone_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("microphone", "ms-settings:privacy-microphone", "open_microphone_settings")


def open_camera_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("camera", "ms-settings:privacy-webcam", "open_camera_settings")


def open_startup_settings(slots: dict | None = None) -> dict[str, Any]:
    return _open("startup apps", "ms-settings:startupapps", "open_startup_settings")


def open_windows_update(slots: dict | None = None) -> dict[str, Any]:
    return _open("Windows Update", "ms-settings:windowsupdate", "open_windows_update")


def open_settings_page(slots: dict | None = None) -> dict[str, Any]:
    page = str((slots or {}).get("page") or (slots or {}).get("text") or "").strip()
    if not page:
        return {"handled": True, "ok": False, "success": False, "verified": False,
                "tool": "open_settings_page", "expects_user_reply": True,
                "message": "Which settings page should I open?", "missing_slot": "page"}
    uri = settings_uri(page)
    if not uri:
        return _fail(f"I don't know the settings page '{page}'.", "open_settings_page")
    return _open(page, uri, "open_settings_page")
