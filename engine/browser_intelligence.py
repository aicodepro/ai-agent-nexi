"""Browser Intelligence Layer (Roadmap Feature #9, read-only surface).

Tool cards
----------
read_current_page   role: browser agent | risk: LOW | confirm: never | verifier: page title/url confirmed | memory: never store
list_browser_tabs   role: browser agent | risk: LOW | confirm: never | verifier: tab list read            | memory: never store
read_browser_console role: browser agent | risk: LOW | confirm: never | verifier: console sampled          | memory: never store

READ-ONLY: these inspect a Chromium browser (Chrome/Edge) that was started with remote
debugging (`--remote-debugging-port=9222`). Tab title/URL come from the CDP HTTP endpoint
(no extra dependency). Page text and console use Playwright if installed. The write-path
(click/type/fill) is intentionally NOT built here. Everything degrades gracefully to a
verified, honest message when no debug browser (or Playwright) is available. Never exposes
passwords/cookies — only page text, titles, URLs, and console messages.
"""

from __future__ import annotations

import os
from typing import Any

_NO_BROWSER_MSG = ("I can't read the browser. Start Chrome or Edge with remote debugging "
                   "(--remote-debugging-port=9222) so I can read your pages.")


def _ok(message: str, **extra: Any) -> dict[str, Any]:
    return {"handled": True, "ok": True, "success": True, "verified": True,
            "tool": extra.pop("tool", "browser_intelligence"), "message": message, **extra}


def _cdp_base() -> str:
    return os.getenv("BROWSER_CDP_URL", "http://localhost:9222").rstrip("/")


def _fetch_targets() -> list[dict[str, Any]]:
    """Page targets from the CDP HTTP endpoint (urllib, no extra dependency)."""
    import json
    import urllib.request
    with urllib.request.urlopen(_cdp_base() + "/json/list", timeout=2) as resp:
        data = json.loads(resp.read().decode("utf-8", "ignore"))
    return [t for t in data if isinstance(t, dict) and t.get("type") == "page"]


def _safe_targets() -> list[dict[str, Any]]:
    try:
        return _fetch_targets() or []
    except Exception:
        return []


def _page_text(target: dict[str, Any]) -> str:
    """Visible text of a target page via Playwright (empty if Playwright unavailable)."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return ""
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(_cdp_base())
            try:
                for ctx in browser.contexts:
                    for page in ctx.pages:
                        if page.url == target.get("url"):
                            return (page.inner_text("body") or "")[:4000]
            finally:
                browser.close()
    except Exception:
        return ""
    return ""


def _capture_console(target: dict[str, Any], window_ms: int = 1200) -> list[str]:
    """Best-effort console capture over a short listen window via Playwright."""
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return []
    messages: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(_cdp_base())
            try:
                pages = [pg for ctx in browser.contexts for pg in ctx.pages]
                if pages:
                    page = pages[0]
                    page.on("console", lambda m: messages.append(f"{m.type}: {m.text}"[:200]))
                    page.wait_for_timeout(window_ms)
            finally:
                browser.close()
    except Exception:
        pass
    return messages


def read_current_page(slots: dict | None = None) -> dict[str, Any]:
    targets = _safe_targets()
    if not targets:
        return _ok(_NO_BROWSER_MSG, tool="read_current_page", available=False, title="", url="", text="")
    target = targets[0]
    title = target.get("title") or "(untitled)"
    url = target.get("url") or ""
    try:
        text = _page_text(target) or ""
    except Exception:
        text = ""
    excerpt = " ".join(text.split())[:200]
    msg = f"Current page: {title} — {url}." + (f" {excerpt}" if excerpt else "")
    return _ok(msg, tool="read_current_page", available=True, title=title, url=url, text=text)


def list_browser_tabs(slots: dict | None = None) -> dict[str, Any]:
    targets = _safe_targets()
    tabs = [{"title": t.get("title", ""), "url": t.get("url", "")} for t in targets]
    if not tabs:
        return _ok(_NO_BROWSER_MSG, tool="list_browser_tabs", available=False, tab_count=0, tabs=[])
    preview = "; ".join(t["title"] for t in tabs[:5] if t["title"])
    msg = f"You have {len(tabs)} browser tab{'s' if len(tabs) != 1 else ''} open" + (f": {preview}." if preview else ".")
    return _ok(msg, tool="list_browser_tabs", available=True, tab_count=len(tabs), tabs=tabs)


def read_browser_console(slots: dict | None = None) -> dict[str, Any]:
    targets = _safe_targets()
    if not targets:
        return _ok(_NO_BROWSER_MSG, tool="read_browser_console", available=False, errors=[])
    try:
        errors = _capture_console(targets[0]) or []
    except Exception:
        errors = []
    if errors:
        msg = f"Console shows {len(errors)} message(s): " + " | ".join(errors[:3])
    else:
        msg = "No console messages captured in the listen window."
    return _ok(msg, tool="read_browser_console", available=True, errors=errors)
