"""
Test configuration and fixtures for CTI Scraper tests.
"""
import os
import pytest
import pytest_asyncio
import httpx
from typing import AsyncGenerator
from playwright.sync_api import sync_playwright
from unittest.mock import AsyncMock, MagicMock


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API testing."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    timeout = httpx.Timeout(60.0)  # Increased timeout for RAG operations
    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
        yield client


@pytest.fixture
def api_headers():
    """Default API headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


# Async Mock Fixtures for Database and Service Testing
@pytest.fixture
def mock_async_session():
    """Create a properly configured async database session mock."""
    session = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.close = AsyncMock()
    session.add = MagicMock()
    session.delete = MagicMock()
    session.merge = MagicMock()
    session.refresh = AsyncMock()
    session.scalar = AsyncMock()
    session.scalars = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def mock_async_engine():
    """Create a properly configured async database engine mock."""
    engine = AsyncMock()
    engine.begin = AsyncMock()
    engine.__aenter__ = AsyncMock(return_value=engine)
    engine.__aexit__ = AsyncMock(return_value=None)
    engine.connect = AsyncMock()
    engine.dispose = AsyncMock()
    return engine


@pytest.fixture
def mock_async_http_client():
    """Create a properly configured async HTTP client mock."""
    client = AsyncMock()
    client.get = AsyncMock()
    client.post = AsyncMock()
    client.put = AsyncMock()
    client.delete = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_async_deduplication_service():
    """Create a properly configured async deduplication service mock."""
    service = AsyncMock()
    service.check_duplicate = AsyncMock()
    service.add_content_hash = AsyncMock()
    service.get_similar_content = AsyncMock()
    service.cleanup_old_hashes = AsyncMock()
    return service


# Playwright fixtures for UI testing
@pytest.fixture(scope="session")
def browser_context_args():
    """Browser context arguments for Playwright tests"""
    return {
        "viewport": {"width": 1280, "height": 720},
        "ignore_https_errors": True,
        "record_video_dir": "test-results/videos/",
        "record_video_size": {"width": 1280, "height": 720},
    }

@pytest.fixture(scope="session")
def browser_type_launch_args():
    """Browser launch arguments"""
    return {
        "headless": True,
        "slow_mo": 100,  # Slow down actions for better debugging
    }

@pytest.fixture(scope="session")
def playwright_context():
    """Playwright context for session-scoped tests"""
    with sync_playwright() as p:
        yield p

@pytest.fixture(scope="session")
def browser(playwright_context):
    """Browser instance for session-scoped tests"""
    browser = playwright_context.chromium.launch(headless=True)
    yield browser
    browser.close()

@pytest.fixture(scope="session")
def context(browser):
    """Browser context for session-scoped tests"""
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True,
        record_video_dir="test-results/videos/",
    )
    yield context
    context.close()

@pytest.fixture
def page(context):
    """Page instance for each test"""
    page = context.new_page()
    yield page
    page.close()


def pytest_configure(config):
    """Register custom markers to satisfy strict marker checks."""
    config.addinivalue_line("markers", "ui: UI tests")
    config.addinivalue_line("markers", "ai: AI assistant and summarization tests")
