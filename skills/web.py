"""Website navigation and search."""

import webbrowser
import urllib.parse

SITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "gmail": "https://mail.google.com",
    "github": "https://github.com",
    "stackoverflow": "https://stackoverflow.com",
    "stack overflow": "https://stackoverflow.com",
    "twitter": "https://twitter.com", "x": "https://x.com",
    "linkedin": "https://www.linkedin.com",
    "reddit": "https://www.reddit.com",
    "wikipedia": "https://en.wikipedia.org",
    "amazon": "https://www.amazon.com",
    "netflix": "https://www.netflix.com",
    "spotify": "https://open.spotify.com",
    "chatgpt": "https://chat.openai.com",
    "facebook": "https://www.facebook.com",
    "instagram": "https://www.instagram.com",
    "whatsapp": "https://web.whatsapp.com",
}


def open_website(name: str) -> dict:
    lower = name.lower().strip()
    url = SITES.get(lower)
    if url:
        webbrowser.open(url)
        return {"handled": True, "message": f"Opening {name}."}

    # Try as direct URL
    if "." in name and " " not in name:
        if not name.startswith("http"):
            name = "https://" + name
        webbrowser.open(name)
        return {"handled": True, "message": f"Opening {name}."}

    return {"handled": False, "message": f"I don't have a URL for {name}."}


def web_search(query: str) -> dict:
    url = f"https://www.google.com/search?q={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return {"handled": True, "message": f"Searching for '{query}'."}


def youtube_search(query: str) -> dict:
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(query)}"
    webbrowser.open(url)
    return {"handled": True, "message": f"Searching YouTube for '{query}'."}
