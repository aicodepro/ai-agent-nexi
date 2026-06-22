"""Browser control — keyboard hotkeys for tab/navigation/zoom."""

import pyautogui
import time


def volume_up():
    for _ in range(10):
        pyautogui.press("volumeup")
        time.sleep(0.1)


def volume_down():
    for _ in range(10):
        pyautogui.press("volumedown")
        time.sleep(0.1)


def new_tab():
    pyautogui.hotkey("ctrl", "t")


def close_tab():
    pyautogui.hotkey("ctrl", "w")


def next_tab():
    pyautogui.hotkey("ctrl", "tab")


def prev_tab():
    pyautogui.hotkey("ctrl", "shift", "tab")


def zoom_in():
    pyautogui.hotkey("ctrl", "+")


def zoom_out():
    pyautogui.hotkey("ctrl", "-")


def refresh():
    pyautogui.hotkey("ctrl", "r")


def go_back():
    pyautogui.hotkey("alt", "left")


def go_forward():
    pyautogui.hotkey("alt", "right")


def history():
    pyautogui.hotkey("ctrl", "h")


def bookmarks():
    pyautogui.hotkey("ctrl", "d")


def dev_tools():
    pyautogui.hotkey("ctrl", "shift", "i")


def fullscreen():
    pyautogui.hotkey("F11")


def private_window():
    pyautogui.hotkey("ctrl", "shift", "n")


def minimize():
    pyautogui.hotkey("alt", "space")
    time.sleep(0.1)
    pyautogui.press("n")


def search_google(query: str):
    pyautogui.hotkey("win")
    time.sleep(0.5)
    pyautogui.typewrite(query, interval=0.02)
    time.sleep(0.3)
    pyautogui.press("enter")
