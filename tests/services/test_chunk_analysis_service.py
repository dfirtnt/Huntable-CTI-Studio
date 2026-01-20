"""Tests for chunk analysis service functionality."""

import pytest
from unittest.mock import Mock, patch
from typing import List, Tuple

from src.services.chunk_analysis_service import ChunkAnalysisService
from src.database.models import ChunkAnalysisResultTable, ArticleTable

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestChunkAnalysisService:
    """Test ChunkAnalysisService functionality."""

    @pytest.fixture
    def mock_db_session(self):
        """Create mock database session."""
        session = Mock()
        session.query = Mock()
        session.add = Mock()
        session.commit = Mock()
        return session

    @pytest.fixture
    def service(self, mock_db_session):
        """Create ChunkAnalysisService instance."""
        return ChunkAnalysisService(mock_db_session)

    @pytest.fixture
    def sample_article(self):
        """Create sample article."""
        article = Mock(spec=ArticleTable)
        article.id = 1
        article.article_metadata = {'threat_hunting_score': 85.0}
        return article

    def test_should_store_analysis_high_score(self, service, mock_db_session, sample_article):
        """Test should_store_analysis with high hunt score."""
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_article
        mock_db_session.query.return_value = mock_query
        
        should_store = service.should_store_analysis(article_id=1)
        
        assert should_store is True

    def test_should_store_analysis_low_score(self, service, mock_db_session, sample_article):
        """Test should_store_analysis with low hunt score."""
        sample_article.article_metadata = {'threat_hunting_score': 30.0}
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = sample_article
        mock_db_session.query.return_value = mock_query
        
        should_store = service.should_store_analysis(article_id=1)
        
        assert should_store is False

    def test_store_chunk_analysis_success(self, service, mock_db_session, sample_article):
        """Test successful chunk analysis storage."""
        mock_query = Mock()
        mock_query.filter.return_value.first.side_effect = [sample_article, None]  # Article exists, chunk doesn't
        mock_db_session.query.return_value = mock_query
        
        chunks = [(0, 100, "PowerShell command execution")]
        ml_predictions = [(True, 0.85)]
        model_version = "test-model-v1"
        
        stored_count = service.store_chunk_analysis(
            article_id=1,
            chunks=chunks,
            ml_predictions=ml_predictions,
            model_version=model_version
        )
        
        assert stored_count >= 0
        mock_db_session.add.assert_called()

    def test_store_chunk_analysis_duplicate_chunk(self, service, mock_db_session, sample_article):
        """Test storage with duplicate chunk."""
        existing_chunk = Mock(spec=ChunkAnalysisResultTable)
        mock_query = Mock()
        mock_query.filter.return_value.first.side_effect = [sample_article, existing_chunk]  # Chunk exists
        mock_db_session.query.return_value = mock_query
        
        chunks = [(0, 100, "PowerShell command execution")]
        ml_predictions = [(True, 0.85)]
        model_version = "test-model-v1"
        
        stored_count = service.store_chunk_analysis(
            article_id=1,
            chunks=chunks,
            ml_predictions=ml_predictions,
            model_version=model_version
        )
        
        assert stored_count == 0  # Should skip duplicate
