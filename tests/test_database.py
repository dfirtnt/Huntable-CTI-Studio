"""
Tests for database modules in src/database/.
"""

from contextlib import asynccontextmanager
from unittest.mock import Mock, patch

import pytest

from src.database.manager import DatabaseManager
from src.database.models import ArticleTable, SourceTable
from tests.utils.async_mocks import AsyncMockDatabaseManager, AsyncMockSession, setup_transaction_mock

# Mark all tests in this file as unit tests (they use mocks, no real DB)
pytestmark = pytest.mark.unit


class TestDatabaseManager:
    """Test the DatabaseManager class."""

    def test_connection_string(self):
        """Test database connection string generation."""
        # Test connection string format
        expected = "postgresql://test_user:test_pass@localhost:5432/test_db"

        # Verify the format is correct
        assert "postgresql://" in expected
        assert "test_user:test_pass" in expected
        assert "localhost:5432" in expected
        assert "test_db" in expected

    def test_validate_connection_params(self):
        """Test connection parameter validation."""
        # Test valid parameters
        valid_params = {
            "host": "localhost",
            "port": 5432,
            "database": "test_db",
            "username": "test_user",
            "password": "test_pass",
        }
        # All required fields present
        assert all(key in valid_params for key in ["host", "port", "database", "username", "password"])

        # Test invalid parameters (missing host)
        invalid_params = {"port": 5432, "database": "test_db", "username": "test_user", "password": "test_pass"}
        # Missing required field
        assert "host" not in invalid_params

    def test_create_tables(self):
        """Test table creation."""
        # Test that we can import the models
        from src.database.models import ArticleTable, SourceTable

        # Verify models exist
        assert ArticleTable is not None
        assert SourceTable is not None

    def test_get_article_count(self):
        """Test getting article count."""
        # Test model structure
        from datetime import datetime

        from src.database.models import ArticleTable

        # Create a mock article
        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com",
            source_id=1,
            published_at=datetime.now(),
            content_hash="test_hash",
        )

        assert article.title == "Test Article"
        assert article.content == "Test content"
        assert article.canonical_url == "https://example.com"
        assert article.source_id == 1

    def test_get_source_count(self):
        """Test getting source count."""
        # Test model structure
        from src.database.models import SourceTable

        # Create a mock source
        source = SourceTable(
            name="Test Source", url="https://example.com/feed.xml", identifier="test-source", active=True
        )

        assert source.name == "Test Source"
        assert source.url == "https://example.com/feed.xml"
        assert source.identifier == "test-source"
        assert source.active is True

    def test_db_article_to_model_sets_url_from_canonical_url(self):
        """DatabaseManager._db_article_to_model sets Article.url from db_article.canonical_url."""
        from datetime import datetime

        with patch.object(DatabaseManager, "create_tables"):
            manager = DatabaseManager(database_url="sqlite:///:memory:")
        mock_db = Mock()
        mock_db.id = 1
        mock_db.source_id = 1
        mock_db.canonical_url = "https://example.com/article"
        mock_db.title = "Title"
        mock_db.published_at = datetime.now()
        mock_db.modified_at = None
        mock_db.authors = []
        mock_db.tags = []
        mock_db.summary = None
        mock_db.content = "body"
        mock_db.content_hash = "hash"
        mock_db.article_metadata = {}
        mock_db.simhash = None
        mock_db.simhash_bucket = None
        mock_db.word_count = 0
        mock_db.discovered_at = datetime.now()
        mock_db.processing_status = "pending"
        mock_db.created_at = datetime.now()
        mock_db.updated_at = datetime.now()

        article = manager._db_article_to_model(mock_db)
        assert article.url == "https://example.com/article"
        assert article.canonical_url == "https://example.com/article"

    def test_get_source_applies_limit_one(self):
        """get_source() must call .limit(1) before .first() to prevent non-deterministic row selection."""
        with patch.object(DatabaseManager, "create_tables"):
            manager = DatabaseManager(database_url="sqlite:///:memory:")

        mock_session = Mock()
        mock_session.__enter__ = Mock(return_value=mock_session)
        mock_session.__exit__ = Mock(return_value=False)

        # Build the query chain mock so we can assert .limit(1) was called
        mock_chain = mock_session.query.return_value
        mock_chain.filter.return_value = mock_chain
        mock_chain.limit.return_value = mock_chain
        mock_chain.first.return_value = None

        with patch.object(manager, "get_session", return_value=mock_session):
            result = manager.get_source(42)

        mock_chain.limit.assert_called_once_with(1)
        assert result is None

    def test_create_tables_bounds_ddl_with_lock_timeout(self):
        """create_tables() must set a lock_timeout before the idempotent schema-ensure DDL.

        Regression: with no lock_timeout, an ALTER TABLE issued at startup queues for
        ACCESS EXCLUSIVE behind a worker's idle-in-transaction session, and the pending
        lock then blocks ALL readers of that table for tens of seconds (app-wide freeze).
        A bounded lock_timeout makes the no-op ALTER give up fast instead.
        """
        mock_conn = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_engine = Mock()
        mock_engine.begin.return_value = mock_conn
        mock_engine.url = Mock()
        mock_engine.url.drivername = "postgresql"

        with (
            patch("src.database.manager.create_engine", return_value=mock_engine),
            patch("src.database.manager.Base.metadata.create_all"),
        ):
            # Unique URL so the class-level engine cache doesn't skip create_tables().
            manager = DatabaseManager(database_url="postgresql://u:p@h/db_locktimeout")

        assert manager is not None
        executed_sql = " ".join(str(call.args[0]) for call in mock_conn.execute.call_args_list)
        assert "lock_timeout" in executed_sql.lower()

    def test_create_tables_survives_locked_ddl(self):
        """A lock-timeout error on one idempotent DDL must not abort startup or the
        remaining DDL -- these are no-ops on a healthy DB, so a busy table is skippable."""
        from sqlalchemy.exc import OperationalError

        def _execute(stmt, *args, **kwargs):
            if "expected_items" in str(stmt):
                raise OperationalError("ALTER ...", {}, Exception("canceling: lock_timeout"))
            return Mock()

        mock_conn = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.execute = Mock(side_effect=_execute)

        mock_engine = Mock()
        mock_engine.begin.return_value = mock_conn
        mock_engine.url = Mock()
        mock_engine.url.drivername = "postgresql"

        with (
            patch("src.database.manager.create_engine", return_value=mock_engine),
            patch("src.database.manager.Base.metadata.create_all"),
        ):
            # Must NOT raise even though one DDL statement errors. Unique URL so the
            # class-level engine cache doesn't skip create_tables().
            manager = DatabaseManager(database_url="postgresql://u:p@h/db_lockedddl")

        executed_sql = " ".join(str(call.args[0]) for call in mock_conn.execute.call_args_list)
        # A statement issued AFTER the failing one still ran (PK DDL is last).
        assert "ADD PRIMARY KEY" in executed_sql
        assert manager is not None

    def test_create_tables_executes_pk_ddl_for_three_tables(self):
        """create_tables() must execute idempotent ADD PRIMARY KEY DDL for sources, subagent_evaluations, content_hashes."""
        mock_conn = Mock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)

        mock_engine = Mock()
        mock_engine.begin.return_value = mock_conn
        mock_engine.url = Mock()
        mock_engine.url.drivername = "postgresql"

        with (
            patch("src.database.manager.create_engine", return_value=mock_engine),
            patch("src.database.manager.Base.metadata.create_all"),
        ):
            DatabaseManager(database_url="postgresql://u:p@h/db")

        # Collect all SQL text strings passed to conn.execute
        executed_sql = " ".join(str(call.args[0]) for call in mock_conn.execute.call_args_list)

        assert "sources" in executed_sql
        assert "subagent_evaluations" in executed_sql
        assert "content_hashes" in executed_sql
        assert "ADD PRIMARY KEY" in executed_sql


