"""Unit tests for ContentFetcher helper methods and statistics.

These methods remained after the dead-code deletion of ScheduledFetcher and
its feeder chain (fetch_multiple_sources / fetch_due_sources) but had no
direct test coverage.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.core.fetcher import ContentFetcher, FetchResult
from src.models.article import ArticleCreate
from src.models.source import Source

pytestmark = pytest.mark.unit


# -- helpers ------------------------------------------------------------------


def _make_source(*, config: dict | None = None, name: str = "Test Source") -> Source:
    now = datetime.now(UTC)
    return Source(
        id=1,
        identifier="test-source",
        name=name,
        url="https://example.com",
        rss_url="https://example.com/feed",
        check_frequency=1800,
        lookback_days=999,
        active=True,
        config=config or {},
        last_check=None,
        last_success=None,
        consecutive_failures=0,
        total_articles=0,
        average_response_time=0.0,
        created_at=now,
        updated_at=now,
    )


def _article(url: str | None, title: str = "T") -> ArticleCreate:
    return ArticleCreate(
        title=title,
        canonical_url=url,
        content="content",
        source_id=1,
        published_at=datetime.now(UTC),
        modified_at=None,
        authors=[],
        tags=[],
        summary=None,
        article_metadata={},
        content_hash=None,
    )


# -- _should_use_playwright ---------------------------------------------------


class TestShouldUsePlaywright:
    def test_false_for_empty_config(self):
        fetcher = ContentFetcher()
        assert fetcher._should_use_playwright(_make_source()) is False

    def test_true_when_flat_config_has_use_playwright(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"use_playwright": True})
        assert fetcher._should_use_playwright(source) is True

    def test_true_when_nested_config_has_use_playwright(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"config": {"use_playwright": True}})
        assert fetcher._should_use_playwright(source) is True

    def test_false_when_use_playwright_not_set(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"archive_pages": True})
        assert fetcher._should_use_playwright(source) is False

    def test_false_for_non_dict_config(self):
        fetcher = ContentFetcher()
        source = _make_source()
        source.config = "not-a-dict"  # type: ignore[assignment]
        assert fetcher._should_use_playwright(source) is False


@pytest.mark.asyncio
async def test_playwright_source_reports_when_browser_dependency_is_unavailable(monkeypatch):
    fetcher = ContentFetcher()
    source = _make_source(config={"use_playwright": True})
    source.rss_url = None
    monkeypatch.setattr(fetcher, "_playwright_scraper_class", lambda: None)

    async with fetcher:
        result = await fetcher.fetch_source(source)

    assert result.success is False
    assert result.method == "playwright_unavailable"
    assert "Playwright is unavailable" in result.error


# -- _has_modern_config -------------------------------------------------------


class TestHasModernConfig:
    def test_false_for_empty_config(self):
        fetcher = ContentFetcher()
        assert fetcher._has_modern_config(_make_source()) is False

    def test_true_when_discovery_strategies_present(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"discovery": {"strategies": ["sitemap"]}})
        assert fetcher._has_modern_config(source) is True

    def test_true_when_extract_has_title_selectors(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"extract": {"title_selectors": ["h1"]}})
        assert fetcher._has_modern_config(source) is True

    def test_true_when_extract_has_date_selectors(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"extract": {"date_selectors": ["time"]}})
        assert fetcher._has_modern_config(source) is True

    def test_true_when_extract_has_body_selectors(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"extract": {"body_selectors": ["article"]}})
        assert fetcher._has_modern_config(source) is True

    def test_false_when_extract_has_no_selectors(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"extract": {}})
        assert fetcher._has_modern_config(source) is False

    def test_false_when_discovery_has_no_strategies(self):
        fetcher = ContentFetcher()
        source = _make_source(config={"discovery": {}})
        assert fetcher._has_modern_config(source) is False


# -- _merge_articles_by_url ---------------------------------------------------


class TestMergeArticlesByUrl:
    def test_empty_lists_return_empty(self):
        fetcher = ContentFetcher()
        assert fetcher._merge_articles_by_url([], []) == []

    def test_preserves_primary_order(self):
        fetcher = ContentFetcher()
        a1 = _article("https://x.com/a", "A")
        a2 = _article("https://x.com/b", "B")
        result = fetcher._merge_articles_by_url([a1, a2], [])
        assert result == [a1, a2]

    def test_appends_secondary_after_primary(self):
        fetcher = ContentFetcher()
        a1 = _article("https://x.com/a", "A")
        b1 = _article("https://x.com/b", "B")
        result = fetcher._merge_articles_by_url([a1], [b1])
        assert result == [a1, b1]

    def test_deduplicates_by_canonical_url(self):
        fetcher = ContentFetcher()
        a1 = _article("https://x.com/a", "A")
        a2 = _article("https://x.com/a", "A dup")
        result = fetcher._merge_articles_by_url([a1], [a2])
        assert len(result) == 1
        assert result[0].title == "A"

    def test_trailing_slash_is_normalized_for_dedup(self):
        fetcher = ContentFetcher()
        a1 = _article("https://x.com/a", "A")
        a2 = _article("https://x.com/a/", "A dup")
        result = fetcher._merge_articles_by_url([a1], [a2])
        assert len(result) == 1
        assert result[0].title == "A"

    def test_articles_without_url_are_kept(self):
        fetcher = ContentFetcher()
        a_no_url = _article("", "No URL")
        a_with_url = _article("https://x.com/a", "A")
        result = fetcher._merge_articles_by_url([a_no_url], [a_with_url])
        assert len(result) == 2
        assert result[0].title == "No URL"

    def test_blank_url_articles_are_kept(self):
        fetcher = ContentFetcher()
        a_blank = _article("  ", "Blank URL")
        result = fetcher._merge_articles_by_url([a_blank], [])
        assert len(result) == 1


# -- _update_stats + get_statistics + reset_statistics ------------------------


class TestStatistics:
    def test_initial_stats_are_zeroed(self):
        fetcher = ContentFetcher()
        stats = fetcher.get_statistics()
        assert stats["total_fetches"] == 0
        assert stats["successful_fetches"] == 0
        assert stats["failed_fetches"] == 0
        assert stats["articles_collected"] == 0
        assert stats["avg_response_time"] == 0.0

    def test_update_stats_on_success(self):
        fetcher = ContentFetcher()
        fetcher._update_stats("rss_successes", article_count=5, response_time=1.0, success=True)
        stats = fetcher.get_statistics()
        assert stats["total_fetches"] == 1
        assert stats["successful_fetches"] == 1
        assert stats["failed_fetches"] == 0
        assert stats["articles_collected"] == 5
        assert stats["rss_successes"] == 1
        assert stats["avg_response_time"] == 1.0

    def test_update_stats_on_failure(self):
        fetcher = ContentFetcher()
        fetcher._update_stats("legacy_scraping_successes", article_count=0, response_time=2.0, success=False)
        stats = fetcher.get_statistics()
        assert stats["total_fetches"] == 1
        assert stats["successful_fetches"] == 0
        assert stats["failed_fetches"] == 1
        assert stats["articles_collected"] == 0

    def test_avg_response_time_weighted(self):
        fetcher = ContentFetcher()
        fetcher._update_stats("rss_successes", 0, 1.0, True)
        fetcher._update_stats("rss_successes", 0, 3.0, True)
        stats = fetcher.get_statistics()
        assert stats["avg_response_time"] == pytest.approx(2.0)

    def test_get_statistics_returns_copy(self):
        fetcher = ContentFetcher()
        fetcher._update_stats("rss_successes", 1, 1.0, True)
        snapshot = fetcher.get_statistics()
        snapshot["total_fetches"] = 999
        assert fetcher.get_statistics()["total_fetches"] == 1

    def test_reset_statistics_zeroes_all(self):
        fetcher = ContentFetcher()
        fetcher._update_stats("rss_successes", 10, 1.5, True)
        fetcher._update_stats("rss_successes", 5, 2.5, True)
        fetcher.reset_statistics()
        stats = fetcher.get_statistics()
        for value in stats.values():
            assert value == 0


# -- FetchResult.__str__ ------------------------------------------------------


class TestFetchResultStr:
    def _minimal_source(self) -> Source:
        return _make_source()

    def test_str_shows_success(self):
        result = FetchResult(source=self._minimal_source(), articles=[], method="rss")
        text = str(result)
        assert "SUCCESS" in text
        assert "rss" in text
        assert "0 articles" in text

    def test_str_shows_failed(self):
        result = FetchResult(source=self._minimal_source(), articles=[], method="error", success=False, error="boom")
        text = str(result)
        assert "FAILED" in text
        assert "error" in text
