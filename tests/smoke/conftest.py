"""
Smoke test configuration and utilities for CTI Scraper.

This module provides shared fixtures and utilities for smoke tests.
"""

from collections.abc import AsyncGenerator

import httpx
import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """Async HTTP client fixture for smoke tests."""
    base_url = "http://localhost:8001"

    client = httpx.AsyncClient(base_url=base_url, timeout=httpx.Timeout(10.0), follow_redirects=True)
    try:
        yield client
    finally:
        # Manually close the client to avoid event loop closure issues
        try:
            await client.aclose()
        except RuntimeError:
            # Event loop already closed, ignore
            pass


@pytest.fixture
def smoke_test_timeout():
    """Timeout for smoke tests (30 seconds total)."""
    return 30


class SmokeTestHelper:
    """Helper class for smoke test utilities."""

    @staticmethod
    async def verify_endpoint_health(client: httpx.AsyncClient, endpoint: str) -> bool:
        """Verify an endpoint is healthy."""
        try:
            response = await client.get(endpoint)
            return response.status_code == 200
        except Exception:
            return False

    @staticmethod
    async def verify_api_response_structure(client: httpx.AsyncClient, endpoint: str, expected_keys: list) -> bool:
        """Verify API response has expected structure."""
        try:
            response = await client.get(endpoint)
            if response.status_code != 200:
                return False

            data = response.json()
            return all(key in data for key in expected_keys)
        except Exception:
            return False

    @staticmethod
    async def measure_response_time(client: httpx.AsyncClient, endpoint: str) -> float:
        """Measure response time for an endpoint."""
        import time

        start_time = time.time()
        await client.get(endpoint)
        return time.time() - start_time
