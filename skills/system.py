"""System utilities — time, weather, clipboard."""

import datetime
import re
import webbrowser


def get_time() -> dict:
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p")
    return {"handled": True, "message": f"It's {time_str}."}


def get_weather(city: str = "") -> dict:
    """Get weather via Google search scraping."""
    try:
        import requests
        from bs4 import BeautifulSoup
        query = f"weather {city}" if city else "weather"
        url = f"https://www.google.com/search?q={query}"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")

        temp = soup.select_one("#wob_tm")
        desc = soup.select_one("#wob_dc")
        loc = soup.select_one("#wob_loc")

        if temp:
            parts = []
            if loc:
                parts.append(loc.get_text(strip=True))
            parts.append(f"{temp.get_text(strip=True)}°C")
            if desc:
                parts.append(desc.get_text(strip=True))
            return {"handled": True, "message": ", ".join(parts)}
        return {"handled": True, "message": "Couldn't get weather info."}
    except Exception as e:
        return {"handled": False, "message": f"Weather check failed: {e}"}


def read_clipboard() -> dict:
    try:
        import pyperclip
        content = pyperclip.paste()
        if content:
            return {"handled": True, "message": f"Clipboard: {content[:500]}"}
        return {"handled": True, "message": "Clipboard is empty."}
    except Exception:
        return {"handled": False, "message": "Couldn't read clipboard."}


def copy_to_clipboard(text: str) -> dict:
    try:
        import pyperclip
        pyperclip.copy(text)
        return {"handled": True, "message": "Copied to clipboard."}
    except Exception:
        return {"handled": False, "message": "Couldn't copy to clipboard."}


def play_music(query: str) -> dict:
    """Open Spotify or YouTube for music."""
    import urllib.parse
    if query:
        url = f"https://open.spotify.com/search/{urllib.parse.quote(query)}"
        webbrowser.open(url)
        return {"handled": True, "message": f"Playing '{query}' on Spotify."}
    return {"handled": False, "message": "What would you like to play?"}
