# Required Imports
import pyautogui
from time import sleep
from pynput.keyboard import Key, Controller

keyboard = Controller()

# Define all necessary functions
def volumeup():
    for i in range(10):
        keyboard.press(Key.media_volume_up)
        keyboard.release(Key.media_volume_up)
        sleep(0.1)

def volumedown():
    for i in range(10):
        keyboard.press(Key.media_volume_down)
        keyboard.release(Key.media_volume_down)
        sleep(0.1)

def open_new_tab():
    pyautogui.hotkey('ctrl', 't')

def close_tab():
    pyautogui.hotkey('ctrl', 'w')

def open_browser_menu():
    pyautogui.hotkey('alt', 'f')

def zoom_in():
    pyautogui.hotkey('ctrl', '+')

def zoom_out():
    pyautogui.hotkey('ctrl', '-')

def refresh_page():
    pyautogui.hotkey('ctrl', 'r')

def switch_to_next_tab():
    pyautogui.hotkey('ctrl', 'tab')

def switch_to_previous_tab():
    pyautogui.hotkey('ctrl', 'shift', 'tab')

def open_history():
    pyautogui.hotkey('ctrl', 'h')

def open_bookmarks():
    pyautogui.hotkey('ctrl', 'd')

def go_back():
    pyautogui.hotkey('alt', 'left')

def go_forward():
    pyautogui.hotkey('alt', 'right')

def open_dev_tools():
    pyautogui.hotkey('ctrl', 'shift', 'i')

def toggle_full_screen():
    pyautogui.hotkey('f11')

def open_private_window():
    pyautogui.hotkey('ctrl', 'shift', 'n')

def minimize_window():
    pyautogui.hotkey('alt', 'space')
    sleep(1)
    pyautogui.hotkey('n')

def chrome_task_manager():
    pyautogui.hotkey('shift', 'esc')

def search_google(query, tabs=4):
    pyautogui.hotkey("win")
    pyautogui.typewrite("chrome")
    pyautogui.press("enter")
    sleep(2)  # Adjust sleep time as needed for your system
    for _ in range(tabs):
        pyautogui.hotkey('tab')
        sleep(0.5)
    pyautogui.hotkey('enter')
    sleep(2)
    pyautogui.typewrite(query)
    pyautogui.press('enter')
