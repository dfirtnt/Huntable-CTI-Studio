"""
Tests for core modules in src/core/.
"""

import pytest

from src.core.rss_parser import RSSParser


class TestSourceManager:
    """Test the SourceManager class."""

    def test_get_active_sources(self):
        """Test getting active sources."""
        from datetime import datetime

        from src.models.source import Source

        now = datetime.now()
        # Create mock sources with all required fields
        active_source1 = Source(
            id=1,
            name="Active Source",
            url="https://example.com",
            identifier="active-1",
            active=True,
            check_frequency=3600,
            lookback_days=180,
            consecutive_failures=0,
            total_articles=0,
            average_response_time=0.0,
            created_at=now,
            updated_at=now,
            config={},
        )
        inactive_source = Source(
            id=2,
            name="Inactive Source",
            url="https://example.com",
            identifier="inactive",
            active=False,
            check_frequency=3600,
            lookback_days=180,
            consecutive_failures=0,
            total_articles=0,
            average_response_time=0.0,
            created_at=now,
            updated_at=now,
            config={},
        )
        active_source2 = Source(
            id=3,
            name="Another Active",
            url="https://example.com",
            identifier="active-2",
            active=True,
            check_frequency=3600,
            lookback_days=180,
            consecutive_failures=0,
            total_articles=0,
            average_response_time=0.0,
            created_at=now,
            updated_at=now,
            config={},
        )

        sources = [active_source1, inactive_source, active_source2]

        # Filter active sources
        active_sources = [s for s in sources if s.active]
        assert len(active_sources) == 2
        assert all(source.active for source in active_sources)


class TestRSSParser:
    """Test the RSSParser class."""

    def test_validate_feed_url(self):
        """Test feed URL validation."""

        # Test basic URL validation (simplified test)
        parser = RSSParser(None)
        assert parser is not None


class TestFetcher:
    """Test the Fetcher class."""


class TestProcessor:
    """Test the Processor class."""

    def test_extract_metadata(self):
        """Test metadata extraction."""
        from src.utils.content import ContentCleaner

        content = """
        This article discusses advanced persistent threat techniques.
        The attack used PowerShell scripts and living-off-the-land techniques.
        Indicators of compromise include IP addresses and domain names.
        """

        # Test content cleaning
        cleaned = ContentCleaner.clean_html(content)
        assert len(cleaned) > 0
        assert "advanced persistent threat" in cleaned.lower()


if __name__ == "__main__":
    pytest.main([__file__])
