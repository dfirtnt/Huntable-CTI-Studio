"""Tests for content filter functionality."""

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from src.utils.content_filter import ContentFilter, FilterConfig, FilterResult


class TestContentFilter:
    """Test ContentFilter functionality."""

    @pytest.fixture
    def filter_config(self):
        """Create filter configuration for testing."""
        return FilterConfig(
            min_content_length=100,
            max_content_length=50000,
            min_title_length=10,
            max_title_length=200,
            max_age_days=365,
            quality_threshold=0.5,
            cost_threshold=0.1,
            enable_ml_filtering=True,
            enable_cost_optimization=True,
        )

    @pytest.fixture
    def content_filter(self, filter_config):
        """Create ContentFilter instance for testing."""
        return ContentFilter(config=filter_config)

    @pytest.fixture
    def sample_article(self):
        """Create sample article for testing."""
        return {
            "title": "Advanced Threat Hunting Techniques for Windows Malware",
            "content": "This article discusses advanced threat hunting techniques for detecting Windows malware. It covers various methods including process monitoring, registry analysis, and network traffic analysis. The techniques described are based on real-world incident response scenarios and provide practical guidance for security professionals.",
            "published_at": datetime.now() - timedelta(days=30),
            "authors": ["Security Expert"],
            "tags": ["threat-hunting", "malware", "windows"],
            "url": "https://example.com/threat-hunting-guide",
            "source": "Security Blog",
        }

    def test_init_default_config(self):
        """Test ContentFilter initialization with default config."""
        filter_instance = ContentFilter()

        assert filter_instance.config is not None
        assert filter_instance.config.min_content_length > 0
        assert filter_instance.config.max_content_length > 0
        assert filter_instance.config.quality_threshold > 0

    def test_init_custom_config(self, filter_config):
        """Test ContentFilter initialization with custom config."""
        filter_instance = ContentFilter(config=filter_config)

        assert filter_instance.config == filter_config
        assert filter_instance.config.min_content_length == 100
        assert filter_instance.config.max_content_length == 50000

    def test_filter_article_success(self, content_filter, sample_article):
        """Test successful article filtering."""
        result = content_filter.filter_article(sample_article)

        assert isinstance(result, FilterResult)
        assert result.passed is True
        assert result.reason == "Article passed all filters"
        assert result.score >= 0.0
        assert result.cost_estimate >= 0.0

    def test_filter_article_too_short_content(self, content_filter):
        """Test filtering article with too short content."""
        article = {
            "title": "Short Article",
            "content": "Too short",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/short",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)

        assert result.passed is False
        assert "content too short" in result.reason.lower()

    def test_filter_article_too_long_content(self, content_filter):
        """Test filtering article with too long content."""
        article = {
            "title": "Very Long Article",
            "content": "x" * 60000,  # Exceeds max length
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/long",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)

        assert result.passed is False
        assert "content too long" in result.reason.lower()

    def test_filter_article_too_short_title(self, content_filter):
        """Test filtering article with too short title."""
        article = {
            "title": "Short",
            "content": "This is a valid article with sufficient content length for testing purposes.",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/short-title",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)

        assert result.passed is False
        assert "title too short" in result.reason.lower()

    def test_filter_article_too_long_title(self, content_filter):
        """Test filtering article with too long title."""
        article = {
            "title": "x" * 250,  # Exceeds max title length
            "content": "This is a valid article with sufficient content length for testing purposes.",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/long-title",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)

        assert result.passed is False
        assert "title too long" in result.reason.lower()

    def test_filter_article_too_old(self, content_filter):
        """Test filtering article that is too old."""
        article = {
            "title": "Old Article Title",
            "content": "This is a valid article with sufficient content length for testing purposes. It contains enough text to meet the minimum content length requirements and should pass the content length check.",
            "published_at": datetime.now() - timedelta(days=400),  # Too old
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/old",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)

        assert result.passed is False
        assert "too old" in result.reason.lower()

    def test_filter_article_missing_required_fields(self, content_filter):
        """Test filtering article with missing required fields."""
        article = {
            "title": "Incomplete Article",
            # Missing content
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/incomplete",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)

        assert result.passed is False
        assert "missing required fields" in result.reason.lower()

    def test_calculate_quality_score_high_quality(self, content_filter, sample_article):
        """Test quality score calculation for high-quality content."""
        score = content_filter.calculate_quality_score(sample_article)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score > 0.5  # Should be high quality

    def test_calculate_quality_score_low_quality(self, content_filter):
        """Test quality score calculation for low-quality content."""
        article = {
            "title": "Low Quality Article",
            "content": "This is a low quality article with minimal content and no valuable information.",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/low-quality",
            "source": "Test Source",
        }

        score = content_filter.calculate_quality_score(article)

        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        assert score < 0.5  # Should be low quality

    def test_calculate_cost_estimate(self, content_filter, sample_article):
        """Test cost estimation for article processing."""
        cost = content_filter.calculate_cost_estimate(sample_article)

        assert isinstance(cost, float)
        assert cost >= 0.0
        assert cost <= 1.0  # Normalized cost

    def test_calculate_cost_estimate_long_content(self, content_filter):
        """Test cost estimation for long content."""
        article = {
            "title": "Long Article",
            "content": "x" * 10000,  # Long content
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/long",
            "source": "Test Source",
        }

        cost = content_filter.calculate_cost_estimate(article)

        assert isinstance(cost, float)
        assert cost >= 0.0
        assert cost > 0.1  # Should be higher cost

    @pytest.mark.asyncio
    async def test_filter_articles_batch(self, content_filter):
        """Test filtering multiple articles in batch."""
        articles = [
            {
                "title": "Valid Article Title",
                "content": "This is a valid article with sufficient content length for testing purposes. It contains enough text to meet the minimum content length requirements and should pass the content length check. This article discusses advanced threat hunting techniques for detecting Windows malware and security vulnerabilities.",
                "published_at": datetime.now(),
                "authors": ["Author"],
                "tags": ["test"],
                "url": "https://example.com/article1",
                "source": "Test Source",
            },
            {
                "title": "Article 2",
                "content": "Too short",
                "published_at": datetime.now(),
                "authors": ["Author"],
                "tags": ["test"],
                "url": "https://example.com/article2",
                "source": "Test Source",
            },
        ]

        results = await content_filter.filter_articles_batch(articles)

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False

    def test_get_filter_statistics(self, content_filter):
        """Test getting filter statistics."""
        # Process some articles to generate statistics
        articles = [
            {
                "title": "Article 1",
                "content": "This is a valid article with sufficient content length for testing purposes.",
                "published_at": datetime.now(),
                "authors": ["Author"],
                "tags": ["test"],
                "url": "https://example.com/article1",
                "source": "Test Source",
            },
            {
                "title": "Short",
                "content": "Too short",
                "published_at": datetime.now(),
                "authors": ["Author"],
                "tags": ["test"],
                "url": "https://example.com/article2",
                "source": "Test Source",
            },
        ]

        for article in articles:
            content_filter.filter_article(article)

        stats = content_filter.get_statistics()

        assert "total_processed" in stats
        assert "passed_count" in stats
        assert "failed_count" in stats
        assert "pass_rate" in stats
        assert "average_quality_score" in stats
        assert "average_cost_estimate" in stats

    def test_reset_statistics(self, content_filter):
        """Test resetting filter statistics."""
        # Process an article to generate statistics
        article = {
            "title": "Test Article",
            "content": "This is a valid article with sufficient content length for testing purposes.",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/test",
            "source": "Test Source",
        }

        content_filter.filter_article(article)
        stats_before = content_filter.get_statistics()

        content_filter.reset_statistics()
        stats_after = content_filter.get_statistics()

        assert stats_before["total_processed"] > 0
        assert stats_after["total_processed"] == 0

    def test_update_config(self, content_filter):
        """Test updating filter configuration."""
        new_config = FilterConfig(
            min_content_length=200,
            max_content_length=40000,
            min_title_length=15,
            max_title_length=150,
            max_age_days=180,
            quality_threshold=0.6,
            cost_threshold=0.05,
            enable_ml_filtering=True,
            enable_cost_optimization=True,
        )

        content_filter.update_config(new_config)

        assert content_filter.config == new_config
        assert content_filter.config.min_content_length == 200
        assert content_filter.config.quality_threshold == 0.6

    def test_filter_article_with_ml_prediction(self, content_filter, sample_article):
        """Test filtering with ML prediction enabled."""
        with patch.object(content_filter, "get_ml_prediction") as mock_ml:
            mock_ml.return_value = {"quality_score": 0.8, "cost_estimate": 0.05}

            result = content_filter.filter_article(sample_article)

            assert result.passed is True
            assert result.score == 0.8
            assert result.cost_estimate == 0.05
            mock_ml.assert_called_once_with(sample_article)

    def test_filter_article_cost_optimization(self, content_filter):
        """Test cost optimization filtering."""
        expensive_article = {
            "title": "Expensive Article",
            "content": "x" * 20000,  # Very long content
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/expensive",
            "source": "Test Source",
        }

        result = content_filter.filter_article(expensive_article)

        # Should fail due to high cost
        assert result.passed is False
        assert "cost too high" in result.reason.lower()

    def test_filter_article_quality_threshold(self, content_filter):
        """Test quality threshold filtering."""
        low_quality_article = {
            "title": "Low Quality Article",
            "content": "This is a low quality article with minimal content and no valuable information. It has enough text to pass the content length check but lacks technical depth and quality indicators.",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/low-quality",
            "source": "Test Source",
        }

        result = content_filter.filter_article(low_quality_article)

        # Should fail due to low quality
        assert result.passed is False
        assert "quality too low" in result.reason.lower()

    def test_filter_article_edge_cases(self, content_filter):
        """Test filtering edge cases."""
        # Empty content
        article = {
            "title": "Empty Content",
            "content": "",
            "published_at": datetime.now(),
            "authors": ["Author"],
            "tags": ["test"],
            "url": "https://example.com/empty",
            "source": "Test Source",
        }

        result = content_filter.filter_article(article)
        assert result.passed is False

        # None content
        article["content"] = None
        result = content_filter.filter_article(article)
        assert result.passed is False

        # Very old article
        article["content"] = "Valid content"
        article["published_at"] = datetime.now() - timedelta(days=1000)
        result = content_filter.filter_article(article)
        assert result.passed is False

    def test_filter_result_creation(self):
        """Test FilterResult creation and properties."""
        result = FilterResult(
            passed=True, reason="Test passed", score=0.8, cost_estimate=0.2, metadata={"test": "value"}
        )

        assert result.passed is True
        assert result.reason == "Test passed"
        assert result.score == 0.8
        assert result.cost_estimate == 0.2
        assert result.metadata == {"test": "value"}

    def test_filter_config_validation(self):
        """Test FilterConfig validation."""
        # Valid config
        config = FilterConfig(
            min_content_length=100,
            max_content_length=50000,
            min_title_length=10,
            max_title_length=200,
            max_age_days=365,
            quality_threshold=0.5,
            cost_threshold=0.1,
            enable_ml_filtering=True,
            enable_cost_optimization=True,
        )

        assert config.min_content_length > 0
        assert config.max_content_length > config.min_content_length
        assert config.quality_threshold > 0
        assert config.cost_threshold > 0

    def test_content_filter_performance(self, content_filter, sample_article):
        """Test content filter performance."""
        import time

        start_time = time.time()

        # Process multiple articles
        for _ in range(100):
            content_filter.filter_article(sample_article)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should process 100 articles in reasonable time
        assert processing_time < 1.0  # Less than 1 second
        assert processing_time > 0.0
