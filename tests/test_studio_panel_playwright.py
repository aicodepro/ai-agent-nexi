"""The live Studio space, verified in a real browser.

Darsh: "whenever I run the studio or any agency for development, a new space opens
for NEXI — show the results, tell me NEXI is handling this part, live updates."

Pinned here:
  * the panel is HIDDEN until a build starts (it must not clutter normal voice use);
  * it opens on the first studio event and shows which stage/agent/model is running;
  * completed stages are marked done and failures are visibly different;
  * stage text is rendered as TEXT, never markup — stage messages carry tool output.
"""
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
INDEX = ROOT / "www_mark" / "index.html"

pytestmark = pytest.mark.skipif(not INDEX.exists(), reason="www_mark UI not present")

EEL_MOCK = """
    window.eel = new Proxy({}, { get: () => () => Promise.resolve({}) });
    window.eel.expose = function () {};
"""


@pytest.fixture(scope="module")
def page(shared_playwright):
    # Shared session sync_playwright() (tests/conftest.py) to avoid the
    # "Sync API inside the asyncio loop" cascade across browser test modules.
    p = shared_playwright
    try:
        browser = p.chromium.launch()
    except Exception:
        try:
            browser = p.chromium.launch(channel="msedge")
        except Exception as exc:
            pytest.skip(f"no chromium/edge: {type(exc).__name__}")
    pg = browser.new_page(viewport={"width": 1600, "height": 900})
    pg.add_init_script(EEL_MOCK)
    pg.route("**/eel.js", lambda r: r.fulfill(
        status=200, content_type="application/javascript", body=""))
    pg.goto(INDEX.as_uri())
    pg.wait_for_timeout(1200)
    yield pg
    browser.close()


def _emit(page, **payload):
    page.evaluate("p => window.studioEvent(p)", payload)
    page.wait_for_timeout(180)


def test_panel_is_hidden_until_a_build_starts(page):
    assert page.evaluate(
        "!document.getElementById('studio-panel').classList.contains('open')"
    ), "the studio space must not be open during normal voice use"


def test_panel_opens_on_the_first_studio_event(page):
    _emit(page, run_id="run-1", stage="requirements", status="stage_started",
          agent="business-analyst", model="claude-opus-4-8", mode="plan",
          message="Analysing the request", completed=[], total_stages=11)
    assert page.evaluate("document.getElementById('studio-panel').classList.contains('open')")


def test_it_says_what_nexi_is_handling_right_now(page):
    _emit(page, run_id="run-1", stage="implementation", status="stage_started",
          agent="developer-team", model="claude-opus-4-8", mode="acceptEdits",
          message="Writing the code", completed=["requirements", "research"],
          total_stages=11)
    title = page.text_content("#studio-run-title")
    meta = page.text_content("#studio-meta")
    assert "NEXI" in title and "implementation" in title
    assert "developer-team" in meta and "claude-opus-4-8" in meta
    assert "2/11 stages" in meta, meta


def test_completed_stages_are_marked_done(page):
    done = page.evaluate("""() => Array.from(
        document.querySelectorAll('.studio-stage.done .studio-stage-name')
    ).map(e => e.textContent.trim())""")
    assert "requirements" in done and "research" in done


def test_the_active_stage_is_visibly_distinct(page):
    active = page.evaluate("""() => {
        const a = document.querySelector('.studio-stage.active .studio-stage-name');
        return a ? a.textContent.trim() : '';
    }""")
    assert active == "implementation", active


def test_failures_are_shown_as_failed_not_active(page):
    _emit(page, run_id="run-1", stage="qa", status="stage_failed",
          message="tests did not pass", completed=["requirements", "research"],
          total_stages=11)
    failed = page.evaluate("""() => Array.from(
        document.querySelectorAll('.studio-stage.failed .studio-stage-name')
    ).map(e => e.textContent.trim())""")
    assert "qa" in failed


def test_live_log_accumulates_messages(page):
    lines = page.evaluate("document.querySelectorAll('.studio-log-line').length")
    assert lines >= 3, f"expected accumulated live updates, saw {lines}"
    text = page.text_content("#studio-log")
    assert "NEXI is handling this build" in text


def test_stage_output_is_rendered_as_text_not_markup(page):
    """Stage messages carry tool output — it must never be parsed as HTML."""
    _emit(page, run_id="run-1", stage="qa", status="stage_started",
          message="<img src=x onerror=window.__pwned=1>", completed=[], total_stages=11)
    assert page.evaluate("window.__pwned === undefined"), "stage output was parsed as markup"
    assert page.evaluate(
        "document.querySelectorAll('#studio-log img').length === 0"
    ), "markup from stage output created a real element"


def test_a_new_run_resets_the_board(page):
    _emit(page, run_id="run-2", stage="requirements", status="stage_started",
          completed=[], total_stages=11)
    done = page.evaluate("document.querySelectorAll('.studio-stage.done').length")
    failed = page.evaluate("document.querySelectorAll('.studio-stage.failed').length")
    assert done == 0 and failed == 0, "a new build must start from a clean board"
