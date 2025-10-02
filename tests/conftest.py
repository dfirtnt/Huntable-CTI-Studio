"""
Test configuration and fixtures for CTI Scraper tests.
"""
import os
import pytest
import pytest_asyncio
import httpx
from typing import AsyncGenerator


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
