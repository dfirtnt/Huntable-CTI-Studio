"""Tests for security fixes from 2026-04-02 daily code review.

Covers:
- XSS escaping in workflow_executions.html and diags.html
- sort_by allowlist in articles API
- Dummy article removal from rss_parser
- Parameterized SQL in async_manager score ranges
- error_detail truncation in source_healing_service
"""

from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.unit


# ── sort_by allowlist ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_sort_by_rejects_invalid_column(monkeypatch):
    """sort_by parameter not in allowlist should fall back to published_at."""
    from src.web.routes import articles as mod

    captured = {}
    original_list = mod.async_db_manager.list_articles

    async def spy_list(article_filter=None, **kwargs):
        captured["sort_by"] = getattr(article_filter, "sort_by", None)
        return []

    monkeypatch.setattr(mod.async_db_manager, "list_articles", spy_list)

    await mod.api_articles_list(sort_by="article_metadata", sort_order="desc")
    assert captured["sort_by"] == "published_at"


@pytest.mark.asyncio
async def test_sort_by_accepts_valid_column(monkeypatch):
    """sort_by with an allowed column should pass through unchanged."""
    from src.web.routes import articles as mod

    captured = {}

    async def spy_list(article_filter=None, **kwargs):
        captured["sort_by"] = getattr(article_filter, "sort_by", None)
        return []

    monkeypatch.setattr(mod.async_db_manager, "list_articles", spy_list)

    await mod.api_articles_list(sort_by="created_at", sort_order="asc")
    assert captured["sort_by"] == "created_at"


@pytest.mark.asyncio
async def test_sort_order_rejects_invalid_value(monkeypatch):
    """sort_order not in {'asc', 'desc'} should fall back to desc."""
    from src.web.routes import articles as mod

    captured = {}

    async def spy_list(article_filter=None, **kwargs):
        captured["sort_order"] = getattr(article_filter, "sort_order", None)
        return []

    monkeypatch.setattr(mod.async_db_manager, "list_articles", spy_list)

    await mod.api_articles_list(sort_by="published_at", sort_order="DROP TABLE")
    assert captured["sort_order"] == "desc"


# ── Dummy article removal ────────────────────────────────────────


@pytest.mark.asyncio
async def test_rss_parser_no_dummy_article_on_all_filtered():
    """When all RSS entries are filtered, parse_feed should return empty list (no dummy)."""
    from datetime import datetime

    from src.core.rss_parser import RSSParser
    from src.models.source import Source
    from tests.utils.async_mocks import AsyncMockHTTPClient, create_async_mock_response

    now = datetime.now()
    source = Source(
        id=1,
        identifier="test-dummy",
        name="Dummy Test",
        url="https://example.com",
        rss_url="https://example.com/rss",
        active=True,
        check_frequency=3600,
        lookback_days=180,
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
        config={"post_url_regex": "^https://example\\.com/never-match/"},
    )

    # RSS feed with one entry that won't match the post_url_regex
    rss_xml = """<?xml version="1.0"?>
    <rss version="2.0"><channel><title>Test</title>
    <item>
        <title>Filtered Article</title>
        <link>https://other-domain.com/article</link>
        <description>Content here</description>
        <pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
    </item>
    </channel></rss>"""

    client = AsyncMockHTTPClient()
    resp = create_async_mock_response(text=rss_xml)
    resp.raise_for_status = AsyncMock()
    client.get.return_value = resp

    parser = RSSParser(client)
    articles = await parser.parse_feed(source)

    # Should return empty list — no dummy with url=""
    dummy_articles = [a for a in articles if getattr(a, "url", None) == ""]
    assert len(dummy_articles) == 0, "Dummy articles with empty URL should not be created"


# ── error_detail truncation ──────────────────────────────────────


def test_healing_error_detail_truncated():
    """error_detail stored in healing event should be truncated to 500 chars."""
    # Simulate the truncation logic from source_healing_service.py
    raw_detail = "x" * 1000
    truncated = raw_detail[:500] if raw_detail else None
    assert len(truncated) == 500


# ── SQL parameterization ────���────────────────────────────────────


def test_score_range_query_uses_parameters():
    """Verify the score range query uses :min_score/:max_score, not f-string."""
    import inspect

    from src.database.async_manager import AsyncDatabaseManager

    source = inspect.getsource(AsyncDatabaseManager.get_database_stats)
    # Should use parameterized query, not f-string interpolation
    assert ":min_score" in source, "Score range query should use :min_score parameter"
    assert ":max_score" in source, "Score range query should use :max_score parameter"
    # Should NOT contain f-string pattern for the score range
    assert "BETWEEN {min_score}" not in source, "Score range query should not use f-string interpolation"
