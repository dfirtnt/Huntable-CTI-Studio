"""Standardized async mock utilities for pytest tests."""

from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest


class AsyncMockSession:
    """Mock async database session with proper async context manager support."""

    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)
        self._async_mock = AsyncMock()

        # Configure async context manager methods
        self.__aenter__ = AsyncMock(return_value=self)
        self.__aexit__ = AsyncMock(return_value=None)

        # Configure common async methods
        self.execute = AsyncMock()
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.close = AsyncMock()
        self.query = Mock()
        self.add = Mock()
        self.delete = Mock()
        self.merge = Mock()
        self.flush = Mock()
        self.refresh = Mock()

        # Configure query methods
        self.query.return_value.filter = Mock(return_value=self.query.return_value)
        self.query.return_value.filter_by = Mock(return_value=self.query.return_value)
        self.query.return_value.first = Mock()
        self.query.return_value.all = Mock(return_value=[])
        self.query.return_value.count = Mock(return_value=0)
        self.query.return_value.limit = Mock(return_value=self.query.return_value)
        self.query.return_value.offset = Mock(return_value=self.query.return_value)
        self.query.return_value.order_by = Mock(return_value=self.query.return_value)


class AsyncMockHTTPClient:
    """Mock async HTTP client with proper async method support."""

    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)

        # Configure async methods
        self.get = AsyncMock()
        self.post = AsyncMock()
        self.put = AsyncMock()
        self.delete = AsyncMock()
        self.head = AsyncMock()
        self.options = AsyncMock()

        # Configure sync methods
        self.configure_source_robots = Mock()
        self.get_text_with_encoding_fallback = Mock(return_value="<html>Test content</html>")

        # Configure response methods
        self._setup_default_response()

    def _setup_default_response(self):
        """Setup default mock response."""
        mock_response = Mock()
        mock_response.text = "<html>Test content</html>"
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "text/html"}
        mock_response.raise_for_status = AsyncMock()
        mock_response.json = AsyncMock(return_value={})

        # Set as default return value for all HTTP methods
        self.get.return_value = mock_response
        self.post.return_value = mock_response
        self.put.return_value = mock_response
        self.delete.return_value = mock_response
        self.head.return_value = mock_response
        self.options.return_value = mock_response


class AsyncMockDeduplicationService:
    """Mock async deduplication service."""

    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)

        # Configure async methods
        self.check_duplicate = AsyncMock()
        self.find_duplicates = AsyncMock()
        self.process_articles = AsyncMock()
        self.get_similarity_stats = AsyncMock()

        # Configure sync methods
        self.compute_simhash = Mock()
        self.is_content_similar = Mock()


class AsyncMockContentProcessor:
    """Mock async content processor."""

    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)

        # Configure async methods
        self.process_articles = AsyncMock()
        self.process_batch = AsyncMock()
        self.enhance_content = AsyncMock()

        # Configure sync methods
        self.filter_quality = Mock()
        self.normalize_url = Mock()
        self.extract_metadata = Mock()


class AsyncMockDatabaseManager:
    """Mock async database manager with proper async context manager support."""

    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)
        self.engine = AsyncMock()
        self.AsyncSessionLocal = AsyncMock()

        # Configure async context manager for get_session()
        self.get_session = AsyncMock()
        self._session_mock = AsyncMockSession()
        self.get_session.return_value.__aenter__ = AsyncMock(return_value=self._session_mock)
        self.get_session.return_value.__aexit__ = AsyncMock(return_value=None)

        # Configure async methods
        self.create_tables = AsyncMock()
        self.get_database_stats = AsyncMock()
        self.create_source = AsyncMock()
        self.get_source_by_id = AsyncMock()
        self.update_source = AsyncMock()
        self.delete_source = AsyncMock()
        self.list_sources = AsyncMock()
        self.create_article = AsyncMock()
        self.get_article_by_id = AsyncMock()
        self.update_article = AsyncMock()
        self.delete_article = AsyncMock()
        self.list_articles = AsyncMock()
        self.create_annotation = AsyncMock()
        self.get_annotation_by_id = AsyncMock()
        self.update_annotation = AsyncMock()
        self.delete_annotation = AsyncMock()
        self.list_annotations = AsyncMock()

        # Configure engine methods
        self.engine.begin = AsyncMock()
        self.engine.begin.return_value.__aenter__ = AsyncMock(return_value=self.engine.begin.return_value)
        self.engine.begin.return_value.__aexit__ = AsyncMock(return_value=None)
        self.engine.connect = AsyncMock()
        self.engine.dispose = AsyncMock()


