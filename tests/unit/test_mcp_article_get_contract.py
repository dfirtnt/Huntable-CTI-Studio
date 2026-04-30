"""Contract test: get_article MCP tool consumes a stable article dict shape.

get_article is the primary article retrieval surface for external AI agents.
It reads specific keys from the db.get_article_by_id() result dict; any key
rename in that dict is a silent breaking change for every agent caller.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from mcp.server.fastmcp import FastMCP

from src.huntable_mcp.tools.articles import register

# Markdown sections the rendered output must always contain.
_EXPECTED_SECTIONS = ("**Source:**", "**Published:**", "**URL:**", "## Summary", "## Content")


def _make_get_article_fn(db_mock):
    """Register article tools and return the get_article callable."""
    mcp = FastMCP("test-articles")
    register(mcp, MagicMock(), db_mock)
    tools = {t.name: t for t in mcp._tool_manager.list_tools()}
    return tools["get_article"].fn


def _minimal_article(article_id: int = 42) -> dict:
    return {
        "title": "Ransomware Campaign Targets Healthcare",
        "source_name": "Bleeping Computer",
        "published_at": "2026-01-15T10:00:00",
        "canonical_url": "https://example.com/article/42",
        "summary": "A new ransomware group is targeting healthcare providers.",
        "content": "Full article content here.",
    }


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.asyncio
async def test_get_article_renders_all_expected_sections():
    """get_article output always contains the stable markdown section headers."""
    db = AsyncMock()
    db.get_article_by_id.return_value = _minimal_article()
    fn = _make_get_article_fn(db)

    result = await fn(article_id=42)

    for section in _EXPECTED_SECTIONS:
        assert section in result, f"Expected section '{section}' missing from get_article output"


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.asyncio
async def test_get_article_surfaces_all_consumed_field_values():
    """get_article renders every key it reads from the article dict into output.

    If a field is consumed but its value never reaches the output, the contract
    has drifted and callers lose information silently.
    """
    article = _minimal_article()
    db = AsyncMock()
    db.get_article_by_id.return_value = article
    fn = _make_get_article_fn(db)

    result = await fn(article_id=42)

    assert article["title"] in result
    assert article["source_name"] in result
    assert article["canonical_url"] in result
    assert article["summary"] in result
    assert article["content"] in result


@pytest.mark.unit
@pytest.mark.contract
@pytest.mark.asyncio
async def test_get_article_not_found_is_stable():
    """get_article returns a deterministic not-found message shape."""
    db = AsyncMock()
    db.get_article_by_id.return_value = None
    fn = _make_get_article_fn(db)

    result = await fn(article_id=9999)

    assert "9999" in result
    assert "not found" in result.lower()
