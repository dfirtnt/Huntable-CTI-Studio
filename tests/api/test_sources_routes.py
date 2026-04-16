"""Tests for source management API routes.

Covers endpoints that lacked test coverage:
- GET  /api/sources          (api_sources_list)
- GET  /api/sources/failing  (api_sources_failing)
- GET  /api/sources/{id}     (api_get_source)
- POST /api/sources/{id}/toggle (api_toggle_source_status)
- POST /api/sources/{id}/collect (api_collect_from_source)
- PUT  /api/sources/{id}/min_content_length (api_update_source_min_content_length)
- PUT  /api/sources/{id}/check_frequency (api_update_source_check_frequency)
- GET  /api/sources/{id}/stats (api_source_stats)
Also covers the _get_collection_method helper.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.web.routes.sources import (
    _get_collection_method,
    api_collect_from_source,
    api_get_source,
    api_source_stats,
    api_sources_failing,
    api_sources_list,
    api_toggle_source_status,
    api_update_source_check_frequency,
    api_update_source_min_content_length,
)

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_source(**overrides):
    """Build a source-like mock with sensible defaults."""
    now = datetime.now(UTC)
    source = MagicMock()
    source.id = overrides.get("id", 1)
    source.identifier = overrides.get("identifier", "test_blog")
    source.name = overrides.get("name", "Test Blog")
    source.url = overrides.get("url", "https://test.example.com")
    source.rss_url = overrides.get("rss_url", "https://test.example.com/feed/")
    source.config = overrides.get("config", {})
    source.active = overrides.get("active", True)
    source.tier = overrides.get("tier", 1)
    source.consecutive_failures = overrides.get("consecutive_failures", 0)
    source.last_success = overrides.get("last_success", now)
    source.last_check = overrides.get("last_check", now)
    source.healing_exhausted = overrides.get("healing_exhausted", False)
    source.dict = Mock(return_value={"id": source.id, "name": source.name})
    return source


def _mock_article(**overrides):
    """Build an article-like mock."""
    art = MagicMock()
    art.id = overrides.get("id", 1)
    art.content = overrides.get("content", "x" * 2000)
    art.published_at = overrides.get("published_at", datetime(2026, 4, 15, tzinfo=UTC))
    art.article_metadata = overrides.get("article_metadata", {"threat_hunting_score": 75})
    return art


# ---------------------------------------------------------------------------
# _get_collection_method
# ---------------------------------------------------------------------------


class TestGetCollectionMethod:
    """Tests for the _get_collection_method helper."""

    def test_playwright_detected(self):
        source = _mock_source(config={"use_playwright": True})
        assert _get_collection_method(source) == "Playwright Scraping"

    def test_nested_config_playwright(self):
        source = _mock_source(config={"config": {"use_playwright": True}})
        assert _get_collection_method(source) == "Playwright Scraping"

    def test_rss_detected(self):
        source = _mock_source(config={}, rss_url="https://example.com/feed/")
        assert _get_collection_method(source) == "RSS Feed"

    def test_default_web_scraping(self):
        source = _mock_source(config={}, rss_url="")
        assert _get_collection_method(source) == "Web Scraping"

    def test_empty_rss_url_falls_to_web_scraping(self):
        source = _mock_source(config={}, rss_url="   ")
        assert _get_collection_method(source) == "Web Scraping"

    def test_none_config_defaults_to_web_scraping(self):
        source = _mock_source(config=None, rss_url="")
        source.config = None
        assert _get_collection_method(source) == "Web Scraping"


# ---------------------------------------------------------------------------
# GET /api/sources
# ---------------------------------------------------------------------------


class TestApiSourcesList:
    """Tests for api_sources_list."""

    @pytest.mark.asyncio
    async def test_returns_sources_list(self):
        sources = [_mock_source(id=1), _mock_source(id=2)]

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(return_value=sources)
            filter_params = MagicMock()
            result = await api_sources_list(filter_params)

        assert "sources" in result
        assert len(result["sources"]) == 2

    @pytest.mark.asyncio
    async def test_returns_500_on_db_error(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(side_effect=Exception("DB connection lost"))
            filter_params = MagicMock()
            with pytest.raises(HTTPException) as exc_info:
                await api_sources_list(filter_params)
            assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# GET /api/sources/failing
# ---------------------------------------------------------------------------


class TestApiSourcesFailing:
    """Tests for api_sources_failing."""

    @pytest.mark.asyncio
    async def test_returns_failing_sources_sorted(self):
        s1 = _mock_source(id=1, consecutive_failures=3, name="Blog A", last_success=None)
        s2 = _mock_source(id=2, consecutive_failures=7, name="Blog B")
        s3 = _mock_source(id=3, consecutive_failures=0, name="Blog C")

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(return_value=[s1, s2, s3])
            result = await api_sources_failing()

        # Only s1 and s2 have failures; s2 (7) should come first
        assert len(result) == 2
        assert result[0]["source_name"] == "Blog B"
        assert result[0]["consecutive_failures"] == 7
        assert result[1]["source_name"] == "Blog A"

    @pytest.mark.asyncio
    async def test_skips_manual_source(self):
        manual = _mock_source(identifier="manual", consecutive_failures=5)

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(return_value=[manual])
            result = await api_sources_failing()

        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_limits_to_10(self):
        sources = [_mock_source(id=i, consecutive_failures=i, name=f"Blog {i}") for i in range(1, 15)]

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(return_value=sources)
            result = await api_sources_failing()

        assert len(result) <= 10

    @pytest.mark.asyncio
    async def test_returns_empty_on_error(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(side_effect=Exception("DB error"))
            result = await api_sources_failing()

        assert result == []

    @pytest.mark.asyncio
    async def test_last_success_never(self):
        s = _mock_source(consecutive_failures=2, last_success=None)
        s.last_success = None

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.list_sources = AsyncMock(return_value=[s])
            result = await api_sources_failing()

        assert result[0]["last_success"] == "Never"


# ---------------------------------------------------------------------------
# GET /api/sources/{id}
# ---------------------------------------------------------------------------


class TestApiGetSource:
    """Tests for api_get_source."""

    @pytest.mark.asyncio
    async def test_returns_source(self):
        source = _mock_source(id=42)

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=source)
            result = await api_get_source(42)

        assert result["id"] == 42

    @pytest.mark.asyncio
    async def test_404_when_not_found(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_get_source(999)
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/sources/{id}/toggle
# ---------------------------------------------------------------------------


class TestApiToggleSourceStatus:
    """Tests for api_toggle_source_status."""

    @pytest.mark.asyncio
    async def test_toggle_returns_new_status(self):
        toggle_result = {
            "source_id": 1,
            "source_name": "Test Blog",
            "old_status": True,
            "new_status": False,
        }

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.toggle_source_status = AsyncMock(return_value=toggle_result)
            result = await api_toggle_source_status(1)

        assert result["success"] is True
        assert result["old_status"] is True
        assert result["new_status"] is False
        assert "Inactive" in result["message"]

    @pytest.mark.asyncio
    async def test_toggle_404_when_not_found(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.toggle_source_status = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_toggle_source_status(999)
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/sources/{id}/collect
# ---------------------------------------------------------------------------


class TestApiCollectFromSource:
    """Tests for api_collect_from_source."""

    @pytest.mark.asyncio
    async def test_collect_dispatches_celery_task(self):
        with patch("src.web.routes.sources.Celery") as mock_celery_cls:
            mock_app = MagicMock()
            mock_task = MagicMock()
            mock_task.id = "task-abc-123"
            mock_app.send_task.return_value = mock_task
            mock_celery_cls.return_value = mock_app

            result = await api_collect_from_source(42)

        assert result["success"] is True
        assert result["task_id"] == "task-abc-123"
        mock_app.send_task.assert_called_once_with(
            "src.worker.celery_app.collect_from_source",
            args=[42],
            queue="collection_immediate",
        )


# ---------------------------------------------------------------------------
# PUT /api/sources/{id}/min_content_length
# ---------------------------------------------------------------------------


class TestApiUpdateMinContentLength:
    """Tests for api_update_source_min_content_length."""

    @pytest.mark.asyncio
    async def test_valid_update(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.update_source_min_content_length = AsyncMock(
                return_value={"success": True, "min_content_length": 500}
            )
            result = await api_update_source_min_content_length(1, {"min_content_length": 500})

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_missing_field_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await api_update_source_min_content_length(1, {})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_negative_value_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await api_update_source_min_content_length(1, {"min_content_length": -1})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_string_value_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await api_update_source_min_content_length(1, {"min_content_length": "abc"})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_source_not_found_returns_404(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.update_source_min_content_length = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_update_source_min_content_length(1, {"min_content_length": 500})
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# PUT /api/sources/{id}/check_frequency
# ---------------------------------------------------------------------------


class TestApiUpdateCheckFrequency:
    """Tests for api_update_source_check_frequency."""

    @pytest.mark.asyncio
    async def test_valid_update(self):
        source = _mock_source(id=1)

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=source)
            mock_db.get_session = MagicMock()
            # Mock the async context manager for get_session
            mock_session = AsyncMock()
            mock_result = MagicMock()
            mock_result.rowcount = 1
            mock_session.execute = AsyncMock(return_value=mock_result)
            mock_session.commit = AsyncMock()

            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_session)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_db.get_session.return_value = mock_ctx

            result = await api_update_source_check_frequency(1, {"check_frequency": 3600})

        assert result["success"] is True
        assert result["check_frequency"] == 3600

    @pytest.mark.asyncio
    async def test_missing_field_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await api_update_source_check_frequency(1, {})
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    async def test_below_minimum_returns_400(self):
        with pytest.raises(HTTPException) as exc_info:
            await api_update_source_check_frequency(1, {"check_frequency": 30})
        assert exc_info.value.status_code == 400
        assert "at least 60" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_source_not_found_returns_404(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_update_source_check_frequency(1, {"check_frequency": 3600})
            assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/sources/{id}/stats
# ---------------------------------------------------------------------------


class TestApiSourceStats:
    """Tests for api_source_stats."""

    @pytest.mark.asyncio
    async def test_stats_returns_aggregates(self):
        source = _mock_source(id=1, name="Test Blog")
        articles = [
            _mock_article(id=1, content="x" * 1000, article_metadata={"threat_hunting_score": 80}),
            _mock_article(id=2, content="x" * 3000, article_metadata={"threat_hunting_score": 60}),
        ]

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=source)
            mock_db.list_articles_by_source = AsyncMock(return_value=articles)
            result = await api_source_stats(1)

        assert result["source_id"] == 1
        assert result["total_articles"] == 2
        assert result["avg_content_length"] == 2000.0  # (1000 + 3000) / 2
        assert result["avg_threat_hunting_score"] == 70.0  # (80 + 60) / 2
        assert "articles_by_date" in result
        assert result["collection_method"] in ["RSS Feed", "Web Scraping", "Playwright Scraping"]

    @pytest.mark.asyncio
    async def test_stats_no_articles(self):
        source = _mock_source(id=1)

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=source)
            mock_db.list_articles_by_source = AsyncMock(return_value=[])
            result = await api_source_stats(1)

        assert result["total_articles"] == 0
        assert result["avg_content_length"] == 0.0
        assert result["avg_threat_hunting_score"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_404_when_source_not_found(self):
        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=None)
            with pytest.raises(HTTPException) as exc_info:
                await api_source_stats(999)
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_stats_articles_with_zero_hunt_score_excluded_from_avg(self):
        """Articles with threat_hunting_score=0 are excluded from the average."""
        source = _mock_source(id=1)
        articles = [
            _mock_article(article_metadata={"threat_hunting_score": 80}),
            _mock_article(article_metadata={"threat_hunting_score": 0}),
            _mock_article(article_metadata={}),
        ]

        with patch("src.web.routes.sources.async_db_manager") as mock_db:
            mock_db.get_source = AsyncMock(return_value=source)
            mock_db.list_articles_by_source = AsyncMock(return_value=articles)
            result = await api_source_stats(1)

        # Only the article with score=80 is included
        assert result["avg_threat_hunting_score"] == 80.0