class AsyncMockFeedParser:
    """Mock async feed parser with proper feedparser response structure."""

    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)

        # Configure async methods
        self.parse_feed = AsyncMock()
        self.validate_feed = AsyncMock()
        self.extract_entries = AsyncMock()

        # Configure sync methods (feedparser.parse() is sync)
        self.parse = Mock()
        self.validate = Mock()

        # Configure default parse response structure
        self._setup_default_parse_response()

    def _setup_default_parse_response(self):
        """Setup default feedparser.parse() response structure."""
        mock_feed_data = Mock()
        mock_feed_data.bozo = False
        mock_feed_data.bozo_exception = None
        mock_feed_data.entries = []
        mock_feed_data.feed = Mock()
        mock_feed_data.feed.title = "Test Feed"
        mock_feed_data.feed.link = "https://example.com"
        mock_feed_data.feed.description = "Test feed description"
        mock_feed_data.feed.language = "en"

        self.parse.return_value = mock_feed_data


class AsyncMockBeautifulSoup:
    """Mock BeautifulSoup for HTML parsing."""

    def __init__(self, html_content: str = "<html><body>Test</body></html>", **kwargs):
        self._mock = Mock(**kwargs)
        self.html_content = html_content

        # Configure BeautifulSoup-like methods
        self.find = Mock()
        self.find_all = Mock(return_value=[])
        self.select = Mock(return_value=[])
        self.select_one = Mock(return_value=None)
        self.get_text = Mock(return_value="Test content")
        self.prettify = Mock(return_value=html_content)

        # Configure JSON-LD extraction
        self.find_all.return_value = []

        # Setup default find behavior
        self._setup_default_find()

    def _setup_default_find(self):
        """Setup default find() behavior."""
        # Mock common tag finds
        mock_tag = Mock()
        mock_tag.get_text.return_value = "Test content"
        mock_tag.get.return_value = None
        mock_tag.attrs = {}

        self.find.return_value = mock_tag
        self.select_one.return_value = mock_tag


def create_async_mock_response(
    text: str = "<html>Test content</html>",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    json_data: dict[str, Any] | None = None,
) -> Mock:
    """Create a mock HTTP response with async support."""
    mock_response = Mock()
    mock_response.text = text
    mock_response.status_code = status_code
    mock_response.headers = headers or {"content-type": "text/html"}
    mock_response.raise_for_status = Mock()
    mock_response.json = Mock(return_value=json_data or {})
    return mock_response


def create_async_mock_feed_entry(
    title: str = "Test Article",
    link: str = "https://example.com/article",
    published: str = "2024-01-01T12:00:00Z",
    description: str = "<p>Test content</p>",
    author: str = "Test Author",
    tags: list[dict[str, str]] | None = None,
) -> Mock:
    """Create a mock RSS feed entry with proper date parsing."""
    entry = Mock()
    entry.title = title
    entry.link = link
    entry.id = link
    entry.published = published
    entry.description = description
    entry.summary = description
    entry.author = author
    entry.tags = tags or [{"term": "security"}]
    entry.content = None

    # Mock parsed date objects
    parsed_date = Mock()
    parsed_date.tm_year = 2024
    parsed_date.tm_mon = 1
    parsed_date.tm_mday = 1
    parsed_date.tm_hour = 12
    parsed_date.tm_min = 0
    parsed_date.tm_sec = 0
    parsed_date.tm_isdst = -1

    entry.published_parsed = parsed_date
    entry.updated_parsed = parsed_date
    entry.get = Mock(return_value=None)

    return entry


