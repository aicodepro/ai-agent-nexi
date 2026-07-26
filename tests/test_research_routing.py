"""Public-web research must not select repository analysis.

Live regression: "Research the top three python web frameworks and compare them"
routed to nexi_run_codebase_research and started a 5-step codebase workflow
instead of answering. web_search had NO examples and NO aliases while the
codebase workflow claimed "research" through four of them - retrieval can only
choose among the things that are actually described.
"""
from __future__ import annotations

import pytest

from engine.tool_registry import router_tool_manifest
from engine import router_semantic as rs

MANIFEST = router_tool_manifest()
BY_NAME = {c["name"]: c for c in MANIFEST}

PUBLIC_RESEARCH = [
    "research the top three python web frameworks and compare them",
    "look up the latest news on ai regulation",
    "compare the iphone and pixel cameras",
    "what is the best laptop for programming",
    "research electric cars",
]

REPO_RESEARCH = [
    "research this repo with agents",
    "run codebase research",
    "research this codebase",
    "analyse this repository with agents",
]


def _top_names(text: str, limit: int = 6) -> list[str]:
    return [c["name"] for c in rs.retrieve_capabilities(text, MANIFEST, limit=limit)]


def test_web_search_is_actually_described():
    """The root cause: an undescribed capability cannot be retrieved."""
    spec = BY_NAME["web_search"]
    assert spec["examples"], "web_search had no examples, so retrieval never saw it"
    assert spec["aliases"], "web_search had no aliases"


@pytest.mark.parametrize("query", PUBLIC_RESEARCH)
def test_public_research_does_not_retrieve_codebase_workflow(query):
    names = _top_names(query)
    assert "web_search" in names, f"web_search not retrieved for {query!r}: {names}"
    if "nexi_run_codebase_research" in names:
        assert names.index("web_search") < names.index("nexi_run_codebase_research"), \
            f"repo analysis outranked web research for {query!r}: {names}"


@pytest.mark.parametrize("query", REPO_RESEARCH)
def test_explicit_repo_requests_still_reach_the_codebase_workflow(query):
    assert "nexi_run_codebase_research" in _top_names(query), \
        f"explicit repo request lost the codebase workflow: {query!r}"


def test_codebase_aliases_all_carry_repo_context():
    """A bare 'research ...' alias is what caused the misroute."""
    repo_words = ("repo", "repositor", "codebase", "project")
    for alias in BY_NAME["nexi_run_codebase_research"]["aliases"]:
        low = alias.lower()
        assert any(w in low for w in repo_words) or "agent research workflow" in low, \
            f"alias {alias!r} would capture generic research requests"