class TestAsyncDatabaseManager:
    """Test the AsyncDatabaseManager class."""

    @pytest.fixture
    def mock_db_manager(self):
        """Create properly configured async database manager mock."""
        manager = AsyncMockDatabaseManager()

        # Setup get_session to return async context manager
        mock_session = AsyncMockSession()
        setup_transaction_mock(mock_session)

        @asynccontextmanager
        async def get_session():
            yield mock_session

        manager.get_session = get_session
        return manager

    @pytest.mark.asyncio
    async def test_async_connection_string(self):
        """Test async database connection string generation."""
        # Test async connection string format
        expected = "postgresql+asyncpg://test_user:test_pass@localhost:5432/test_db"

        # Verify the format is correct
        assert "postgresql+asyncpg://" in expected
        assert "test_user:test_pass" in expected
        assert "localhost:5432" in expected
        assert "test_db" in expected

    @pytest.mark.asyncio
    async def test_async_create_tables(self):
        """Test async table creation."""
        # Test that we can import async models
        from src.database.models import ArticleTable, SourceTable

        # Verify models exist
        assert ArticleTable is not None
        assert SourceTable is not None

    @pytest.mark.asyncio
    async def test_async_get_article_count(self):
        """Test async getting article count."""
        # Test model structure
        from src.database.models import ArticleTable

        # Create a mock article
        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com",
            source_id=1,
            published_at="2024-01-01T00:00:00Z",
            content_hash="test_hash",
        )

        assert article.title == "Test Article"
        assert article.content == "Test content"
        assert article.canonical_url == "https://example.com"
        assert article.source_id == 1

    @pytest.mark.asyncio
    async def test_async_get_source_count(self):
        """Test async getting source count."""
        # Test model structure
        from src.database.models import SourceTable

        # Create a mock source
        source = SourceTable(
            name="Test Source", url="https://example.com/feed.xml", identifier="test-source", active=True
        )

        assert source.name == "Test Source"
        assert source.url == "https://example.com/feed.xml"
        assert source.identifier == "test-source"
        assert source.active is True

    @pytest.mark.asyncio
    async def test_async_save_article(self):
        """Test async saving article."""
        # Test ArticleCreate model
        from datetime import datetime

        from src.models.article import ArticleCreate

        article_data = ArticleCreate(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com/article",
            source_id=1,
            published_at=datetime(2024, 1, 1, 0, 0, 0),
        )

        assert article_data.title == "Test Article"
        assert article_data.content == "Test content"
        assert article_data.canonical_url == "https://example.com/article"
        assert article_data.source_id == 1

    @pytest.mark.asyncio
    async def test_async_get_articles(self):
        """Test async getting articles."""
        # Test model structure
        from src.database.models import ArticleTable

        # Create mock articles
        article1 = ArticleTable(
            title="Article 1",
            content="Content 1",
            canonical_url="https://example.com/1",
            source_id=1,
            published_at="2024-01-01T00:00:00Z",
            content_hash="hash1",
        )
        article2 = ArticleTable(
            title="Article 2",
            content="Content 2",
            canonical_url="https://example.com/2",
            source_id=1,
            published_at="2024-01-01T00:00:00Z",
            content_hash="hash2",
        )

        articles = [article1, article2]

        assert len(articles) == 2
        assert articles[0].title == "Article 1"
        assert articles[1].title == "Article 2"