def create_async_mock_feed_data(
    entries: list[Mock] | None = None, bozo: bool = False, title: str = "Test Feed"
) -> Mock:
    """Create mock feedparser data structure."""
    mock_feed_data = Mock()
    mock_feed_data.bozo = bozo
    mock_feed_data.entries = entries or []
    mock_feed_data.feed = Mock()
    mock_feed_data.feed.title = title
    mock_feed_data.feed.link = "https://example.com"
    mock_feed_data.feed.description = "Test feed description"
    return mock_feed_data


def create_async_mock_article(
    source_id: int = 1,
    canonical_url: str = "https://example.com/article",
    title: str = "Test Article",
    content: str = "<p>Test content</p>",
    published_at: datetime | None = None,
) -> Mock:
    """Create a mock article for testing."""

    article = Mock()
    article.source_id = source_id
    article.canonical_url = canonical_url
    article.title = title
    article.content = content
    article.published_at = published_at or datetime.now()
    article.summary = "Test summary"
    article.authors = ["Test Author"]
    article.tags = ["security"]
    article.article_metadata = {}
    article.content_hash = "test_hash_123"
    return article


def create_async_mock_source(
    identifier: str = "test-source",
    name: str = "Test Source",
    url: str = "https://example.com",
    rss_url: str = "https://example.com/feed.xml",
) -> Mock:
    """Create a mock source for testing."""
    source = Mock()
    source.id = 1
    source.identifier = identifier
    source.name = name
    source.url = url
    source.rss_url = rss_url
    source.check_frequency = 3600
    source.lookback_days = 180
    source.active = True
    source.config = {}
    return source


# Common async mock fixtures
@pytest.fixture
def async_mock_session():
    """Fixture for async database session mock."""
    return AsyncMockSession()


@pytest.fixture
def async_mock_http_client():
    """Fixture for async HTTP client mock."""
    return AsyncMockHTTPClient()


@pytest.fixture
def async_mock_deduplication_service():
    """Fixture for async deduplication service mock."""
    return AsyncMockDeduplicationService()


@pytest.fixture
def async_mock_content_processor():
    """Fixture for async content processor mock."""
    return AsyncMockContentProcessor()


@pytest.fixture
def async_mock_feed_parser():
    """Fixture for async feed parser mock."""
    return AsyncMockFeedParser()


@pytest.fixture
def async_mock_database_manager():
    """Fixture for async database manager mock."""
    return AsyncMockDatabaseManager()


@pytest.fixture
def async_mock_beautiful_soup():
    """Fixture for BeautifulSoup mock."""
    return AsyncMockBeautifulSoup()


# Utility functions for common async mock patterns
def mock_async_method(mock_obj, method_name: str, return_value: Any = None, side_effect: Any = None):
    """Helper to mock an async method on an object."""
    async_mock = AsyncMock()
    if return_value is not None:
        async_mock.return_value = return_value
    if side_effect is not None:
        async_mock.side_effect = side_effect
    setattr(mock_obj, method_name, async_mock)
    return async_mock


def mock_async_context_manager(mock_obj, return_value: Any = None):
    """Helper to mock async context manager methods."""
    if return_value is None:
        return_value = mock_obj

    mock_obj.__aenter__ = AsyncMock(return_value=return_value)
    mock_obj.__aexit__ = AsyncMock(return_value=None)
    return mock_obj


def create_async_mock_with_context_manager(**kwargs):
    """Create a mock object with async context manager support."""
    mock_obj = Mock(**kwargs)
    return mock_async_context_manager(mock_obj)


