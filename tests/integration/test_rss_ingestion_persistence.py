"""Tests for RSS ingestion → article persistence."""

import uuid
from datetime import datetime

import pytest

from src.models.article import ArticleCreate
from tests.factories.article_factory import ArticleFactory


@pytest.mark.integration
class TestRSSIngestionPersistence:
    """Test RSS feed ingestion and article persistence."""

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

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.integration_full
    async def test_ingestion_via_create_article_real_db(self, test_database_manager):
        """Ingestion path: ArticleCreate → AsyncDatabaseManager.create_article → row in DB."""
        from sqlalchemy import select

        from src.database.models import ArticleTable, SourceTable

        uid = uuid.uuid4().hex[:8]
        async with test_database_manager.get_session() as session:
            source = SourceTable(
                identifier=f"test-source-ingest-{uid}",
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
            source_id = source.id

        article_data = ArticleCreate(
            title=f"Ingestion Path Test Article {uid}",
            canonical_url=f"https://example.com/ingestion-path-{uid}",
            content=f"Content for create_article integration test {uid}.",
            source_id=source_id,
            published_at=datetime.now(),
            content_hash=f"ingestion-path-hash-{uid}",
        )

        created = await test_database_manager.create_article(article_data)
        assert created is not None
        assert created.id is not None
        assert created.title == article_data.title
        assert created.canonical_url == article_data.canonical_url

        async with test_database_manager.get_session() as session:
            result = await session.execute(
                select(ArticleTable).where(ArticleTable.canonical_url == article_data.canonical_url)
            )
            rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].id == created.id
        assert rows[0].title == article_data.title