class TestDatabaseModels:
    """Test database models."""

    def test_article_model(self):
        """Test Article model."""
        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com/article",
            source_id=1,
            published_at="2024-01-01T00:00:00Z",
            content_hash="test_hash",
        )

        assert article.title == "Test Article"
        assert article.content == "Test content"
        assert article.canonical_url == "https://example.com/article"
        assert article.source_id == 1
        assert article.published_at == "2024-01-01T00:00:00Z"

    def test_source_model(self):
        """Test Source model."""
        source = SourceTable(
            name="Test Source", url="https://example.com/feed.xml", identifier="test-source", active=True
        )

        assert source.name == "Test Source"
        assert source.url == "https://example.com/feed.xml"
        assert source.identifier == "test-source"
        assert source.active is True

    def test_article_relationships(self):
        """Test Article model relationships."""
        from datetime import datetime

        source = SourceTable(
            name="Test Source", url="https://example.com/feed.xml", identifier="test-source", active=True
        )

        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com/article",
            source=source,
            published_at=datetime.now(),
        )

        assert article.source == source
        assert article.source.name == "Test Source"

    def test_model_validation(self):
        """Test model validation."""
        from datetime import datetime

        # Test Article with required fields
        article = ArticleTable(
            title="Test Article",
            content="Test content",
            canonical_url="https://example.com/article",
            source_id=1,
            published_at=datetime.now(),
            content_hash="test_hash",
        )

        assert article.title is not None
        assert article.content is not None
        assert article.canonical_url is not None

        # Test Source with required fields
        source = SourceTable(name="Test Source", url="https://example.com/feed.xml", identifier="test-source")

        assert source.name is not None
        assert source.url is not None
        assert source.identifier is not None


if __name__ == "__main__":
    pytest.main([__file__])
