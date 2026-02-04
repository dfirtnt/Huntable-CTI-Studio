"""Tests for scraper parsing and deduplication with fixtures.

These are unit tests using fixtures and mocks - no real infrastructure required.
"""

from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from src.core.rss_parser import RSSParser
from src.models.source import Source
from src.utils.http import HTTPClient


def create_test_source(**kwargs):
    """Helper to create test Source with all required fields."""
    now = datetime.now()
    defaults = {
        "check_frequency": 3600,
        "lookback_days": 180,
        "consecutive_failures": 0,
        "total_articles": 0,
        "average_response_time": 0.0,
        "created_at": now,
        "updated_at": now,
        "active": True,
        "config": {},
    }
    defaults.update(kwargs)
    return Source(**defaults)


# Mark all tests in this file as unit tests (use fixtures/mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestScraperParsing:
    """Test scraper parsing and deduplication using fixtures."""

    @pytest.fixture
    def rss_fixture_path(self):
        """Path to RSS feed fixture."""
        return Path("tests/fixtures/rss/sample_feed.xml")

    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client for testing."""
        client = AsyncMock(spec=HTTPClient)
        return client

    @pytest.fixture
    def sample_feed_content(self, rss_fixture_path):
        """Load RSS feed fixture content."""
        if not rss_fixture_path.exists():
            pytest.skip(f"Fixture not found: {rss_fixture_path}")

        with open(rss_fixture_path) as f:
            return f.read()

    @pytest.mark.asyncio
    async def test_rss_parsing_with_fixture(self, mock_http_client, sample_feed_content):
        """Test RSS parsing using fixture data."""
        # Mock HTTP response for RSS feed
        mock_response = Mock()
        mock_response.text = sample_feed_content
        mock_response.status_code = 200
        mock_response.raise_for_status = Mock()

        # Mock HTTP response for modern scraping (when RSS content is too short)
        mock_article_response = Mock()
        mock_article_response.text = (
            "<html><body><article><h1>Test Threat Intelligence Article</h1><p>"
            + "This is a comprehensive test article about threat intelligence. " * 50
            + "</p></article></body></html>"
        )
        mock_article_response.status_code = 200
        mock_article_response.raise_for_status = Mock()

        # Configure mock to return RSS feed for feed URL, article content for article URLs
        async def mock_get(url, **kwargs):
            if "feed.xml" in url:
                return mock_response
            return mock_article_response

        mock_http_client.get = AsyncMock(side_effect=mock_get)

        # Create parser
        parser = RSSParser(mock_http_client)

        # Create mock source with config to allow modern scraping
        source = create_test_source(
            id=1,
            identifier="test_source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            active=True,
            config={"rss_only": False},  # Allow modern scraping fallback
        )

        # Parse feed
        articles = await parser.parse_feed(source)

        # Assert articles were parsed
        assert len(articles) > 0
        assert articles[0].title == "Test Threat Intelligence Article"
        assert articles[0].canonical_url == "https://example.com/article1"

    @pytest.mark.skip(reason="Requires database for deduplication - implement with test containers")
    def test_deduplication_with_fixtures(self):
        """Test deduplication using fixture articles."""
        # TODO: Implement with test containers
        # Load article fixtures
        # Create articles
        # Test deduplication logic
        pass
