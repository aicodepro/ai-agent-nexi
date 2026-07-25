"""State-reactive HUD background layers, verified in a real browser.

Darsh supplied 6 animations (Pinterest_Jarvis_UI_Refs); the HUD used exactly one
of them as a static background. Now each NEXI state cross-fades to its own layer, and
the two 720x1280 PORTRAIT clips became side rails (as a full-bleed background they'd
crop to a narrow centre strip).

Two things are pinned here that a screenshot cannot show:
  * the right layer is visible for each state (a wrong mapping still "looks fine")
  * at most ONE video decodes at a time. A video at opacity:0 still decodes every
    frame, so 4 stacked layers would burn CPU forever and undo the lag fix. This is
    the entire reason hud_layers.js exists, and it fails silently if it breaks.

Runs against file:// with the Eel bridge mocked, like scripts/visual_validate_mark_ui.py.
"""
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = (ROOT / "www_mark" / "index.html")

pytestmark = pytest.mark.skipif(not INDEX.exists(), reason="www_mark UI not present")

# state -> media filename fragment that must be the visible layer
EXPECT = {
    "sleep": "hud_bg", "online": "hud_bg", "error": "hud_bg",
    "listening": "pulse", "recognising": "pulse",
    "thinking": "dna", "saying": "rings",
}

EEL_MOCK = """
    window.eel = new Proxy({}, {
      get: () => () => { const f = () => Promise.resolve({}); f.call = f; return f; }
    });
    window.eel.expose = function () {};
"""


_LOAD_ERRORS = []


@pytest.fixture(scope="module")
def page(shared_playwright):
    # Uses the session-wide sync_playwright() (tests/conftest.py) so a second
    # sync_playwright() in another module can't raise "Sync API inside the
    # asyncio loop" and cascade errors across the run.
    p = shared_playwright
    try:
        browser = p.chromium.launch()
    except Exception:
        # `playwright install` was never run here; Edge is a Chromium channel.
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception as exc:
            pytest.skip(f"no chromium/edge available: {type(exc).__name__}")
    pg = browser.new_page(viewport={"width": 1920, "height": 1080})
    pg.add_init_script(EEL_MOCK)
    pg.route("**/eel.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript", body=""))
    # Attach BEFORE goto so first-paint errors are captured.
    pg.on("console", lambda m: _LOAD_ERRORS.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: _LOAD_ERRORS.append(str(e)))
    pg.goto(INDEX.as_uri())
    pg.wait_for_timeout(2500)
    yield pg
    browser.close()


def _set_state(page, state):
    """Set the state and wait for the cross-fade AND the pause timer to actually settle.

    This used to sleep a flat 950ms (700ms fade + the 60ms pause margin). That is enough
    only on an idle machine: under load the fade and the setTimeout driving the pause both
    stretch, and the test would read mid-fade — seeing the OUTGOING layer still above the
    opacity floor and the incoming one still below it. That produced failures that looked
    like a broken state->layer mapping but vanished on a quiet box. Wait for the condition,
    not for a duration.
    """
    page.evaluate(f"document.body.setAttribute('data-state', '{state}')")
    page.wait_for_function(
        """(state) => {
          const all = Array.from(document.querySelectorAll('.hud-video-bg[data-for]'));
          const wanted = el => (' ' + (el.getAttribute('data-for') || '') + ' ')
                                 .includes(' ' + state + ' ');
          const settled = all.every(el => {
            const o = parseFloat(getComputedStyle(el).opacity);
            return wanted(el) ? o > 0.05 : o <= 0.05;
          });
          const decoding = Array.from(document.querySelectorAll('video.hud-video-bg'))
                                .filter(v => !v.paused).length;
          return settled && decoding <= 1;
        }""",
        arg=state,
        timeout=15000,
    )


