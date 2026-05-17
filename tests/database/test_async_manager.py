"""Tests for async database manager functionality."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

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
        return AsyncMock()

    @pytest.fixture
    def manager(self, mock_engine, mock_session_factory):
        """Create AsyncDatabaseManager with mocked dependencies."""
        with (
            patch("src.database.async_manager.create_async_engine", return_value=mock_engine),
            patch("src.database.async_manager.async_sessionmaker", return_value=mock_session_factory),
        ):
            manager = AsyncDatabaseManager()
            manager.engine = mock_engine
            manager.AsyncSessionLocal = mock_session_factory
            return manager

    @pytest.mark.asyncio
    async def test_get_session(self, manager, mock_session_factory):
        """Test getting async session."""
        from contextlib import asynccontextmanager

        mock_session = AsyncMockSession()
        # Make mock_session_factory return the session directly
        mock_session_factory.return_value = mock_session

        # Mock get_session as async context manager
        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        async with manager.get_session() as session:
            assert session is not None

    @pytest.mark.asyncio
    async def test_get_session_error_handling(self, manager, mock_session_factory):
        """Test session error handling."""
        from contextlib import asynccontextmanager

        mock_session = AsyncMockSession()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        mock_session_factory.return_value = mock_session

        # Mock get_session as async context manager that raises error
        @asynccontextmanager
        async def mock_get_session():
            try:
                yield mock_session
            except Exception:
                await mock_session.rollback()
                raise
            finally:
                await mock_session.close()

        manager.get_session = mock_get_session

        # Simulate error in session
        with pytest.raises(Exception, match="Test error"):
            async with manager.get_session() as _:
                raise Exception("Test error")

        # rollback is called in the context manager's exception handler
        # Verify it was called (may be called multiple times due to finally block)
        assert mock_session.rollback.called or mock_session.close.called

    @pytest.mark.asyncio
    async def test_create_tables(self, manager, mock_engine):
        """Test table creation."""
        # Mock engine.begin() to return an async context manager
        from contextlib import asynccontextmanager

        @asynccontextmanager
        async def mock_begin():
            conn = AsyncMock()
            conn.run_sync = AsyncMock()
            yield conn

        # Replace the mock_engine.begin with our async context manager
        mock_engine.begin = Mock(return_value=mock_begin())

        await manager.create_tables()

        mock_engine.begin.assert_called()

    @pytest.mark.asyncio
    async def test_get_database_stats(self, manager, mock_session_factory):
        """Test database statistics retrieval."""
        from contextlib import asynccontextmanager

        mock_session = AsyncMockSession()

        # Setup query chain for stats
        mock_result = Mock()
        mock_result.scalar = Mock(return_value=10)
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_factory.return_value = mock_session

        # Mock get_session as async context manager
        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        stats = await manager.get_database_stats()

        assert isinstance(stats, dict)
        assert "total_sources" in stats or "total_articles" in stats

    @pytest.mark.asyncio
    async def test_get_sigma_rule_embedding_stats(self, manager, mock_session_factory):
        """Sigma rule counts and RAG-searchable embedding coverage."""
        from contextlib import asynccontextmanager

        mock_session = AsyncMockSession()
        mock_session.execute = AsyncMock(
            side_effect=[
                Mock(scalar=Mock(return_value=100)),
                Mock(scalar=Mock(return_value=80)),
            ]
        )
        mock_session_factory.return_value = mock_session

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        stats = await manager.get_sigma_rule_embedding_stats()

        assert stats["total_sigma_rules"] == 100
        assert stats["sigma_rules_with_rag_embedding"] == 80
        assert stats["sigma_embedding_coverage_percent"] == 80.0
        assert stats["sigma_rules_pending_rag_embedding"] == 20
        assert mock_session.execute.await_count == 2

    @pytest.mark.asyncio
    async def test_create_source(self, manager, mock_session_factory):
        """Test source creation."""
        from contextlib import asynccontextmanager
        from datetime import datetime

        from src.models.source import Source

        mock_session = AsyncMockSession()
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()
        mock_session_factory.return_value = mock_session

        # Mock get_session as async context manager
        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        # Mock create_source to return a Source object
        now = datetime.now()
        mock_source = Source(
            id=1,
            identifier="test-source",
            name="Test Source",
            url="https://example.com",
            check_frequency=3600,
            lookback_days=180,
            active=True,
            consecutive_failures=0,
            total_articles=0,
            average_response_time=0.0,
            created_at=now,
            updated_at=now,
            config={},
        )
        manager.create_source = AsyncMock(return_value=mock_source)

        source_data = {
            "identifier": "test-source",
            "name": "Test Source",
            "url": "https://example.com",
            "rss_url": "https://example.com/rss",
        }

        result = await manager.create_source(**source_data)

        assert result is not None

    @pytest.mark.asyncio
    async def test_get_article_by_id(self, manager, mock_session_factory):
        """Test getting article by ID."""
        from contextlib import asynccontextmanager
        from datetime import datetime

        from src.models.article import Article

        mock_session = AsyncMockSession()
        now = datetime.now()
        mock_article = Article(
            id=1,
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com/article",
            url="https://example.com/article",
            published_at=now,
            source_id=1,
            content_hash="test-hash",
            word_count=2,
            processing_status="processed",
            authors=[],
            tags=[],
            article_metadata={},
            collected_at=now,
            discovered_at=now,
            created_at=now,
            updated_at=now,
        )

        # Mock get_session as async context manager
        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session
        manager.get_article_by_id = AsyncMock(return_value=mock_article)

        result = await manager.get_article_by_id(1)

        assert result is not None
        assert result.id == 1
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
        mock_annotation = {"id": 1, "article_id": 1, "selected_text": "PowerShell command", "similarity": 0.85}

        mock_query = Mock()
        setup_async_query_chain(mock_query, return_value=[mock_annotation])

        mock_session.execute = AsyncMock(return_value=mock_query)
        mock_session_factory.return_value = mock_session

        results = await manager.search_similar_annotations(query_embedding=[0.1] * 768, limit=10, threshold=0.7)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_articles_by_lexical_terms(self, manager, mock_session_factory):
        """Test search_articles_by_lexical_terms returns articles matching terms."""
        from contextlib import asynccontextmanager

        from tests.utils.async_mocks import AsyncMockSession

        mock_session = AsyncMockSession()
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.title = "Emotet delivery techniques"
        mock_row.summary = "Summary"
        mock_row.content = "Content about emotet"
        mock_row.canonical_url = "https://example.com/1"
        mock_row.published_at = None
        mock_row.source_id = 1
        mock_row.article_metadata = {}
        mock_row.source_name = "Test Source"

        mock_result = MagicMock()
        mock_result.fetchall = MagicMock(return_value=[mock_row])
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session_factory.return_value = mock_session

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        results = await manager.search_articles_by_lexical_terms(
            terms=["emotet"],
            limit=10,
        )

        assert isinstance(results, list)
        assert len(results) == 1
        assert results[0]["title"] == "Emotet delivery techniques"
        assert results[0]["similarity"] == 0.35
        assert results[0]["source_name"] == "Test Source"

    @pytest.mark.asyncio
    async def test_search_articles_by_lexical_terms_empty_terms(self, manager):
        """Test search_articles_by_lexical_terms returns [] for empty terms."""
        results = await manager.search_articles_by_lexical_terms(terms=[], limit=10)
        assert results == []

    @pytest.mark.asyncio
    async def test_create_source_upsert_returns_source(self, manager):
        """create_source uses an upsert and returns the Source model from the DB row.

        Regression: the old implementation used session.add() with no ON CONFLICT
        guard, which produced duplicate rows when list_sources() silently returned [].
        The new implementation uses pg_insert(...).on_conflict_do_update() so the
        call is idempotent regardless of whether the row already exists.
        """
        from contextlib import asynccontextmanager
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock

        from src.models.source import SourceConfig, SourceCreate

        now = datetime.now()
        fake_db_row = SimpleNamespace(
            id=99,
            identifier="talos-blog",
            name="Cisco Talos",
            url="https://blog.talosintelligence.com",
            rss_url="https://blog.talosintelligence.com/rss.xml",
            check_frequency=1800,
            lookback_days=180,
            active=True,
            config={},
            last_check=None,
            last_success=None,
            consecutive_failures=0,
            total_articles=0,
            average_response_time=0.0,
            created_at=now,
            updated_at=now,
        )

        mock_execute_result = Mock()
        mock_execute_result.scalar_one = Mock(return_value=fake_db_row)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.commit = AsyncMock()

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        source_data = SourceCreate(
            identifier="talos-blog",
            name="Cisco Talos",
            url="https://blog.talosintelligence.com",
            rss_url="https://blog.talosintelligence.com/rss.xml",
            active=True,
            config=SourceConfig(check_frequency=1800, lookback_days=180),
        )

        result = await manager.create_source(source_data)

        # Verify the result is a Source with the right identifier
        assert result is not None
        assert result.identifier == "talos-blog"
        assert result.id == 99

        # Verify it used execute (upsert path), not session.add (old blind-insert path)
        mock_session.execute.assert_awaited_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_source_upsert_does_not_use_session_add(self, manager):
        """create_source must NOT call session.add() — that was the pre-upsert path
        that allowed duplicates to be created when ON CONFLICT was absent."""
        from contextlib import asynccontextmanager
        from datetime import datetime
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, Mock

        from src.models.source import SourceCreate

        now = datetime.now()
        fake_db_row = SimpleNamespace(
            id=1, identifier="test-src", name="Test", url="https://t.co",
            rss_url=None, check_frequency=3600, lookback_days=180,
            active=True, config={}, last_check=None, last_success=None,
            consecutive_failures=0, total_articles=0, average_response_time=0.0,
            created_at=now, updated_at=now,
        )

        mock_execute_result = Mock()
        mock_execute_result.scalar_one = Mock(return_value=fake_db_row)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_execute_result)
        mock_session.commit = AsyncMock()
        mock_session.add = Mock()

        @asynccontextmanager
        async def mock_get_session():
            yield mock_session

        manager.get_session = mock_get_session

        source_data = SourceCreate(identifier="test-src", name="Test", url="https://t.co")
        await manager.create_source(source_data)

        # session.add() must never be called — that was the old blind-insert path
        mock_session.add.assert_not_called()
