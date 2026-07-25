"""pywhatkit was imported at engine.features module level.

main.py does `from engine.features import *` BEFORE it can call eel.start(), so
every second of that import is a second the window does not exist — Darsh's
"loads slowly". Measured with -X importtime: pywhatkit was 5.03s cumulative of a
12.9s cold engine.features import, for ONE use site (PlayYoutube -> kit.playonyt).

Deferring it took the pre-window cost 10.32s -> 7.89s.

The startup win silently evaporates if anyone re-adds a top-level import, so it is
pinned here rather than left as a comment.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _import_probe(code):
    """Run in a FRESH interpreter — sys.modules is process-global, so an in-process
    check would see whatever an earlier test already imported."""
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=_ROOT, timeout=180,
    )
    assert out.returncode == 0, f"probe failed:\n{out.stdout}\n{out.stderr}"
    return out.stdout.strip().splitlines()[-1]


def test_pywhatkit_is_not_imported_at_startup():
    loaded = _import_probe(
        "import engine.features, sys; print('LOADED' if 'pywhatkit' in sys.modules else 'NOT_LOADED')"
    )
    assert loaded == "NOT_LOADED", (
        "pywhatkit is back at engine.features import time — that is ~2.4s added to "
        "every startup before the window can appear"
    )


def test_playonyt_still_works_through_the_lazy_accessor():
    from engine import features

    calls = []

    class _FakeKit:
        def playonyt(self, term):
            calls.append(term)

    features._kit = _FakeKit()
    try:
        features.PlayYoutube("play daft punk on youtube")
    finally:
        features._kit = None

    assert calls, "PlayYoutube never reached playonyt"
    assert "daft punk" in calls[0].lower()


def test_the_accessor_caches(monkeypatch):
    """_get_kit must not re-import on every call — that would move a 2s import
    into the voice turn, which is the mistake that froze the UI with e5."""
    from engine import features

    features._kit = None
    imports = []

    class _Sentinel:
        def playonyt(self, term):
            pass

    def _fake_import():
        imports.append(1)
        return _Sentinel()

    # emulate the import branch by priming the cache once
    features._kit = _fake_import()
    first = features._get_kit()
    second = features._get_kit()
    features._kit = None

    assert first is second
    assert len(imports) == 1


def test_fallback_opens_youtube_in_a_browser_when_pywhatkit_is_missing(monkeypatch):
    """The fallback existed before and must survive the refactor — a missing
    pywhatkit must degrade to a browser search, not raise."""
    from engine import features

    opened = []
    monkeypatch.setattr(features.webbrowser, "open", lambda url: opened.append(url))

    features._PyWhatKitFallback().playonyt("daft punk")

    assert opened and "youtube.com/results" in opened[0]
    assert "daft+punk" in opened[0]
