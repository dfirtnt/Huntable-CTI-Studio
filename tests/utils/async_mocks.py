"""Standardized async mock utilities for pytest tests."""

import pytest
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import asyncio


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


class AsyncMockFeedParser:
    """Mock async feed parser."""
    
    def __init__(self, **kwargs):
        self._mock = Mock(**kwargs)
        
        # Configure async methods
        self.parse_feed = AsyncMock()
        self.validate_feed = AsyncMock()
        self.extract_entries = AsyncMock()
        
        # Configure sync methods
        self.parse = Mock()
        self.validate = Mock()


def create_async_mock_response(
    text: str = "<html>Test content</html>",
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None
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
    tags: Optional[List[Dict[str, str]]] = None
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
    entries: Optional[List[Mock]] = None,
    bozo: bool = False,
    title: str = "Test Feed"
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
    published_at: Optional[datetime] = None
) -> Mock:
    """Create a mock article for testing."""
    
    article = Mock()
    article.source_id = source_id
    article.canonical_url = canonical_url
    article.title = title
    article.content = content
    article.published_at = published_at or datetime.utcnow()
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
    rss_url: str = "https://example.com/feed.xml"
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
