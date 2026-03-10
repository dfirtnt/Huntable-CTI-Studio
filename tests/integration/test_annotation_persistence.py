"""Tests for annotation persistence (create/update/delete)."""

import uuid
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
        """Create a test article for annotations. Commits so test_database_manager_real can see it."""
        session = test_database_with_rollback
        uid = uuid.uuid4().hex[:8]

        source = SourceTable(
            identifier=f"test-source-annotation-{uid}",
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
            canonical_url=f"https://example.com/test-annotation-{uid}",
            title="Test Article for Annotations",
            published_at=datetime.now(),
            content="Test content for annotation testing.",
            content_hash=f"test-hash-annotation-{uid}",
            article_metadata={},
        )
        session.add(article)
        await session.commit()
        await session.refresh(article)

        yield article

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Async fixture teardown (rollback) runs in different event loop; needs pytest-asyncio/asyncpg fix"
    )
    async def test_create_annotation(self, test_article, test_database_manager_real):
        """Test creating an annotation."""
        annotation_data = AnnotationFactory.create(
            article_id=test_article.id,
            annotation_type="huntable",
            selected_text="x" * 1000,
            start_position=0,
            end_position=1000,
        )

        annotation = await test_database_manager_real.create_annotation(annotation_data)

        assert annotation is not None
        assert annotation.article_id == test_article.id
        assert annotation.annotation_type == "huntable"
        assert len(annotation.selected_text) == 1000

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Async fixture teardown (rollback) runs in different event loop; needs pytest-asyncio/asyncpg fix"
    )
    async def test_get_annotation(self, test_article, test_database_manager_real):
        """Test retrieving an annotation."""
        # Create annotation
        annotation_data = AnnotationFactory.create(article_id=test_article.id, annotation_type="huntable")
        created = await test_database_manager_real.create_annotation(annotation_data)
        assert created is not None

        # Retrieve annotation
        retrieved = await test_database_manager_real.get_annotation(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.article_id == test_article.id

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Async fixture teardown (rollback) runs in different event loop; needs pytest-asyncio/asyncpg fix"
    )
    async def test_get_article_annotations(self, test_article, test_database_manager_real):
        """Test retrieving all annotations for an article."""
        # Create multiple annotations
        for i in range(3):
            annotation_data = AnnotationFactory.create(
                article_id=test_article.id, annotation_type="huntable" if i % 2 == 0 else "not_huntable"
            )
            await test_database_manager_real.create_annotation(annotation_data)

        # Retrieve all annotations
        annotations = await test_database_manager_real.get_article_annotations(test_article.id)

        assert len(annotations) == 3
        assert all(ann.article_id == test_article.id for ann in annotations)
