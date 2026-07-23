import re
import shlex
import subprocess
import time


def extract_yt_term(command):
    # Define a regular expression pattern to capture the song name
    pattern = r'play\s+(.*?)\s+on\s+youtube'
    # Use re.search to find the match in the command
    match = re.search(pattern, command, re.IGNORECASE)
    # If a match is found, return the extracted song name; otherwise, return None
    return match.group(1) if match else None


def remove_words(input_string, words_to_remove):
    # Split the input string into words
    words = input_string.split()

    # Remove unwanted words
    filtered_words = [word for word in words if word.lower() not in words_to_remove]

    # Join the remaining words back into a string
    result_string = ' '.join(filtered_words)

    return result_string



def _adb_shell(*args):
    """Run `adb shell <args>` with no host shell involved.

    These used to be f-strings handed to os.system, so a message containing
    `" & calc & "` ran on THIS machine. The list form removes the host shell
    entirely: nothing in args can be metacharacters, only arguments.
    """
    subprocess.run(["adb", "shell", *args], check=False)
    time.sleep(1)


# key events like receive call, stop call, go back
def keyEvent(key_code):
    _adb_shell("input", "keyevent", str(key_code))

# Tap event used to tap anywhere on screen
def tapEvents(x, y):
    _adb_shell("input", "tap", str(x), str(y))

# Input Event is used to insert text in mobile
def adbInput(message):
    # adb hands its argv to the DEVICE's shell, so the message needs device-side
    # quoting too — the list form above only protects the host.
    _adb_shell("input", "text", shlex.quote(str(message)))

# to go complete back
def goback(key_code):
    for i in range(6):
        keyEvent(key_code)

# To replace space in string with %s for complete message send
def replace_spaces_with_percent_s(input_string):
    return input_string.replace(' ', '%s')
