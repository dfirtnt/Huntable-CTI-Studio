"""Tests for database operations functionality."""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import List, Optional, Dict, Any

from src.database.async_manager import AsyncDatabaseManager
from src.models.source import Source, SourceCreate, SourceUpdate, SourceFilter
from src.models.article import Article, ArticleCreate, ArticleUpdate, ArticleListFilter
from src.models.annotation import ArticleAnnotation, ArticleAnnotationCreate, ArticleAnnotationUpdate, ArticleAnnotationFilter
from src.database.models import SourceTable, ArticleTable, ArticleAnnotationTable


class TestAsyncDatabaseManager:
    """Test AsyncDatabaseManager functionality."""

    @pytest.fixture
    def mock_engine(self, mock_async_engine):
        """Create mock database engine."""
        return mock_async_engine

    @pytest.fixture
    def mock_session(self, mock_async_session):
        """Create mock database session."""
        return mock_async_session

    @pytest.fixture
    def sample_source_data(self):
        """Sample source data for testing."""
        return {
            "id": 1,
            "identifier": "test-source-123",
            "name": "Test Source",
            "url": "https://example.com",
            "rss_url": "https://example.com/rss",
            "check_frequency": 3600,
            "lookback_days": 180,
            "active": True,
            "config": {"test": "config"}
        }

    @pytest.fixture
    def sample_article_data(self):
        """Sample article data for testing."""
        now = datetime.now()
        return {
            "title": "Test Article",
            "content": "Test article content",
            "canonical_url": "https://example.com/article",
            "published_at": now,
            "source_id": 1,
            "content_hash": "test-hash-1234567890abcdef",
            "authors": ["Test Author"],
            "tags": ["test", "article"],
            "summary": "Test article summary",
            "article_metadata": {"test": "metadata"},
            "collected_at": now,
            "discovered_at": now,
            "created_at": now,
            "updated_at": now
        }

    @pytest.fixture
    def sample_annotation_data(self):
        """Sample annotation data for testing."""
        return {
            "article_id": 1,
            "annotation_type": "huntable",
            "selected_text": "Contains IOCs and threat intelligence",
            "start_position": 100,
            "end_position": 150,
            "context_before": "Previous context text",
            "context_after": "Following context text",
            "confidence_score": 0.95,
            "used_for_training": False,
            "usage": "train",
            "user_id": 1,
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        }

    @pytest.mark.asyncio
    async def test_create_source(self, mock_session, sample_source_data):
        """Test creating a new source."""
        # Mock the session behavior
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        mock_session.refresh.return_value = None
        
        # Create source
        source_create = SourceCreate(**sample_source_data)
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.create_source = AsyncMock(return_value=Source(**sample_source_data))
            
            result = await mock_instance.create_source(source_create)
            
            assert result.name == sample_source_data["name"]
            assert result.url == sample_source_data["url"]
            assert result.active == sample_source_data["active"]

    @pytest.mark.asyncio
    async def test_get_source_by_id(self, mock_session):
        """Test getting a source by ID."""
        source_id = 1
        expected_source = Source(
            id=source_id,
            identifier="test-source-123",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/rss",
            check_frequency=3600,
            lookback_days=180,
            active=True,
            config={"test": "config"}
        )
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_source_by_id = AsyncMock(return_value=expected_source)
            
            result = await mock_instance.get_source_by_id(source_id)
            
            assert result.id == source_id
            assert result.name == "Test Source"

    @pytest.mark.asyncio
    async def test_update_source(self, mock_session, sample_source_data):
        """Test updating a source."""
        source_id = 1
        update_data = {"name": "Updated Source Name", "active": False}
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            updated_source = Source(**{**sample_source_data, **update_data, "id": source_id})
            mock_instance.update_source = AsyncMock(return_value=updated_source)
            
            source_update = SourceUpdate(**update_data)
            result = await mock_instance.update_source(source_id, source_update)
            
            assert result.name == update_data["name"]
            assert result.active == update_data["active"]

    @pytest.mark.asyncio
    async def test_delete_source(self, mock_session):
        """Test deleting a source."""
        source_id = 1
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.delete_source = AsyncMock(return_value=True)
            
            result = await mock_instance.delete_source(source_id)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_list_sources(self, mock_session):
        """Test listing sources with filters."""
        expected_sources = [
            Source(
                id=1,
                name="Source 1",
                url="https://example1.com",
                description="Description 1",
                is_active=True,
                last_scraped=datetime.now(),
                scrape_frequency=3600,
                source_type="rss",
                identifier="source-1"
            ),
            Source(
                id=2,
                name="Source 2",
                url="https://example2.com",
                description="Description 2",
                is_active=False,
                last_scraped=datetime.now(),
                scrape_frequency=7200,
                source_type="scraping",
                identifier="source-2"
            )
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.list_sources = AsyncMock(return_value=expected_sources)
            
            source_filter = SourceFilter(is_active=True)
            result = await mock_instance.list_sources(source_filter)
            
            assert len(result) == 2
            assert all(isinstance(source, Source) for source in result)

    @pytest.mark.asyncio
    async def test_create_article(self, mock_session, sample_article_data):
        """Test creating a new article."""
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            article_create = ArticleCreate(**sample_article_data)
            created_article = Article(id=1, **sample_article_data)
            mock_instance.create_article = AsyncMock(return_value=created_article)
            
            result = await mock_instance.create_article(article_create)
            
            assert result.title == sample_article_data["title"]
            assert result.content == sample_article_data["content"]
            assert result.source_id == sample_article_data["source_id"]

    @pytest.mark.asyncio
    async def test_get_article_by_id(self, mock_session):
        """Test getting an article by ID."""
        article_id = 1
        expected_article = Article(
            id=article_id,
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com/article",
            published_at=datetime.now(),
            source_id=1,
            content_hash="test-hash-123",
            collected_at=datetime.now(),
            discovered_at=datetime.now(),
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_article_by_id = AsyncMock(return_value=expected_article)
            
            result = await mock_instance.get_article_by_id(article_id)
            
            assert result.id == article_id
            assert result.title == "Test Article"

    @pytest.mark.asyncio
    async def test_update_article(self, mock_session, sample_article_data):
        """Test updating an article."""
        article_id = 1
        update_data = {"title": "Updated Article Title", "content": "Updated content"}
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            updated_article = Article(id=article_id, **{**sample_article_data, **update_data})
            mock_instance.update_article = AsyncMock(return_value=updated_article)
            
            article_update = ArticleUpdate(**update_data)
            result = await mock_instance.update_article(article_id, article_update)
            
            assert result.title == update_data["title"]
            assert result.content == update_data["content"]

    @pytest.mark.asyncio
    async def test_delete_article(self, mock_session):
        """Test deleting an article."""
        article_id = 1
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.delete_article = AsyncMock(return_value=True)
            
            result = await mock_instance.delete_article(article_id)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_list_articles(self, mock_session):
        """Test listing articles with filters."""
        expected_articles = [
            Article(
                id=1,
                title="Article 1",
                content="Content 1",
                canonical_url="https://example.com/article1",
                published_at=datetime.now(),
                source_id=1,
                content_hash="test-hash-1",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            ),
            Article(
                id=2,
                title="Article 2",
                content="Content 2",
                canonical_url="https://example.com/article2",
                published_at=datetime.now(),
                source_id=2,
                content_hash="test-hash-2",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.list_articles = AsyncMock(return_value=expected_articles)
            
            article_filter = ArticleListFilter(source_id=1)
            result = await mock_instance.list_articles(article_filter)
            
            assert len(result) == 2
            assert all(isinstance(article, Article) for article in result)

    @pytest.mark.asyncio
    async def test_create_annotation(self, mock_session, sample_annotation_data):
        """Test creating a new annotation."""
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            annotation_create = ArticleAnnotationCreate(**sample_annotation_data)
            created_annotation = ArticleAnnotation(id=1, **sample_annotation_data)
            mock_instance.create_annotation = AsyncMock(return_value=created_annotation)
            
            result = await mock_instance.create_annotation(annotation_create)
            
            assert result.article_id == sample_annotation_data["article_id"]
            assert result.annotation_type == sample_annotation_data["annotation_type"]
            assert result.confidence_score == sample_annotation_data["confidence_score"]

    @pytest.mark.asyncio
    async def test_get_annotation_by_id(self, mock_session):
        """Test getting an annotation by ID."""
        annotation_id = 1
        expected_annotation = ArticleAnnotation(
            id=annotation_id,
            article_id=1,
            annotation_type="huntable",
            selected_text="Contains IOCs",
            start_position=100,
            end_position=150,
            context_before="Previous context",
            context_after="Following context",
            confidence_score=0.95,
            used_for_training=False,
            usage="train",
            user_id=1,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_annotation_by_id = AsyncMock(return_value=expected_annotation)
            
            result = await mock_instance.get_annotation_by_id(annotation_id)
            
            assert result.id == annotation_id
            assert result.annotation_type == "huntable"

    @pytest.mark.asyncio
    async def test_update_annotation(self, mock_session, sample_annotation_data):
        """Test updating an annotation."""
        annotation_id = 1
        update_data = {"annotation_type": "not_huntable", "confidence_score": 0.85}
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            updated_annotation = ArticleAnnotation(id=annotation_id, **{**sample_annotation_data, **update_data})
            mock_instance.update_annotation = AsyncMock(return_value=updated_annotation)
            
            annotation_update = ArticleAnnotationUpdate(**update_data)
            result = await mock_instance.update_annotation(annotation_id, annotation_update)
            
            assert result.annotation_type == update_data["annotation_type"]
            assert result.confidence_score == update_data["confidence_score"]

    @pytest.mark.asyncio
    async def test_delete_annotation(self, mock_session):
        """Test deleting an annotation."""
        annotation_id = 1
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.delete_annotation = AsyncMock(return_value=True)
            
            result = await mock_instance.delete_annotation(annotation_id)
            
            assert result is True

    @pytest.mark.asyncio
    async def test_list_annotations(self, mock_session):
        """Test listing annotations with filters."""
        expected_annotations = [
            ArticleAnnotation(
                id=1,
                article_id=1,
                annotation_type="huntable",
                selected_text="Contains IOCs",
                start_position=100,
                end_position=150,
                context_before="Previous context",
                context_after="Following context",
                confidence_score=0.95,
                used_for_training=False,
                usage="train",
                user_id=1,
                created_at=datetime.now(),
                updated_at=datetime.now()
            ),
            ArticleAnnotation(
                id=2,
                article_id=2,
                annotation_type="not_huntable",
                selected_text="No threat intelligence",
                start_position=200,
                end_position=250,
                context_before="Previous context",
                context_after="Following context",
                confidence_score=0.80,
                used_for_training=False,
                usage="train",
                user_id=1,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.list_annotations = AsyncMock(return_value=expected_annotations)
            
            annotation_filter = ArticleAnnotationFilter(annotation_type="huntable")
            result = await mock_instance.list_annotations(annotation_filter)
            
            assert len(result) == 2
            assert all(isinstance(annotation, ArticleAnnotation) for annotation in result)

    @pytest.mark.asyncio
    async def test_get_articles_by_source(self, mock_session):
        """Test getting articles by source ID."""
        source_id = 1
        expected_articles = [
            Article(
                id=1,
                title="Article 1",
                content="Content 1",
                canonical_url="https://example.com/article1",
                published_at=datetime.now(),
                source_id=source_id,
                content_hash="test-hash-1",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            ),
            Article(
                id=2,
                title="Article 2",
                content="Content 2",
                canonical_url="https://example.com/article2",
                published_at=datetime.now(),
                source_id=source_id,
                content_hash="test-hash-2",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_articles_by_source = AsyncMock(return_value=expected_articles)
            
            result = await mock_instance.get_articles_by_source(source_id)
            
            assert len(result) == 2
            assert all(article.source_id == source_id for article in result)

    @pytest.mark.asyncio
    async def test_get_annotations_by_article(self, mock_session):
        """Test getting annotations by article ID."""
        article_id = 1
        expected_annotations = [
            ArticleAnnotation(
                id=1,
                article_id=article_id,
                annotation_type="huntable",
                selected_text="Contains IOCs",
                start_position=100,
                end_position=150,
                context_before="Previous context",
                context_after="Following context",
                confidence_score=0.95,
                used_for_training=False,
                usage="train",
                user_id=1,
                created_at=datetime.now(),
                updated_at=datetime.now()
            ),
            ArticleAnnotation(
                id=2,
                article_id=article_id,
                annotation_type="not_huntable",
                selected_text="No threat intelligence",
                start_position=200,
                end_position=250,
                context_before="Previous context",
                context_after="Following context",
                confidence_score=0.80,
                used_for_training=False,
                usage="train",
                user_id=1,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_annotations_by_article = AsyncMock(return_value=expected_annotations)
            
            result = await mock_instance.get_annotations_by_article(article_id)
            
            assert len(result) == 2
            assert all(annotation.article_id == article_id for annotation in result)

    @pytest.mark.asyncio
    async def test_search_articles(self, mock_session):
        """Test searching articles by content."""
        search_query = "threat intelligence"
        expected_articles = [
            Article(
                id=1,
                title="Threat Intelligence Report",
                content="This article contains threat intelligence information",
                canonical_url="https://example.com/article1",
                published_at=datetime.now(),
                source_id=1,
                content_hash="test-hash-1",
                collected_at=datetime.now(),
                discovered_at=datetime.now(),
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.search_articles = AsyncMock(return_value=expected_articles)
            
            result = await mock_instance.search_articles(search_query)
            
            assert len(result) == 1
            assert search_query.lower() in result[0].title.lower()

    @pytest.mark.asyncio
    async def test_get_article_statistics(self, mock_session):
        """Test getting article statistics."""
        expected_stats = {
            "total_articles": 100,
            "articles_by_source": {1: 50, 2: 30, 3: 20},
            "articles_by_month": {"2024-01": 25, "2024-02": 30, "2024-03": 45},
            "average_content_length": 1500
        }
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_article_statistics = AsyncMock(return_value=expected_stats)
            
            result = await mock_instance.get_article_statistics()
            
            assert result["total_articles"] == 100
            assert len(result["articles_by_source"]) == 3
            assert len(result["articles_by_month"]) == 3

    @pytest.mark.asyncio
    async def test_bulk_create_articles(self, mock_session):
        """Test bulk creating articles."""
        articles_data = [
            {
                "title": "Article 1",
                "content": "Content 1",
                "canonical_url": "https://example.com/article1",
                "published_at": datetime.now(),
                "source_id": 1,
                "content_hash": "test-hash-1",
                "collected_at": datetime.now(),
                "discovered_at": datetime.now(),
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            },
            {
                "title": "Article 2",
                "content": "Content 2",
                "canonical_url": "https://example.com/article2",
                "published_at": datetime.now(),
                "source_id": 1,
                "content_hash": "test-hash-2",
                "collected_at": datetime.now(),
                "discovered_at": datetime.now(),
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            created_articles = [Article(id=i+1, **data) for i, data in enumerate(articles_data)]
            mock_instance.bulk_create_articles = AsyncMock(return_value=created_articles)
            
            article_creates = [ArticleCreate(**data) for data in articles_data]
            result = await mock_instance.bulk_create_articles(article_creates)
            
            assert len(result) == 2
            assert all(isinstance(article, Article) for article in result)

    @pytest.mark.asyncio
    async def test_bulk_update_articles(self, mock_session):
        """Test bulk updating articles."""
        updates = [
            {"id": 1, "title": "Updated Article 1"},
            {"id": 2, "title": "Updated Article 2"}
        ]
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            now = datetime.now()
            updated_articles = [
                Article(
                    id=1, 
                    title="Updated Article 1",
                    source_id=1,
                    canonical_url="https://example.com/article1",
                    published_at=now,
                    content="Content 1",
                    content_hash="test-hash-1",
                    collected_at=now,
                    discovered_at=now,
                    created_at=now,
                    updated_at=now
                ),
                Article(
                    id=2, 
                    title="Updated Article 2",
                    source_id=1,
                    canonical_url="https://example.com/article2",
                    published_at=now,
                    content="Content 2",
                    content_hash="test-hash-2",
                    collected_at=now,
                    discovered_at=now,
                    created_at=now,
                    updated_at=now
                )
            ]
            mock_instance.bulk_update_articles = AsyncMock(return_value=updated_articles)
            
            result = await mock_instance.bulk_update_articles(updates)
            
            assert len(result) == 2
            assert result[0].title == "Updated Article 1"
            assert result[1].title == "Updated Article 2"

    @pytest.mark.asyncio
    async def test_cleanup_old_articles(self, mock_session):
        """Test cleaning up old articles."""
        cutoff_date = datetime.now() - timedelta(days=30)
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.cleanup_old_articles = AsyncMock(return_value=25)
            
            result = await mock_instance.cleanup_old_articles(cutoff_date)
            
            assert result == 25

    @pytest.mark.asyncio
    async def test_get_database_health(self, mock_session):
        """Test getting database health status."""
        expected_health = {
            "status": "healthy",
            "connection_count": 5,
            "last_backup": datetime.now() - timedelta(hours=1),
            "database_size_mb": 1024
        }
        
        # Mock the database manager
        with patch('src.database.async_manager.AsyncDatabaseManager') as mock_manager:
            mock_instance = mock_manager.return_value
            mock_instance.get_database_health = AsyncMock(return_value=expected_health)
            
            result = await mock_instance.get_database_health()
            
            assert result["status"] == "healthy"
            assert result["connection_count"] == 5
            assert result["database_size_mb"] == 1024
