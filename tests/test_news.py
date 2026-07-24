"""Parallel news: parser + race logic (engine/news.py). No network."""
import time

import engine.news as news

_RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Alpha wins award</title><link>https://news.google.com/rss/articles/AAA</link><source>BBC</source></item>
<item><title>Beta launches rocket</title><link>https://news.google.com/rss/articles/BBB</link><source>Reuters</source></item>
</channel></rss>"""


def test_parse_google_rss():
    arts = news._parse_google_rss(_RSS, limit=5)
    assert len(arts) == 2
    assert arts[0] == {"title": "Alpha wins award", "url": "https://news.google.com/rss/articles/AAA", "source": "BBC"}
    assert arts[1]["source"] == "Reuters"


def test_parse_respects_limit():
    assert len(news._parse_google_rss(_RSS, limit=1)) == 1


def test_get_news_uses_working_source():
    def failing(t, l):
        raise RuntimeError("down")

    def good(t, l):
        return [{"title": "Real", "url": "https://x/article", "source": "S"}]

    out = news.get_news("tech", sources=[failing, good])
    assert out == [{"title": "Real", "url": "https://x/article", "source": "S"}]


def test_get_news_all_fail_returns_empty():
    def failing(t, l):
        raise RuntimeError("down")

    def empty(t, l):
        return []

    assert news.get_news("tech", sources=[failing, empty]) == []


def test_get_news_first_valid_wins():
    def slow(t, l):
        time.sleep(0.3)
        return [{"title": "slow", "url": "u", "source": "s"}]

    def fast(t, l):
        return [{"title": "fast", "url": "u", "source": "s"}]

    assert news.get_news("x", sources=[slow, fast])[0]["title"] == "fast"


def test_prefetch_warms_cache(monkeypatch):
    def good(t, l):
        return [{"title": "warm", "url": "u", "source": "s"}]

    monkeypatch.setattr(news, "_google_news_rss", good)
    monkeypatch.setattr(news, "_newsapi", good)
    news._CACHE.update({"ts": 0.0, "articles": []})
    news.prefetch_news("x", 3).join(timeout=5)
    assert news.cached_news()[0]["title"] == "warm"


def test_cached_news_stale_returns_empty():
    news._CACHE.update({"ts": time.monotonic() - 1000, "articles": [{"title": "old", "url": "u", "source": "s"}]})
    assert news.cached_news(max_age_s=120) == []
