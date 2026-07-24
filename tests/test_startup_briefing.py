"""Two-phase startup (engine/startup_briefing.py). No network, no heavy imports."""
import time

import engine.startup_briefing as sb


def _stub(monkeypatch):
    """Neutralize reset + network so only phase logic is exercised."""
    import engine.session_reset as sr
    import engine.news as news_mod
    monkeypatch.setattr(sr, "reset_session", lambda: [])
    monkeypatch.setattr(news_mod, "prefetch_news", lambda *a, **k: None)
    return news_mod


def test_greets_and_no_briefing_when_disabled(monkeypatch):
    _stub(monkeypatch)
    monkeypatch.delenv("NEXI_STARTUP_BRIEFING", raising=False)
    greeted, spoken = [], []
    sb.two_phase_startup(greet=lambda: greeted.append(1), speak=lambda t: spoken.append(t))
    time.sleep(0.1)
    assert greeted == [1]
    assert spoken == []  # phase-2 briefing off by default


def test_briefing_speaks_headline_when_enabled(monkeypatch):
    news_mod = _stub(monkeypatch)
    monkeypatch.setattr(news_mod, "cached_news", lambda *a, **k: [{"title": "BIG NEWS", "url": "u", "source": "s"}])
    monkeypatch.setenv("NEXI_STARTUP_BRIEFING", "1")
    spoken = []
    sb.two_phase_startup(greet=None, speak=lambda t: spoken.append(t))
    for _ in range(40):
        if spoken:
            break
        time.sleep(0.05)
    assert spoken and "BIG NEWS" in spoken[0]
