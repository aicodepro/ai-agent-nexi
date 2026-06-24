"""System utilities — time, weather, clipboard."""

import datetime
import re
import webbrowser


def get_time() -> dict:
    now = datetime.datetime.now()
    time_str = now.strftime("%I:%M %p")
    return {"handled": True, "message": f"It's {time_str}."}


def get_weather(city: str = "") -> dict:
    """Get weather via Open-Meteo API (free, no key needed)."""
    try:
        import requests
        geocode_url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language=en&format=json" if city else ""
        
        if geocode_url:
            geo_resp = requests.get(geocode_url, timeout=5)
            geo_data = geo_resp.json()
            results = geo_data.get("results", [])
            if results:
                lat = results[0]["latitude"]
                lon = results[0]["longitude"]
                loc_name = results[0].get("name", city)
            else:
                return {"handled": True, "message": f"Couldn't find location '{city}'."}
        else:
            lat, lon, loc_name = 51.5, -0.13, "London"  # default
        
        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true&temperature_unit=celsius"
        w_resp = requests.get(weather_url, timeout=5)
        w_data = w_resp.json()
        current = w_data.get("current_weather", {})
        temp = current.get("temperature", "?")
        desc_code = current.get("weathercode", 0)
        
        # Map WMO weather codes to descriptions
        weather_codes = {
            0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
            45: "Foggy", 48: "Depositing rime fog",
            51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
            61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
            71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
            80: "Slight rain showers", 81: "Moderate rain showers", 82: "Violent rain showers",
            95: "Thunderstorm", 96: "Thunderstorm with slight hail", 99: "Thunderstorm with heavy hail",
        }
        condition = weather_codes.get(desc_code, "Unknown")
        
        return {"handled": True, "message": f"{loc_name}: {temp}°C, {condition}"}
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
