from __future__ import annotations

import asyncio
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "voice_ui_bridge"


async def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        from playwright.async_api import async_playwright
    except Exception as exc:
        print(f"[PLAYWRIGHT] unavailable reason={type(exc).__name__}")
        return 1

    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        await page.add_init_script(
            """
            window.eel = {
              expose: function(fn, name) { window.__eel_exposed = window.__eel_exposed || {}; window.__eel_exposed[name || fn.name] = fn; },
              ui_get_env_status: function() { return function(cb) { cb({groq:false, gemini:false, openrouter:false}); }; },
              ui_get_runtime_status: function() { return function(cb) { cb({wake_enabled:true, active_workflow:false}); }; },
              ui_submit_text: function(text) { window.__submittedText = text; return function(cb) { cb({ok:true, text:text}); }; },
              ui_submit_file_drop: function(paths) { return function(cb) { cb({ok:false}); }; },
              wakeNexiFromUi: function(source) { window.__wakeSource = source; return function(cb) { if (cb) cb('awake'); }; },
              toggleNexiSleepWake: function() { return function(cb) { if (cb) cb('awake'); }; }
            };
            """
        )
        await page.goto((ROOT / "www_mark" / "index.html").as_uri())
        await page.screenshot(path=str(OUT / "online.png"), full_page=True)

        async def state(name: str, source: str = "test", text: str = ""):
            await page.evaluate("([name, source, text]) => window.updateNexiState({state:name, source:source, text:text})", [name, source, text])

        await state("hotword_detected", "hotword")
        await page.screenshot(path=str(OUT / "hotword_detected.png"), full_page=True)
        await state("listening", "hotword")
        await page.screenshot(path=str(OUT / "listening.png"), full_page=True)
        await state("transcribing", "hotword")
        await page.screenshot(path=str(OUT / "transcribing.png"), full_page=True)
        await page.evaluate("() => window.senderText('what is AI in one line')")
        await page.evaluate("() => window.receiverText('AI is software that learns patterns to help solve tasks.')")
        await page.screenshot(path=str(OUT / "activity_log_transcript.png"), full_page=True)
        await state("speaking", "tts")
        await page.screenshot(path=str(OUT / "speaking.png"), full_page=True)
        await state("double_clap_detected", "clap")
        await state("listening", "clap")
        await page.fill("#command-input", "what is AI in one line")
        await page.press("#command-input", "Enter")
        submitted = await page.evaluate("() => window.__submittedText")
        if submitted != "what is AI in one line":
            errors.append("typed chat did not submit through ui_submit_text")
        await page.screenshot(path=str(OUT / "fullscreen.png"), full_page=True)
        badge = await page.text_content("#state-badge")
        log_text = await page.text_content("#activity-log")
        await browser.close()

    required = ["WAKE: Hotword detected.", "SYS: Listening", "You: what is AI", "NEXI: AI is", "WAKE: Double clap detected."]
    missing = [item for item in required if item not in (log_text or "")]
    if missing:
        errors.append("missing activity log entries: " + ", ".join(missing))
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    print("PASS: voice UI bridge validation")
    print(f"screenshots={OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
