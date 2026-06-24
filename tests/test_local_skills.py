import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


@pytest.fixture(autouse=True)
def _clear_workflow():
    from engine.workflow_state import clear_workflow
    clear_workflow()
    yield
    clear_workflow()


def test_open_app_asks_app_when_missing():
    from engine.local_skills import handle_local_skill
    from engine.workflow_state import get_workflow

    result = handle_local_skill("open app")
    assert result.handled is True
    assert result.message == "Which app should I open?"
    assert get_workflow()["name"] == "local_open_app"


def test_open_app_uses_pyautogui_fallback(monkeypatch):
    from engine.local_skills import handle_local_skill

    calls = []
    fake_pyautogui = SimpleNamespace(
        press=lambda key: calls.append(("press", key)),
        write=lambda text: calls.append(("write", text)),
    )
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    result = handle_local_skill("open made up app")
    assert result.handled is True
    assert ("press", "win") in calls
    assert ("write", "made up app") in calls
    assert ("press", "enter") in calls


def test_open_website_asks_site_when_missing():
    from engine.local_skills import handle_local_skill

    result = handle_local_skill("open website")
    assert result.handled is True
    assert result.message == "Which website should I open?"


def test_search_asks_query_when_missing():
    from engine.local_skills import handle_local_skill

    result = handle_local_skill("search web")
    assert result.handled is True
    assert result.message == "What should I search for?"


def test_note_asks_text_when_missing():
    from engine.local_skills import handle_local_skill

    result = handle_local_skill("take note")
    assert result.handled is True
    assert result.message == "What should I write in the note?"


def test_screenshot_default_location(monkeypatch, tmp_path):
    from engine.local_skills import handle_local_skill

    saved = []
    fake_image = SimpleNamespace(save=lambda path: saved.append(path))
    fake_pyautogui = SimpleNamespace(screenshot=lambda: fake_image)
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    result = handle_local_skill("take screenshot")
    assert result.handled is True
    assert saved
    assert str(tmp_path / "Pictures" / "Nexi Screenshots") in saved[0]


def test_create_file_asks_missing_slots():
    from engine.local_skills import handle_local_skill
    from engine.workflow_state import get_workflow

    result = handle_local_skill("create file")
    assert result.handled is True
    assert result.message == "What should I name the file?"
    assert get_workflow()["name"] == "local_create_file"
    assert get_workflow()["step"] == "ask_name"
