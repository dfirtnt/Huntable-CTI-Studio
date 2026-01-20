"""Tests for async database manager functionality."""

import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from typing import Dict, Any

from src.database.async_manager import AsyncDatabaseManager
from tests.utils.async_mocks import AsyncMockSession, setup_async_query_chain

# Mark all tests in this file as unit tests (use mocks, no real infrastructure)
pytestmark = pytest.mark.unit


class TestAsyncDatabaseManager:
    """Test AsyncDatabaseManager functionality."""

    @pytest.fixture
    def mock_engine(self):
        """Create mock async engine."""
        engine = AsyncMock()
        engine.begin = AsyncMock()
        engine.begin.return_value.__aenter__ = AsyncMock(return_value=engine.begin.return_value)
        engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
        engine.dispose = AsyncMock()
        return engine

    @pytest.fixture
    def mock_session_factory(self):
        """Create mock async session factory."""
        factory = AsyncMock()
        return factory

    @pytest.fixture
    def manager(self, mock_engine, mock_session_factory):
        """Create AsyncDatabaseManager with mocked dependencies."""
        with patch('src.database.async_manager.create_async_engine', return_value=mock_engine), \
             patch('src.database.async_manager.async_sessionmaker', return_value=mock_session_factory):
            manager = AsyncDatabaseManager()
            manager.engine = mock_engine
            manager.AsyncSessionLocal = mock_session_factory
            return manager

    @pytest.mark.asyncio
    async def test_get_session(self, manager, mock_session_factory):
        """Test getting async session."""
        mock_session = AsyncMockSession()
        mock_session_factory.return_value = mock_session
        
        async with manager.get_session() as session:
            assert session is not None

    @pytest.mark.asyncio
    async def test_get_session_error_handling(self, manager, mock_session_factory):
        """Test session error handling."""
        mock_session = AsyncMockSession()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session_factory.return_value = mock_session
        
        # Simulate error in session
        async def error_context():
            async with manager.get_session() as session:
                raise Exception("Test error")
        
        with pytest.raises(Exception):
            await error_context()
        
        mock_session.rollback.assert_called()

    @pytest.mark.asyncio
    async def test_create_tables(self, manager, mock_engine):
        """Test table creation."""
        await manager.create_tables()
        
        mock_engine.begin.assert_called()

    @pytest.mark.asyncio
    async def test_get_database_stats(self, manager, mock_session_factory):
        """Test database statistics retrieval."""
        mock_session = AsyncMockSession()
        
        # Setup query chain for stats
        mock_query = Mock()
        setup_async_query_chain(mock_query, return_value=10)  # Mock count result
        
        mock_session.execute = AsyncMock(return_value=mock_query)
        mock_session_factory.return_value = mock_session
        
        stats = await manager.get_database_stats()
        
        assert isinstance(stats, dict)
        assert 'total_sources' in stats or 'total_articles' in stats

    @pytest.mark.asyncio
    async def test_create_source(self, manager, mock_session_factory):
        """Test source creation."""
        mock_session = AsyncMockSession()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session_factory.return_value = mock_session
        
        source_data = {
            'name': 'Test Source',
            'url': 'https://example.com',
            'source_type': 'rss'
        }
        
        result = await manager.create_source(**source_data)
        
        assert result is not None
        mock_session.add.assert_called()

    @pytest.mark.asyncio
    async def test_get_article_by_id(self, manager, mock_session_factory):
        """Test getting article by ID."""
        mock_session = AsyncMockSession()
        mock_article = Mock()
        mock_article.id = 1
        mock_article.title = "Test Article"
        
        mock_query = Mock()
        setup_async_query_chain(mock_query, return_value=[mock_article])
        mock_query.first = AsyncMock(return_value=mock_article)
        
        mock_session.execute = AsyncMock(return_value=mock_query)
        mock_session_factory.return_value = mock_session
        
        article = await manager.get_article_by_id(1)
        
        assert article is not None

    @pytest.mark.asyncio
    async def test_search_similar_annotations(self, manager, mock_session_factory):
        """Test similar annotation search."""
        mock_session = AsyncMockSession()
        mock_annotation = {
            'id': 1,
            'article_id': 1,
            'selected_text': 'PowerShell command',
            'similarity': 0.85
        }
        
        mock_query = Mock()
        setup_async_query_chain(mock_query, return_value=[mock_annotation])
        
        mock_session.execute = AsyncMock(return_value=mock_query)
        mock_session_factory.return_value = mock_session
        
        results = await manager.search_similar_annotations(
            query_embedding=[0.1] * 768,
            limit=10,
            threshold=0.7
        )
        
        assert isinstance(results, list)
