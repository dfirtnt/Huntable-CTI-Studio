"""Unit tests for RSS + archive supplement behavior in ContentFetcher."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.core.fetcher import ContentFetcher
from src.models.article import ArticleCreate
from src.models.source import Source

pytestmark = pytest.mark.unit


def _make_source(*, archive_pages: bool, max_archive_pages: int) -> Source:
    now = datetime.now(UTC)
    return Source(
        id=1,
        identifier="test-source",
        name="Test Source",
        url="https://example.com",
        rss_url="https://example.com/feed",
        check_frequency=1800,
        lookback_days=999,
        active=True,
        config={
            "archive_pages": archive_pages,
            "max_archive_pages": max_archive_pages,
            "extract": {
                "title_selectors": ["h1"],
                "date_selectors": ["time"],
                "body_selectors": ["article"],
            },
        },
        last_check=None,
        last_success=None,
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


def _article(url: str, title: str) -> ArticleCreate:
    now = datetime.now(UTC)
    return ArticleCreate(
        title=title,
        canonical_url=url,
        content="content",
        source_id=1,
        published_at=now,
        modified_at=None,
        authors=[],
        tags=[],
        summary=None,
        article_metadata={},
        content_hash=None,
    )


@pytest.mark.asyncio
async def test_fetch_source_supplements_rss_with_archive_when_enabled():
    fetcher = ContentFetcher()
    source = _make_source(archive_pages=True, max_archive_pages=20)

    rss_articles = [
        _article("https://example.com/post-1", "Post 1"),
        _article("https://example.com/post-2/", "Post 2"),
    ]
    archive_articles = [
        _article("https://example.com/post-2", "Post 2 duplicate"),
        _article("https://example.com/post-3", "Post 3"),
    ]

    fetcher.rss_parser.parse_feed = AsyncMock(return_value=rss_articles)
    fetcher.modern_scraper.scrape_source = AsyncMock(return_value=archive_articles)

    result = await fetcher.fetch_source(source)

    assert result.success is True
    assert result.method == "rss+basic_scraping"
    assert len(result.articles) == 3
    assert [a.canonical_url.rstrip("/") for a in result.articles] == [
        "https://example.com/post-1",
        "https://example.com/post-2",
        "https://example.com/post-3",
    ]


@pytest.mark.asyncio
async def test_fetch_source_returns_rss_only_when_archive_supplement_disabled():
    fetcher = ContentFetcher()
    source = _make_source(archive_pages=False, max_archive_pages=0)

    rss_articles = [
        _article("https://example.com/post-1", "Post 1"),
        _article("https://example.com/post-2", "Post 2"),
    ]

    fetcher.rss_parser.parse_feed = AsyncMock(return_value=rss_articles)
    fetcher.modern_scraper.scrape_source = AsyncMock(return_value=[])

    result = await fetcher.fetch_source(source)

    assert result.success is True
    assert result.method == "rss"
    assert len(result.articles) == 2
    fetcher.modern_scraper.scrape_source.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_source_keeps_rss_method_when_archive_adds_no_unique_articles():
    fetcher = ContentFetcher()
    source = _make_source(archive_pages=True, max_archive_pages=20)

    rss_articles = [
        _article("https://example.com/post-1", "Post 1"),
        _article("https://example.com/post-2", "Post 2"),
    ]
    archive_articles = [
        _article("https://example.com/post-1/", "Post 1 duplicate"),
        _article("https://example.com/post-2/", "Post 2 duplicate"),
    ]

    fetcher.rss_parser.parse_feed = AsyncMock(return_value=rss_articles)
    fetcher.modern_scraper.scrape_source = AsyncMock(return_value=archive_articles)

    result = await fetcher.fetch_source(source)

    assert result.success is True
    assert result.method == "rss"
    assert len(result.articles) == 2
    fetcher.modern_scraper.scrape_source.assert_awaited_once_with(source)


def test_should_supplement_with_archive_supports_nested_config_shape():
    fetcher = ContentFetcher()
    source = _make_source(archive_pages=False, max_archive_pages=0)
    source.config = {
        "config": {
            "archive_pages": True,
            "max_archive_pages": 3,
        }
    }

    assert fetcher._should_supplement_with_archive(source) is True
