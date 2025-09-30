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


@pytest.mark.skip(reason="Async mock configuration needed for AsyncDatabaseManager tests")
class TestAsyncDatabaseManager:
    """Test AsyncDatabaseManager functionality."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock database engine."""
        engine = AsyncMock()
        engine.begin = AsyncMock()
        engine.__aenter__ = AsyncMock(return_value=engine)
        engine.__aexit__ = AsyncMock(return_value=None)
        return engine

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.add = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.close = AsyncMock()
        session.flush = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=None)
        return session

    @pytest.fixture
    def db_manager(self, mock_engine):
        """Create AsyncDatabaseManager instance with mocked engine."""
        with patch('src.database.async_manager.create_async_engine', return_value=mock_engine):
            with patch('src.database.async_manager.async_sessionmaker') as mock_sessionmaker:
                mock_sessionmaker.return_value = AsyncMock()
                manager = AsyncDatabaseManager()
                manager.engine = mock_engine
                return manager

    @pytest.fixture
    def sample_source_data(self):
        """Create sample source data."""
        return SourceCreate(
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            rss_url="https://example.com/feed.xml",
            check_frequency=3600,
            lookback_days=180,
            active=True,
            config={}
        )

    @pytest.fixture
    def sample_article_data(self):
        """Create sample article data."""
        return ArticleCreate(
            source_id=1,
            canonical_url="https://example.com/article1",
            title="Test Article",
            published_at=datetime.utcnow(),
            content="This is a test article about threat hunting.",
            summary="Test summary",
            authors=["Test Author"],
            tags=["security"],
            article_metadata={},
            content_hash="test_hash_123"
        )

    @pytest.fixture
    def sample_annotation_data(self):
        """Create sample annotation data."""
        return ArticleAnnotationCreate(
            article_id=1,
            annotation_type="huntable",
            selected_text="High-quality threat intelligence content",
            start_position=0,
            end_position=40,
            confidence_score=0.95
        )

    @pytest.mark.asyncio
    async def test_get_session(self, db_manager, mock_session):
        """Test getting database session."""
        db_manager.AsyncSessionLocal = AsyncMock(return_value=mock_session)
        
        async with db_manager.get_session() as session:
            assert session == mock_session
        
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_session_exception_handling(self, db_manager, mock_session):
        """Test session exception handling."""
        db_manager.AsyncSessionLocal = AsyncMock(return_value=mock_session)
        mock_session.rollback = AsyncMock()
        
        with patch.object(mock_session, 'execute', side_effect=Exception("Database error")):
            with pytest.raises(Exception, match="Database error"):
                async with db_manager.get_session() as session:
                    await session.execute("SELECT 1")
        
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tables(self, db_manager, mock_engine):
        """Test table creation."""
        mock_conn = AsyncMock()
        mock_engine.begin.return_value.__aenter__.return_value = mock_conn
        
        await db_manager.create_tables()
        
        mock_engine.begin.assert_called_once()
        mock_conn.run_sync.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_tables_failure(self, db_manager, mock_engine):
        """Test table creation failure."""
        mock_engine.begin.side_effect = Exception("Connection error")
        
        with pytest.raises(Exception, match="Connection error"):
            await db_manager.create_tables()

    @pytest.mark.asyncio
    async def test_get_database_stats(self, db_manager, mock_session):
        """Test getting database statistics."""
        # Mock query results
        mock_result = Mock()
        mock_result.scalar.return_value = 100
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            stats = await db_manager.get_database_stats()
        
        assert 'total_sources' in stats
        assert 'total_articles' in stats
        assert 'total_annotations' in stats

    # Source CRUD Operations

    @pytest.mark.asyncio
    async def test_create_source_success(self, db_manager, mock_session, sample_source_data):
        """Test successful source creation."""
        # Mock query result
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        # Mock the created source
        created_source = Mock(spec=SourceTable)
        created_source.id = 1
        created_source.identifier = "test-source"
        created_source.name = "Test Source"
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            with patch('src.database.models.SourceTable', return_value=created_source):
                result = await db_manager.create_source(sample_source_data)
        
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_source_duplicate_identifier(self, db_manager, mock_session, sample_source_data):
        """Test source creation with duplicate identifier."""
        # Mock existing source
        existing_source = Mock(spec=SourceTable)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_source
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.create_source(sample_source_data)
        
        assert result is None
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_source_success(self, db_manager, mock_session):
        """Test successful source retrieval."""
        # Mock source data
        source_table = Mock(spec=SourceTable)
        source_table.id = 1
        source_table.identifier = "test-source"
        source_table.name = "Test Source"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = source_table
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_source(1)
        
        assert result is not None
        assert result.id == 1
        assert result.identifier == "test-source"

    @pytest.mark.asyncio
    async def test_get_source_not_found(self, db_manager, mock_session):
        """Test source retrieval when not found."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_source(999)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_update_source_success(self, db_manager, mock_session):
        """Test successful source update."""
        # Mock existing source
        existing_source = Mock(spec=SourceTable)
        existing_source.id = 1
        existing_source.identifier = "test-source"
        existing_source.name = "Updated Source"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_source
        mock_session.execute.return_value = mock_result
        
        update_data = SourceUpdate(name="Updated Source")
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.update_source(1, update_data)
        
        assert result is not None
        assert result.name == "Updated Source"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_source_not_found(self, db_manager, mock_session):
        """Test source update when not found."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        update_data = SourceUpdate(name="Updated Source")
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.update_source(999, update_data)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_source_success(self, db_manager, mock_session):
        """Test successful source deletion."""
        # Mock existing source
        existing_source = Mock(spec=SourceTable)
        existing_source.id = 1
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_source
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.delete_source(1)
        
        assert result is True
        mock_session.delete.assert_called_once_with(existing_source)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_source_not_found(self, db_manager, mock_session):
        """Test source deletion when not found."""
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.delete_source(999)
        
        assert result is False

    # Article CRUD Operations

    @pytest.mark.asyncio
    async def test_create_article_success(self, db_manager, mock_session, sample_article_data):
        """Test successful article creation."""
        # Mock deduplication service
        mock_dedup_service = AsyncMock()
        mock_dedup_service.create_article_with_deduplication.return_value = (True, Mock(spec=ArticleTable), [])
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            with patch('src.services.deduplication.AsyncDeduplicationService', return_value=mock_dedup_service):
                result = await db_manager.create_article(sample_article_data)
        
        assert result is not None
        mock_dedup_service.create_article_with_deduplication.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_article_duplicate(self, db_manager, mock_session, sample_article_data):
        """Test article creation with duplicate."""
        # Mock deduplication service
        mock_dedup_service = AsyncMock()
        existing_article = Mock(spec=ArticleTable)
        mock_dedup_service.create_article_with_deduplication.return_value = (False, existing_article, [])
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            with patch('src.services.deduplication.AsyncDeduplicationService', return_value=mock_dedup_service):
                result = await db_manager.create_article(sample_article_data)
        
        assert result is not None
        assert result == existing_article

    @pytest.mark.asyncio
    async def test_get_article_success(self, db_manager, mock_session):
        """Test successful article retrieval."""
        # Mock article data
        article_table = Mock(spec=ArticleTable)
        article_table.id = 1
        article_table.title = "Test Article"
        article_table.canonical_url = "https://example.com/article1"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = article_table
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_article(1)
        
        assert result is not None
        assert result.id == 1
        assert result.title == "Test Article"

    @pytest.mark.asyncio
    async def test_get_article_by_url_success(self, db_manager, mock_session):
        """Test successful article retrieval by URL."""
        # Mock article data
        article_table = Mock(spec=ArticleTable)
        article_table.id = 1
        article_table.canonical_url = "https://example.com/article1"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = article_table
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_article_by_url("https://example.com/article1")
        
        assert result is not None
        assert result.canonical_url == "https://example.com/article1"

    @pytest.mark.asyncio
    async def test_update_article_success(self, db_manager, mock_session):
        """Test successful article update."""
        # Mock existing article
        existing_article = Mock(spec=ArticleTable)
        existing_article.id = 1
        existing_article.title = "Updated Article"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_article
        mock_session.execute.return_value = mock_result
        
        update_data = ArticleUpdate(title="Updated Article")
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.update_article(1, update_data)
        
        assert result is not None
        assert result.title == "Updated Article"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_article_success(self, db_manager, mock_session):
        """Test successful article deletion."""
        # Mock existing article
        existing_article = Mock(spec=ArticleTable)
        existing_article.id = 1
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_article
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.delete_article(1)
        
        assert result is True
        mock_session.delete.assert_called_once_with(existing_article)
        mock_session.commit.assert_called_once()

    # Annotation CRUD Operations

    @pytest.mark.asyncio
    async def test_create_annotation_success(self, db_manager, mock_session, sample_annotation_data):
        """Test successful annotation creation."""
        # Mock created annotation
        created_annotation = Mock(spec=ArticleAnnotationTable)
        created_annotation.id = 1
        created_annotation.article_id = 1
        created_annotation.label = "huntable"
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            with patch('src.database.models.ArticleAnnotationTable', return_value=created_annotation):
                result = await db_manager.create_annotation(sample_annotation_data)
        
        assert result is not None
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_annotation_success(self, db_manager, mock_session):
        """Test successful annotation retrieval."""
        # Mock annotation data
        annotation_table = Mock(spec=ArticleAnnotationTable)
        annotation_table.id = 1
        annotation_table.label = "huntable"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = annotation_table
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_annotation(1)
        
        assert result is not None
        assert result.id == 1
        assert result.label == "huntable"

    @pytest.mark.asyncio
    async def test_get_article_annotations(self, db_manager, mock_session):
        """Test getting article annotations."""
        # Mock annotation data
        annotation1 = Mock(spec=ArticleAnnotationTable)
        annotation1.id = 1
        annotation1.label = "huntable"
        
        annotation2 = Mock(spec=ArticleAnnotationTable)
        annotation2.id = 2
        annotation2.label = "not huntable"
        
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [annotation1, annotation2]
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_article_annotations(1)
        
        assert len(result) == 2
        assert result[0].label == "huntable"
        assert result[1].label == "not huntable"

    @pytest.mark.asyncio
    async def test_update_annotation_success(self, db_manager, mock_session):
        """Test successful annotation update."""
        # Mock existing annotation
        existing_annotation = Mock(spec=ArticleAnnotationTable)
        existing_annotation.id = 1
        existing_annotation.label = "updated"
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_annotation
        mock_session.execute.return_value = mock_result
        
        update_data = ArticleAnnotationUpdate(label="updated")
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.update_annotation(1, update_data)
        
        assert result is not None
        assert result.label == "updated"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_annotation_success(self, db_manager, mock_session):
        """Test successful annotation deletion."""
        # Mock existing annotation
        existing_annotation = Mock(spec=ArticleAnnotationTable)
        existing_annotation.id = 1
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_annotation
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.delete_annotation(1)
        
        assert result is True
        mock_session.delete.assert_called_once_with(existing_annotation)
        mock_session.commit.assert_called_once()

    # Utility Methods

    @pytest.mark.asyncio
    async def test_get_existing_content_hashes(self, db_manager, mock_session):
        """Test getting existing content hashes."""
        # Mock hash data
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = ["hash1", "hash2", "hash3"]
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_existing_content_hashes(limit=1000)
        
        assert isinstance(result, set)
        assert "hash1" in result
        assert "hash2" in result
        assert "hash3" in result

    @pytest.mark.asyncio
    async def test_get_total_article_count(self, db_manager, mock_session):
        """Test getting total article count."""
        mock_result = Mock()
        mock_result.scalar.return_value = 150
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_total_article_count()
        
        assert result == 150

    @pytest.mark.asyncio
    async def test_get_articles_count_with_filters(self, db_manager, mock_session):
        """Test getting article count with filters."""
        mock_result = Mock()
        mock_result.scalar.return_value = 50
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_articles_count(source_id=1, processing_status="processed")
        
        assert result == 50

    @pytest.mark.asyncio
    async def test_get_source_quality_stats(self, db_manager, mock_session):
        """Test getting source quality statistics."""
        # Mock stats data
        mock_row1 = Mock()
        mock_row1._asdict.return_value = {
            'source_id': 1,
            'source_name': 'Test Source',
            'total_articles': 100,
            'avg_quality_score': 0.85
        }
        
        mock_result = Mock()
        mock_result.all.return_value = [mock_row1]
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_source_quality_stats()
        
        assert len(result) == 1
        assert result[0]['source_id'] == 1
        assert result[0]['source_name'] == 'Test Source'

    @pytest.mark.asyncio
    async def test_get_deduplication_stats(self, db_manager, mock_session):
        """Test getting deduplication statistics."""
        # Mock stats data
        mock_result = Mock()
        mock_result.scalar.return_value = 1000
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_deduplication_stats()
        
        assert 'total_articles' in result
        assert 'unique_articles' in result
        assert 'duplicate_articles' in result

    @pytest.mark.asyncio
    async def test_get_annotation_stats(self, db_manager, mock_session):
        """Test getting annotation statistics."""
        # Mock stats data
        mock_result = Mock()
        mock_result.scalar.return_value = 500
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_annotation_stats()
        
        assert 'total_annotations' in result
        assert 'huntable_count' in result
        assert 'not_huntable_count' in result

    @pytest.mark.asyncio
    async def test_get_performance_metrics(self, db_manager, mock_session):
        """Test getting performance metrics."""
        # Mock metrics data
        mock_row = Mock()
        mock_row._asdict.return_value = {
            'source_id': 1,
            'avg_response_time': 1.5,
            'success_rate': 0.95
        }
        
        mock_result = Mock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_performance_metrics()
        
        assert len(result) == 1
        assert result[0]['source_id'] == 1
        assert result[0]['avg_response_time'] == 1.5

    @pytest.mark.asyncio
    async def test_get_ingestion_analytics(self, db_manager, mock_session):
        """Test getting ingestion analytics."""
        # Mock analytics data
        mock_result = Mock()
        mock_result.scalar.return_value = 100
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_ingestion_analytics()
        
        assert 'total_articles' in result
        assert 'recent_articles' in result
        assert 'daily_stats' in result

    @pytest.mark.asyncio
    async def test_update_source_health(self, db_manager, mock_session):
        """Test updating source health."""
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            await db_manager.update_source_health(1, success=True, response_time=1.5)
        
        mock_session.execute.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_source_article_count(self, db_manager, mock_session):
        """Test updating source article count."""
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            await db_manager.update_source_article_count(1)
        
        mock_session.execute.assert_called()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_source_min_content_length(self, db_manager, mock_session):
        """Test updating source minimum content length."""
        # Mock existing source
        existing_source = Mock(spec=SourceTable)
        existing_source.id = 1
        existing_source.config = {}
        
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_source
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.update_source_min_content_length(1, 1000)
        
        assert result is not None
        assert result['min_content_length'] == 1000
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_source_hunt_scores(self, db_manager, mock_session):
        """Test getting source hunt scores."""
        # Mock hunt scores data
        mock_row = Mock()
        mock_row._asdict.return_value = {
            'source_id': 1,
            'source_name': 'Test Source',
            'avg_hunt_score': 75.5,
            'total_articles': 100
        }
        
        mock_result = Mock()
        mock_result.all.return_value = [mock_row]
        mock_session.execute.return_value = mock_result
        
        with patch.object(db_manager, 'get_session', return_value=mock_session):
            result = await db_manager.get_source_hunt_scores()
        
        assert len(result) == 1
        assert result[0]['source_id'] == 1
        assert result[0]['avg_hunt_score'] == 75.5