def setup_query_chain(mock_query, return_value=None):
    """
    Setup a mock query chain (filter, order_by, limit, offset, etc.).

    Args:
        mock_query: Mock query object
        return_value: Value to return from final query methods (first, all, count, etc.)

    Returns:
        Configured mock query object
    """
    if return_value is None:
        return_value = []

    # Make query chainable
    mock_query.filter = Mock(return_value=mock_query)
    mock_query.filter_by = Mock(return_value=mock_query)
    mock_query.order_by = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    mock_query.offset = Mock(return_value=mock_query)
    mock_query.join = Mock(return_value=mock_query)
    mock_query.outerjoin = Mock(return_value=mock_query)

    # Configure final methods
    if isinstance(return_value, list):
        mock_query.all = Mock(return_value=return_value)
        mock_query.first = Mock(return_value=return_value[0] if return_value else None)
        mock_query.count = Mock(return_value=len(return_value))
    elif isinstance(return_value, int):
        mock_query.count = Mock(return_value=return_value)
        mock_query.first = Mock(return_value=None)
        mock_query.all = Mock(return_value=[])
    else:
        mock_query.first = Mock(return_value=return_value)
        mock_query.all = Mock(return_value=[return_value] if return_value else [])
        mock_query.count = Mock(return_value=1 if return_value else 0)

    return mock_query


def setup_async_query_chain(mock_query, return_value=None):
    """
    Setup an async mock query chain with AsyncMock methods.

    Args:
        mock_query: Mock query object
        return_value: Value to return from final query methods

    Returns:
        Configured mock query object
    """
    if return_value is None:
        return_value = []

    # Make query chainable
    mock_query.filter = Mock(return_value=mock_query)
    mock_query.filter_by = Mock(return_value=mock_query)
    mock_query.order_by = Mock(return_value=mock_query)
    mock_query.limit = Mock(return_value=mock_query)
    mock_query.offset = Mock(return_value=mock_query)
    mock_query.join = Mock(return_value=mock_query)
    mock_query.outerjoin = Mock(return_value=mock_query)

    # Configure async final methods
    if isinstance(return_value, list):
        mock_query.all = AsyncMock(return_value=return_value)
        mock_query.first = AsyncMock(return_value=return_value[0] if return_value else None)
        mock_query.count = AsyncMock(return_value=len(return_value))
    elif isinstance(return_value, int):
        mock_query.count = AsyncMock(return_value=return_value)
        mock_query.first = AsyncMock(return_value=None)
        mock_query.all = AsyncMock(return_value=[])
    else:
        mock_query.first = AsyncMock(return_value=return_value)
        mock_query.all = AsyncMock(return_value=[return_value] if return_value else [])
        mock_query.count = AsyncMock(return_value=1 if return_value else 0)

    return mock_query


def setup_transaction_mock(mock_session):
    """
    Setup transaction handling mocks for async session.

    Args:
        mock_session: Mock async session

    Returns:
        Configured mock session
    """
    # Transaction methods
    mock_session.begin = AsyncMock()
    mock_session.begin.return_value.__aenter__ = AsyncMock(return_value=mock_session.begin.return_value)
    mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

    # Commit and rollback
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.flush = AsyncMock()

    return mock_session


def create_time_struct_time(year=2024, month=1, day=1, hour=12, minute=0, second=0):
    """
    Create a mock time.struct_time object for date parsing.

    Args:
        year, month, day, hour, minute, second: Time components

    Returns:
        Mock struct_time object
    """
    parsed_date = Mock()
    parsed_date.tm_year = year
    parsed_date.tm_mon = month
    parsed_date.tm_mday = day
    parsed_date.tm_hour = hour
    parsed_date.tm_min = minute
    parsed_date.tm_sec = second
    parsed_date.tm_wday = 0  # Monday
    parsed_date.tm_yday = 1
    parsed_date.tm_isdst = -1
    return parsed_date
