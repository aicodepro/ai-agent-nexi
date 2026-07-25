"""Parallel news: race two sources, first valid result wins.

Real per-article links, no interactive input, no hardcoded API keys. Keyless by
default via Google News RSS; set NEWS_API_KEY to add NewsAPI (direct publisher
URLs) as a second racing source. Mirrors Mark-48's parallel-news idea natively.
"""
import os
import queue
import threading
import time

try:  # XXE / billion-laughs hardened parser (already vendored)
    import defusedxml.ElementTree as ET
except ImportError:  # pragma: no cover - fallback if defusedxml is absent
    import xml.etree.ElementTree as ET

import requests

_TIMEOUT = 6


def _parse_google_rss(xml_bytes, limit):
    """Pure parser: Google News RSS bytes -> list of {title, url, source}."""
    root = ET.fromstring(xml_bytes)
    out = []
    for it in root.findall(".//item")[:limit]:
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        source = (it.findtext("source") or "").strip()
        if title and link:
            out.append({"title": title, "url": link, "source": source or "Google News"})
    return out


def _google_news_rss(topic, limit):
    q = topic or "top stories"
    url = (
        "https://news.google.com/rss/search?q="
        + requests.utils.quote(q)
        + "&hl=en-US&gl=US&ceid=US:en"
    )
    resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    return _parse_google_rss(resp.content, limit)


def _newsapi(topic, limit):
    key = os.getenv("NEWS_API_KEY", "").strip()
    if not key:
        raise RuntimeError("no NEWS_API_KEY")
    resp = requests.get(
        "https://newsapi.org/v2/everything",
        params={"q": topic or "top stories", "pageSize": limit, "sortBy": "publishedAt", "apiKey": key},
        timeout=_TIMEOUT,
    )
    resp.raise_for_status()
    articles = resp.json().get("articles", [])[:limit]
    out = []
    for a in articles:
        title, url = (a.get("title") or "").strip(), (a.get("url") or "").strip()
        if title and url:
            out.append({"title": title, "url": url, "source": (a.get("source") or {}).get("name", "NewsAPI")})
    return out


def get_news(topic="top stories", limit=5, sources=None):
    """Race the sources; return the first non-empty article list, else []."""
    sources = sources if sources is not None else [_newsapi, _google_news_rss]
    result_q = queue.Queue()

    def worker(fn):
        try:
            arts = fn(topic, limit)
            if arts:
                result_q.put(arts)
        except Exception:
            pass  # a losing/failed source is silently ignored

    for fn in sources:
        threading.Thread(target=worker, args=(fn,), daemon=True).start()
    try:
        return result_q.get(timeout=_TIMEOUT + 1)
    except queue.Empty:
        return []


# --- Background prefetch (two-phase startup: news loads concurrently) ---------
_CACHE = {"ts": 0.0, "articles": []}
_CACHE_LOCK = threading.Lock()


def prefetch_news(topic="top stories", limit=5):
    """Warm the news cache in the background (non-blocking). Returns the thread."""
    def _work():
        arts = get_news(topic, limit)
        if arts:
            with _CACHE_LOCK:
                _CACHE["ts"] = time.monotonic()
                _CACHE["articles"] = arts

    t = threading.Thread(target=_work, daemon=True)
    t.start()
    return t


def cached_news(max_age_s=120):
    """Return the prefetched articles if fresh, else []."""
    with _CACHE_LOCK:
        if _CACHE["articles"] and (time.monotonic() - _CACHE["ts"]) <= max_age_s:
            return list(_CACHE["articles"])
    return []


def latestnews(topic=None):
    """Voice-friendly: speak the top headlines. No blocking input()."""
    from engine.command import speak
    arts = cached_news() or get_news(topic or "top stories", limit=5)
    if not arts:
        speak("I couldn't fetch the news right now.")
        return []
    speak(f"Here are the top {len(arts)} headlines.")
    for a in arts:
        speak(a["title"])
    return arts
