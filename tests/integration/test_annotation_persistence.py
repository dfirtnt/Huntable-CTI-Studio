"""Tests for annotation persistence (create/update/delete)."""

import pytest
import pytest_asyncio
from datetime import datetime
from tests.factories.annotation_factory import AnnotationFactory
from src.models.annotation import ArticleAnnotationCreate
from src.database.models import ArticleTable


@pytest.mark.integration
class TestAnnotationPersistence:
    """Test annotation CRUD operations with database."""
    
    @pytest_asyncio.fixture
    async def test_article(self, test_database_with_rollback):
        """Create a test article for annotations."""
        from src.database.models import ArticleTable
        
        # Create test article
        article = ArticleTable(
            source_id=1,
            canonical_url="https://example.com/test-annotation",
            title="Test Article for Annotations",
            published_at=datetime.now(),
            content="Test content for annotation testing.",
            content_hash="test-hash-annotation",
            article_metadata={}
        )
        
        test_database_with_rollback.add(article)
        await test_database_with_rollback.commit()
        await test_database_with_rollback.refresh(article)
        
        yield article
        
        # Cleanup (rollback will handle it, but explicit delete for clarity)
        await test_database_with_rollback.delete(article)
        await test_database_with_rollback.commit()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers and async_db_manager - implement after infrastructure setup")
    async def test_create_annotation(self, test_article):
        """Test creating an annotation."""
        from src.database.async_manager import async_db_manager
        
        annotation_data = AnnotationFactory.create(
            article_id=test_article.id,
            annotation_type="huntable",
            selected_text="x" * 1000,
            start_position=0,
            end_position=1000
        )
        
        annotation = await async_db_manager.create_annotation(annotation_data)
        
        assert annotation is not None
        assert annotation.article_id == test_article.id
        assert annotation.annotation_type == "huntable"
        assert len(annotation.selected_text) == 1000
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers - implement after infrastructure setup")
    async def test_get_annotation(self, test_article):
        """Test retrieving an annotation."""
        from src.database.async_manager import async_db_manager
        
        # Create annotation
        annotation_data = AnnotationFactory.create(
            article_id=test_article.id,
            annotation_type="huntable"
        )
        created = await async_db_manager.create_annotation(annotation_data)
        assert created is not None
        
        # Retrieve annotation
        retrieved = await async_db_manager.get_annotation(created.id)
        
        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.article_id == test_article.id
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.skip(reason="Requires test containers - implement after infrastructure setup")
    async def test_get_article_annotations(self, test_article):
        """Test retrieving all annotations for an article."""
        from src.database.async_manager import async_db_manager
        
        # Create multiple annotations
        for i in range(3):
            annotation_data = AnnotationFactory.create(
                article_id=test_article.id,
                annotation_type="huntable" if i % 2 == 0 else "not_huntable"
            )
            await async_db_manager.create_annotation(annotation_data)
        
        # Retrieve all annotations
        annotations = await async_db_manager.get_article_annotations(test_article.id)
        
        assert len(annotations) == 3
        assert all(ann.article_id == test_article.id for ann in annotations)
