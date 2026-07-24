import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_youtube_resolves_to_youtube_dot_com():
    from engine.entity_resolver import resolve_entity

    resolved = resolve_entity("youtube", "website")
    assert resolved["type"] == "website"
    assert resolved["matched"] is True
    assert resolved["url"] == "youtube.com"


def test_browser_resolves_to_chrome_app():
    from engine.entity_resolver import resolve_entity

    resolved = resolve_entity("browser", "app_name")
    assert resolved["type"] == "app"
    assert resolved["matched"] is True
    assert resolved["app_name"] == "chrome"
