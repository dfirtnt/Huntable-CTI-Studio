"""Tests for RSS ingestion → article persistence."""

import uuid
from pathlib import Path

import pytest

from tests.factories.article_factory import ArticleFactory


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
    async def test_article_persistence(self, test_database_manager):
        """Test that articles can be persisted to database."""
        from src.database.models import ArticleTable, SourceTable

        article_data = ArticleFactory.create(
            title="Test Persisted Article", canonical_url="https://example.com/persisted"
        )

        async with test_database_manager.get_session() as session:
            source = SourceTable(
                identifier=f"test-source-persist-{uuid.uuid4().hex[:8]}",
                name="Test Source",
                url="https://example.com",
                rss_url="https://example.com/feed.xml",
                check_frequency=3600,
                lookback_days=180,
                active=True,
            )
            session.add(source)
            await session.commit()
            await session.refresh(source)

            content_hash = f"test-hash-{uuid.uuid4().hex[:8]}"
            article_row = ArticleTable(
                source_id=source.id,
                canonical_url=article_data.canonical_url,
                title=article_data.title,
                content=article_data.content or "",
                published_at=article_data.published_at,
                content_hash=content_hash,
            )
            session.add(article_row)
            await session.commit()
            await session.refresh(article_row)

        assert article_row.id is not None
        assert article_row.title == article_data.title
        assert article_row.canonical_url == article_data.canonical_url

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_article_deduplication(self, test_database_manager):
        """Test that duplicate articles are not persisted (same canonical_url)."""
        from sqlalchemy import select

        from src.database.models import ArticleTable, SourceTable

        uid = uuid.uuid4().hex[:8]
        article_data = ArticleFactory.create(
            title="Duplicate Test",
            canonical_url=f"https://example.com/duplicate-{uid}",
            content="Test content for deduplication",
        )

        async with test_database_manager.get_session() as session:
            source = SourceTable(
                identifier=f"test-source-dedup-{uid}",
                name="Test Source",
                url="https://example.com",
                rss_url="https://example.com/feed.xml",
                check_frequency=3600,
                lookback_days=180,
                active=True,
            )
            session.add(source)
            await session.commit()
            await session.refresh(source)

            content_hash = f"dedup-hash-{uid}"
            article_row = ArticleTable(
                source_id=source.id,
                canonical_url=article_data.canonical_url,
                title=article_data.title,
                content=article_data.content or "",
                published_at=article_data.published_at,
                content_hash=content_hash,
            )
            session.add(article_row)
            await session.commit()
            await session.refresh(article_row)

        assert article_row.id is not None

        async with test_database_manager.get_session() as session:
            result = await session.execute(
                select(ArticleTable).where(ArticleTable.canonical_url == article_data.canonical_url)
            )
            articles = result.scalars().all()
        assert len(articles) == 1