def test_every_media_asset_actually_loads(page):
    """A 404'd background is invisible against a dark HUD — it fails silently."""
    _set_state(page, "online")
    # Give the assets time to buffer rather than sampling readyState at one instant: on a
    # loaded machine a perfectly good clip sits at readyState 1 (HAVE_METADATA) for a while
    # and the flat assertion called it a load failure. A genuinely missing asset never
    # reaches readyState 2, so waiting keeps what this test is for.
    try:
        page.wait_for_function(
            """() => Array.from(document.querySelectorAll('video.hud-video-bg, video.hud-rail'))
                          .every(v => v.readyState >= 2)""",
            timeout=15000,
        )
    except Exception:
        pass  # fall through to the assertion below, which reports which asset failed
    media = page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('video.hud-video-bg, video.hud-rail').forEach(v =>
        out.push({src: (v.currentSrc||'').split('/').pop(), ready: v.readyState, w: v.videoWidth}));
      document.querySelectorAll('img.hud-video-gif').forEach(i =>
        out.push({src: (i.currentSrc||'').split('/').pop(), ready: i.complete ? 4 : 0, w: i.naturalWidth}));
      return out;
    }""")
    assert len(media) >= 6, f"expected 6 assets, found {len(media)}: {media}"
    for m in media:
        assert m["ready"] >= 2 and m["w"] > 0, f"asset failed to load: {m}"


@pytest.mark.parametrize("state,fragment", sorted(EXPECT.items()))
def test_each_state_shows_its_own_layer(page, state, fragment):
    _set_state(page, state)
    visible = page.evaluate("""() => {
      const v = [];
      document.querySelectorAll('.hud-video-bg').forEach(el => {
        if (parseFloat(getComputedStyle(el).opacity) > 0.05)
          v.push((el.currentSrc||el.src||'').split('/').pop());
      });
      return v;
    }""")
    assert any(fragment in v for v in visible), (
        f"state {state!r} should show {fragment}, but visible layers were {visible}"
    )


@pytest.mark.parametrize("state", sorted(EXPECT))
def test_only_one_video_decodes_at_a_time(page, state):
    """The whole point of hud_layers.js. opacity:0 does NOT stop decoding."""
    _set_state(page, state)
    playing = page.evaluate(
        "Array.from(document.querySelectorAll('video.hud-video-bg'))"
        ".filter(v => !v.paused).length"
    )
    assert playing <= 1, f"state {state}: {playing} background videos decoding at once"


def test_portrait_clips_are_rails_not_backgrounds(page):
    """compass/terminal are 720x1280. As a background they'd crop to a strip."""
    rails = page.evaluate("""() => Array.from(document.querySelectorAll('.hud-rail')).map(v =>
        ({src: (v.currentSrc||'').split('/').pop(), w: v.getBoundingClientRect().width}))""")
    names = " ".join(r["src"] for r in rails)
    assert "compass" in names and "terminal" in names, f"rails missing: {rails}"
    for r in rails:
        assert r["w"] > 0, f"rail not rendered: {r}"
    # ...and they must NOT also be stacked as background layers
    bg = page.evaluate(
        "Array.from(document.querySelectorAll('.hud-video-bg'))"
        ".map(v => (v.currentSrc||v.src||'').split('/').pop()).join(' ')"
    )
    assert "compass" not in bg and "terminal" not in bg, f"portrait clip used as background: {bg}"


def test_sleep_pauses_all_video_decoding_and_orb_animation(page):
    page.evaluate("window.setOrbState('sleeping'); document.body.setAttribute('data-state', 'sleep')")
    page.wait_for_timeout(950)

    state = page.evaluate("""() => ({
      playing: Array.from(document.querySelectorAll('video')).filter(v => !v.paused).length,
      orbAnimating: window.__nexiHudOrb && window.__nexiHudOrb.isAnimating()
    })""")

    assert state == {"playing": 0, "orbAnimating": False}


def test_collapsed_dashboard_does_not_poll(page):
    calls = page.evaluate("""() => {
      let calls = 0;
      window.eel = {getDashboardState: () => () => { calls += 1; }};
      const panel = document.getElementById('diagnostics-dashboard');
      panel.classList.add('collapsed');
      window.refreshDashboard();
      const collapsed = calls;
      panel.classList.remove('collapsed');
      window.refreshDashboard();
      return {collapsed, expanded: calls};
    }""")

    assert calls == {"collapsed": 0, "expanded": 1}


def test_no_console_errors(page):
    """Errors are collected from first paint (listener attached before goto) and
    through every state switch the other tests drove."""
    assert not _LOAD_ERRORS, f"console errors: {_LOAD_ERRORS}"
