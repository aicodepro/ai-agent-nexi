"""Live web retrieval with citations and explicit stale-data behavior."""
from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class Citation:
    title: str
    url: str
    snippet: str
    provider: str
    retrieved_at: float
    published_at: str = ""
    score: float = 0.0


@dataclass
class SearchResult:
    query: str
    answer: str
    citations: list[Citation] = field(default_factory=list)
    provider: str = ""
    retrieved_at: float = field(default_factory=time.time)
    live: bool = False
    stale: bool = False
    errors: list[str] = field(default_factory=list)

    def tool_result(self) -> dict[str, Any]:
        return {
            "handled": True,
            "ok": self.live,
            "success": self.live,
            "verified": self.live and bool(self.citations),
            "tool": "web_search",
            "message": self.answer,
            "query": self.query,
            "provider": self.provider,
            "retrieved_at": self.retrieved_at,
            "live": self.live,
            "stale": self.stale,
            "citations": [asdict(item) for item in self.citations],
            "errors": list(self.errors),
        }


def _timeout() -> float:
    try:
        return max(1.0, min(20.0, float(os.getenv("NEXI_LIVE_SEARCH_TIMEOUT_SECONDS", "6"))))
    except ValueError:
        return 6.0


def _freshness(query: str, mode: str) -> str:
    text = f"{mode} {query}".lower()
    if mode == "news" or any(word in text for word in ("today", "latest", "breaking", "score", "weather now")):
        return "day"
    if any(word in text for word in ("current", "recent", "this week", "price")):
        return "week"
    return ""


def _ttl_seconds(query: str, mode: str) -> float:
    freshness = _freshness(query, mode)
    if freshness == "day":
        return 3600.0
    if freshness == "week":
        return 21600.0
    return 86400.0


class BraveSearchProvider:
    name = "brave"

    def __init__(self, api_key: str, session=requests) -> None:
        self.api_key = api_key
        self.session = session

    def search(self, query: str, *, mode: str, max_results: int) -> list[Citation]:
        params: dict[str, Any] = {"q": query, "count": min(20, max_results)}
        freshness = _freshness(query, mode)
        if freshness:
            params["freshness"] = {"day": "pd", "week": "pw"}[freshness]
        response = self.session.get(
            "https://api.search.brave.com/res/v1/web/search",
            params=params,
            headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
            timeout=_timeout(),
        )
        response.raise_for_status()
        now = time.time()
        return [
            Citation(
                title=str(item.get("title") or "Untitled"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("description") or ""),
                provider=self.name,
                retrieved_at=now,
                published_at=str(item.get("page_age") or ""),
            )
            for item in response.json().get("web", {}).get("results", [])
            if item.get("url")
        ][:max_results]


class TavilySearchProvider:
    name = "tavily"

    def __init__(self, api_key: str, session=requests) -> None:
        self.api_key = api_key
        self.session = session

    def search(self, query: str, *, mode: str, max_results: int) -> list[Citation]:
        payload: dict[str, Any] = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "advanced" if mode == "research" else "basic",
            "topic": "news" if mode == "news" else "general",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
        }
        freshness = _freshness(query, mode)
        if freshness:
            payload["time_range"] = freshness
        response = self.session.post(
            "https://api.tavily.com/search",
            json=payload,
            timeout=_timeout(),
        )
        response.raise_for_status()
        now = time.time()
        return [
            Citation(
                title=str(item.get("title") or "Untitled"),
                url=str(item.get("url") or ""),
                snippet=str(item.get("content") or ""),
                provider=self.name,
                retrieved_at=now,
                published_at=str(item.get("published_date") or ""),
                score=float(item.get("score") or 0.0),
            )
            for item in response.json().get("results", [])
            if item.get("url")
        ][:max_results]


def _ddg_result_url(href: str) -> str:
    parsed = urlparse(href)
    redirected = parse_qs(parsed.query).get("uddg", [])
    return unquote(redirected[0]) if redirected else href


def _parse_ddg_html(html: str, provider_name: str, max_results: int) -> list[Citation]:
    """Parse a DuckDuckGo HTML results page into Citations."""
    soup = BeautifulSoup(html, "html.parser")
    now = time.time()
    results: list[Citation] = []
    for node in soup.select(".result"):
        link = node.select_one(".result__a")
        if link is None or not link.get("href"):
            continue
        snippet = node.select_one(".result__snippet")
        results.append(Citation(
            title=link.get_text(" ", strip=True) or "Untitled",
            url=_ddg_result_url(str(link.get("href"))),
            snippet=snippet.get_text(" ", strip=True) if snippet else "",
            provider=provider_name,
            retrieved_at=now,
        ))
        if len(results) >= max_results:
            break
    return results


