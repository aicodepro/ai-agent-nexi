"""Crawl4AI search provider: parsing + registration. Offline (no browser)."""
from __future__ import annotations

from unittest.mock import patch

from engine.live_intelligence import (
    Crawl4AISearchProvider,
    _parse_ddg_html,
    configured_providers,
)

_SAMPLE = """
<div class="result">
  <a class="result__a" href="https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa">Example A</a>
  <div class="result__snippet">First snippet</div>
</div>
<div class="result">
  <a class="result__a" href="https://example.org/b">Example B</a>
  <div class="result__snippet">Second snippet</div>
</div>
"""


def test_parse_ddg_html_decodes_redirect_and_snippet():
    cites = _parse_ddg_html(_SAMPLE, "crawl4ai", 5)
    assert [c.url for c in cites] == ["https://example.com/a", "https://example.org/b"]
    assert cites[0].title == "Example A"
    assert cites[0].snippet == "First snippet"
    assert cites[0].provider == "crawl4ai"


def test_parse_ddg_html_respects_max_results():
    assert len(_parse_ddg_html(_SAMPLE, "crawl4ai", 1)) == 1


def test_crawl4ai_provider_parses_fetched_html():
    provider = Crawl4AISearchProvider()
    with patch.object(Crawl4AISearchProvider, "_fetch_html", return_value=_SAMPLE):
        cites = provider.search("anything", mode="search", max_results=5)
    assert [c.url for c in cites] == ["https://example.com/a", "https://example.org/b"]


def test_crawl4ai_empty_html_yields_no_results():
    provider = Crawl4AISearchProvider()
    with patch.object(Crawl4AISearchProvider, "_fetch_html", return_value=""):
        assert provider.search("anything", mode="search", max_results=5) == []


def test_crawl4ai_is_opt_in(monkeypatch):
    monkeypatch.delenv("NEXI_CRAWL4AI_SEARCH", raising=False)
    monkeypatch.setenv("NEXI_LIVE_SEARCH_PROVIDER", "")
    assert "crawl4ai" not in [p.name for p in configured_providers()]


def test_crawl4ai_enabled_by_env_and_ordered_before_duckduckgo(monkeypatch):
    monkeypatch.setenv("NEXI_CRAWL4AI_SEARCH", "true")
    monkeypatch.setenv("NEXI_LIVE_SEARCH_PROVIDER", "")
    names = [p.name for p in configured_providers()]
    assert "crawl4ai" in names and "duckduckgo" in names
    assert names.index("crawl4ai") < names.index("duckduckgo")
