"""Chrome browser control actions."""

import webbrowser
import urllib.parse


def handle_open_chrome(entity: str = "") -> dict:
    try:
        webbrowser.open("https://www.google.com")
        return {"ok": True, "message": "Chrome opened."}
    except Exception as e:
        return {"ok": False, "message": f"Failed: {e}"}


def handle_open_url(entity: str) -> dict:
    url = entity.strip()
    if not url.startswith("http"):
        url = "https://" + url
    webbrowser.open(url)
    return {"ok": True, "message": f"Opening {url}"}


def handle_search_google(entity: str) -> dict:
    url = f"https://www.google.com/search?q={urllib.parse.quote(entity)}"
    webbrowser.open(url)
    return {"ok": True, "message": f"Searching: {entity}"}


def handle_search_youtube(entity: str) -> dict:
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(entity)}"
    webbrowser.open(url)
    return {"ok": True, "message": f"YouTube: {entity}"}


def register_chrome_controls(registry):
    registry.register("open_chrome", handle_open_chrome, risk="safe")
    registry.register("open_url", handle_open_url, risk="safe")
    registry.register("search_google", handle_search_google, risk="safe")
    registry.register("search_youtube", handle_search_youtube, risk="safe")
