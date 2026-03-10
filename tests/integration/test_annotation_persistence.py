"""Tests for annotation persistence (create/update/delete)."""

from datetime import datetime

import pytest
import pytest_asyncio

from src.database.models import ArticleTable, SourceTable
from tests.factories.annotation_factory import AnnotationFactory


@pytest.mark.integration
class TestAnnotationPersistence:
    """Test annotation CRUD operations with database."""

    @pytest_asyncio.fixture
    async def test_article(self, test_database_with_rollback):
        """Create a test article for annotations."""
        session = test_database_with_rollback

        source = SourceTable(
            identifier="test-source-annotation",
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

        article = ArticleTable(
            source_id=source.id,
            canonical_url="https://example.com/test-annotation",
            title="Test Article for Annotations",
            published_at=datetime.now(),
            content="Test content for annotation testing.",
            content_hash="test-hash-annotation",
            article_metadata={},
        )
        session.add(article)
        await session.commit()
        await session.refresh(article)

        yield article

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="async_db_manager event loop conflict with pytest-asyncio")
    async def test_create_annotation(self, test_article):
        """Test creating an annotation."""
        from src.database.async_manager import async_db_manager

        annotation_data = AnnotationFactory.create(
            article_id=test_article.id,
            annotation_type="huntable",
            selected_text="x" * 1000,
            start_position=0,
            end_position=1000,
        )

        annotation = await async_db_manager.create_annotation(annotation_data)

        assert annotation is not None
        assert annotation.article_id == test_article.id
        assert annotation.annotation_type == "huntable"
        assert len(annotation.selected_text) == 1000

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="async_db_manager event loop conflict with pytest-asyncio")
    async def test_get_annotation(self, test_article):
        """Test retrieving an annotation."""
        from src.database.async_manager import async_db_manager

        # Create annotation
        annotation_data = AnnotationFactory.create(article_id=test_article.id, annotation_type="huntable")
        created = await async_db_manager.create_annotation(annotation_data)
        assert created is not None

        # Retrieve annotation
        retrieved = await async_db_manager.get_annotation(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.article_id == test_article.id

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="async_db_manager event loop conflict with pytest-asyncio")
    async def test_get_article_annotations(self, test_article):
        """Test retrieving all annotations for an article."""
        from src.database.async_manager import async_db_manager

        # Create multiple annotations
        for i in range(3):
            annotation_data = AnnotationFactory.create(
                article_id=test_article.id, annotation_type="huntable" if i % 2 == 0 else "not_huntable"
            )
            await async_db_manager.create_annotation(annotation_data)

        # Retrieve all annotations
        annotations = await async_db_manager.get_article_annotations(test_article.id)

        assert len(annotations) == 3
        assert all(ann.article_id == test_article.id for ann in annotations)
