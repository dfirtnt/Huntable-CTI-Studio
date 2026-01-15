"""Tests for RSS ingestion → article persistence."""

import pytest
import pytest_asyncio
from datetime import datetime
from tests.factories.article_factory import ArticleFactory
from pathlib import Path


@pytest.mark.integration
class TestRSSIngestionPersistence:
    """Test RSS feed ingestion and article persistence."""
    
    @pytest.fixture
    def rss_fixture_path(self):
        """Path to RSS feed fixture."""
        return Path("tests/fixtures/rss/sample_feed.xml")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers and RSS parser fixes - implement after Phase 0")
    async def test_rss_ingestion_creates_articles(self, test_database_session, rss_fixture_path):
        """Test that RSS ingestion creates articles in database."""
        # TODO: Implement after RSS parser tests are fixed
        # 1. Load RSS fixture
        # 2. Parse feed
        # 3. Create articles in database
        # 4. Assert articles are persisted
        pass
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers - implement after infrastructure setup")
    async def test_article_persistence(self):
        """Test that articles can be persisted to database."""
        from src.database.async_manager import async_db_manager
        
        # Create article using factory
        article_data = ArticleFactory.create(
            title="Test Persisted Article",
            canonical_url="https://example.com/persisted"
        )
        
        # Persist to database
        article = await async_db_manager.create_article(article_data)
        
        assert article is not None
        assert article.id is not None
        assert article.title == article_data.title
        assert article.canonical_url == article_data.canonical_url
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers - implement after infrastructure setup")
    async def test_article_deduplication(self):
        """Test that duplicate articles are not persisted."""
        from src.database.async_manager import async_db_manager
        
        # Create article with specific content hash
        article_data = ArticleFactory.create(
            title="Duplicate Test",
            canonical_url="https://example.com/duplicate",
            content="Test content for deduplication"
        )
        
        # Persist first article
        article1 = await async_db_manager.create_article(article_data)
        assert article1 is not None
        
        # Try to persist duplicate (same content hash)
        # Should either fail or return existing article
        # TODO: Implement deduplication check when service is available
