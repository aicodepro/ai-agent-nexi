from __future__ import annotations

import contextlib
import http.server
import os
import socket
import socketserver
import threading
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WWW = ROOT / "www"
ARTIFACTS = ROOT / "artifacts"
PORT = 8000


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        return sock.connect_ex(("127.0.0.1", port)) == 0


@contextlib.contextmanager
def _static_server_if_needed():
    if _port_open(PORT):
        yield False
        return
    previous = Path.cwd()
    os.chdir(WWW)
    server = socketserver.TCPServer(("127.0.0.1", PORT), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield True
    finally:
        server.shutdown()
        server.server_close()
        os.chdir(previous)


SHIM = r"""
(() => {
  function elementsFor(selector) {
    if (selector === document || selector === window) return [selector];
    if (selector instanceof Element) return [selector];
    try { return Array.from(document.querySelectorAll(String(selector).replace(/:first\b/g, ':first-child'))); }
    catch (_) { return []; }
  }
  function api(elements) {
    return {
      ready(fn) { if (document.readyState !== 'loading') setTimeout(fn, 0); else document.addEventListener('DOMContentLoaded', fn); return this; },
      click(fn) { elements.forEach((el) => el.addEventListener && el.addEventListener('click', fn)); return this; },
      keyup(fn) { elements.forEach((el) => el.addEventListener && el.addEventListener('keyup', fn)); return this; },
      keypress(fn) { elements.forEach((el) => el.addEventListener && el.addEventListener('keypress', fn)); return this; },
      attr(name, value) { if (value === undefined) return elements[0] ? elements[0].getAttribute(name) : undefined; elements.forEach((el) => value === false ? el.removeAttribute(name) : el.setAttribute(name, value === true ? '' : String(value))); return this; },
      text(value) { if (value === undefined) return elements[0] ? elements[0].textContent : ''; elements.forEach((el) => { el.textContent = String(value); }); return this; },
      val(value) { if (value === undefined) return elements[0] && 'value' in elements[0] ? elements[0].value : ''; elements.forEach((el) => { if ('value' in el) el.value = String(value); }); return this; },
      textillate() { return this; },
    };
  }
  window.$ = window.jQuery = (selector) => api(elementsFor(selector));
  window.SiriWave = window.SiriWave || function() { return {}; };
  const eelTarget = window.eel || function() {};
  eelTarget.expose = function(fn) { if (fn && fn.name) window[fn.name] = fn; };
  window.eel = new Proxy(eelTarget, { get(target, prop) { return prop in target ? target[prop] : function() { return function() { return Promise.resolve(null); }; }; } });
})();
"""

BOOTSTRAP_CSS = """
.row{display:flex;flex-wrap:wrap;width:100%;margin:0}.col-md-1{flex:0 0 8.333%;max-width:8.333%}.col-md-10{flex:0 0 83.333%;max-width:83.333%}.col-md-12{flex:0 0 100%;max-width:100%}.d-flex{display:flex!important}.justify-content-center{justify-content:center!important}.align-items-center{align-items:center!important}.text-center{text-align:center!important}.text-light{color:#f8f9fa!important}.mb-4{margin-bottom:1.5rem!important}.mt-4{margin-top:1.5rem!important}.pt-4{padding-top:1.5rem!important}
"""


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"[PW] verdict=FAIL reason=playwright_import_{type(e).__name__}")
        return 1

    ARTIFACTS.mkdir(exist_ok=True)
    idle_png = ARTIFACTS / "ui_restored_idle.png"
    speaking_png = ARTIFACTS / "ui_restored_speaking.png"
    listening_png = ARTIFACTS / "ui_restored_listening.png"

    print("[PW] launch isolated browser")
    with _static_server_if_needed() as owned_server:
        print(f"[PW] static_server_owned={str(owned_server).lower()}")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            page.route(
                "**/*",
                lambda route: route.fulfill(status=200, body="window.eel=window.eel||{};", content_type="application/javascript")
                if route.request.url.endswith("/eel.js")
                else (route.continue_() if route.request.url.startswith(f"http://127.0.0.1:{PORT}") else route.fulfill(status=200, body="", content_type="text/css")),
            )
            page.add_init_script(SHIM)
            try:
                page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="domcontentloaded", timeout=30000)
                page.add_style_tag(content=BOOTSTRAP_CSS)
                page.wait_for_function("Boolean(window.updateNexiState && window.showOutputWorkspace)", timeout=5000)
                page.evaluate("window.updateNexiState({ state: 'idle', source: 'ready' })")
                page.screenshot(path=str(idle_png), full_page=True)
                page.evaluate("window.updateNexiState({ state: 'speaking', source: 'tts', text: 'Demo speech' })")
                page.screenshot(path=str(speaking_png), full_page=True)
                page.evaluate("window.updateNexiState({ state: 'listening', source: 'wake' })")
                page.screenshot(path=str(listening_png), full_page=True)
                result = page.evaluate(
                    """
                    () => {
                      const badge = document.getElementById('SourceBadge');
                      const badges = Array.from(document.querySelectorAll('.source-badge')).filter((el) => getComputedStyle(el).display !== 'none');
                      const orb = document.querySelector('.square').getBoundingClientRect();
                      const input = document.getElementById('TextInput').getBoundingClientRect();
                      window.updateNexiState({ state: 'speaking', source: 'tts' });
                      const speakingBadge = badge.textContent;
                      window.updateNexiState({ state: 'listening', source: 'wake' });
                      const listeningBadge = badge.textContent;
                      return {
                        one_badge: badges.length === 1,
                        speaking_badge: speakingBadge === 'SPEAKING',
                        listening_badge: listeningBadge === 'LISTENING',
                        orb_limited: orb.width <= 260 && orb.height <= 260,
                        input_near_bottom: (window.innerHeight - input.bottom) < 90,
                        screenshots_saved: true,
                      };
                    }
                    """
                )
                screenshots_saved = all(path.exists() and path.stat().st_size > 0 for path in (idle_png, speaking_png, listening_png))
                for key, value in result.items():
                    print(f"[PW] {key}={str(value).lower()}")
                print(f"[PW] screenshots_saved={str(screenshots_saved).lower()}")
                print(f"[PW] screenshot_idle={idle_png}")
                print(f"[PW] screenshot_speaking={speaking_png}")
                print(f"[PW] screenshot_listening={listening_png}")
                passed = all(result.values()) and screenshots_saved
                print(f"[PW] verdict={'PASS' if passed else 'FAIL'}")
                return 0 if passed else 1
            finally:
                context.close()
                browser.close()


if __name__ == "__main__":
    raise SystemExit(main())