class Crawl4AISearchProvider:
    """Search via Crawl4AI: renders the results page in a real browser, so
    JS/lazy-loaded content and light anti-scraping don't blank the results.

    Needs a Chromium install (`python -m playwright install chromium`). If the
    browser stack is missing, search() raises and LiveSearchService falls
    through to the plain-HTTP DuckDuckGo provider.
    """

    name = "crawl4ai"

    def search(self, query: str, *, mode: str, max_results: int) -> list[Citation]:
        from urllib.parse import quote_plus
        html = self._fetch_html(f"https://html.duckduckgo.com/html/?q={quote_plus(query)}")
        return _parse_ddg_html(html, self.name, max_results) if html else []

    @staticmethod
    def _fetch_html(url: str) -> str:
        import asyncio
        from crawl4ai import AsyncWebCrawler

        async def _run() -> str:
            async with AsyncWebCrawler(verbose=False) as crawler:
                result = await crawler.arun(url=url)
                return getattr(result, "html", "") or ""

        try:
            return asyncio.run(_run())
        except RuntimeError:
            # already inside an event loop - run in a dedicated one
            import threading
            box: dict[str, str] = {}

            def _worker() -> None:
                box["html"] = asyncio.new_event_loop().run_until_complete(_run())

            thread = threading.Thread(target=_worker, daemon=True)
            thread.start()
            thread.join(timeout=_timeout() * 3)
            return box.get("html", "")


class DuckDuckGoSearchProvider:
    name = "duckduckgo"

    def __init__(self, session=requests) -> None:
        self.session = session

    @staticmethod
    def _result_url(href: str) -> str:
        return _ddg_result_url(href)

    def search(self, query: str, *, mode: str, max_results: int) -> list[Citation]:
        response = self.session.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers={"User-Agent": "Nexi-Access/1.0"},
            timeout=_timeout(),
        )
        response.raise_for_status()
        return _parse_ddg_html(response.text, self.name, max_results)


def configured_providers(session=requests) -> list[Any]:
    providers: list[Any] = []
    preferred = os.getenv("NEXI_LIVE_SEARCH_PROVIDER", "").strip().lower()
    brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    tavily_key = os.getenv("TAVILY_API_KEY", "").strip()
    keyed = []
    if brave_key:
        keyed.append(BraveSearchProvider(brave_key, session))
    if tavily_key:
        keyed.append(TavilySearchProvider(tavily_key, session))
    if preferred:
        keyed.sort(key=lambda provider: provider.name != preferred)
    providers.extend(keyed)
    # Crawl4AI renders the results page in a real browser. Opt-in, because it
    # costs a browser launch per search; DuckDuckGo stays as the fast fallback.
    crawl4ai_on = os.getenv("NEXI_CRAWL4AI_SEARCH", "").strip().lower() in {"1", "true", "yes", "on"}
    if preferred == "crawl4ai" or crawl4ai_on:
        providers.append(Crawl4AISearchProvider())
    providers.append(DuckDuckGoSearchProvider(session))
    return providers


class LiveSearchService:
    def __init__(self, providers: list[Any] | None = None, temporal_memory=None) -> None:
        self.providers = providers if providers is not None else configured_providers()
        if temporal_memory is None:
            from engine.memory.temporal_memory import get_temporal_memory

            temporal_memory = get_temporal_memory()
        self.temporal_memory = temporal_memory

    def search(self, query: str, *, mode: str = "search", max_results: int = 5) -> SearchResult:
        clean = " ".join(str(query or "").strip().split())
        if not clean:
            return SearchResult(query="", answer="What should I search for?", errors=["empty_query"])
        errors: list[str] = []
        for provider in self.providers:
            try:
                citations = provider.search(clean, mode=mode, max_results=max_results)
            except Exception as exc:
                errors.append(f"{getattr(provider, 'name', 'provider')}:{type(exc).__name__}")
                continue
            if not citations:
                errors.append(f"{getattr(provider, 'name', 'provider')}:no_results")
                continue
            answer = self._format_live(clean, provider.name, citations)
            self.temporal_memory.store(
                clean,
                answer,
                source=provider.name,
                ttl_seconds=_ttl_seconds(clean, mode),
                citations=[asdict(item) for item in citations],
                confidence=max((item.score for item in citations), default=0.7) or 0.7,
            )
            return SearchResult(
                query=clean,
                answer=answer,
                citations=citations,
                provider=provider.name,
                retrieved_at=time.time(),
                live=True,
                errors=errors,
            )

        cached = self.temporal_memory.recall(clean, include_stale=True)
        if cached is not None:
            retrieved = datetime.fromtimestamp(cached.retrieved_at, timezone.utc).isoformat(timespec="seconds")
            warning = (
                f"Live search is unavailable. This cached result was retrieved at {retrieved} "
                f"and may be stale. {cached.content}"
            )
            citations = [Citation(**item) for item in cached.citations if isinstance(item, dict)]
            return SearchResult(
                query=clean,
                answer=warning,
                citations=citations,
                provider=cached.source,
                retrieved_at=cached.retrieved_at,
                live=False,
                stale=True,
                errors=errors,
            )
        return SearchResult(
            query=clean,
            answer="I couldn't verify this with live sources right now.",
            live=False,
            errors=errors or ["no_live_provider"],
        )

    @staticmethod
    def _format_live(query: str, provider: str, citations: list[Citation]) -> str:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        lines = [f"Live results for {query}, retrieved {timestamp} via {provider}:"]
        for index, citation in enumerate(citations[:5], 1):
            detail = citation.snippet.strip() or citation.title
            lines.append(f"{index}. {citation.title}: {detail} [{index}]")
        lines.append("Sources:")
        for index, citation in enumerate(citations[:5], 1):
            lines.append(f"[{index}] {citation.url}")
        return "\n".join(lines)


def live_web_search(query: str, *, mode: str = "search") -> dict[str, Any]:
    return LiveSearchService().search(query, mode=mode).tool_result()
