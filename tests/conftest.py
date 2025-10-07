"""
Test configuration and fixtures for CTI Scraper tests.
"""
import os
import pytest
import pytest_asyncio
import httpx
from typing import AsyncGenerator
from playwright.sync_api import sync_playwright


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client for API testing."""
    base_url = os.getenv("CTI_SCRAPER_URL", "http://localhost:8001")
    async with httpx.AsyncClient(base_url=base_url) as client:
        yield client


@pytest.fixture
def api_headers():
    """Default API headers."""
    return {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


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
