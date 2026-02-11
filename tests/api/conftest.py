"""
API test configuration. Session-scoped event loop and client when using
in-process ASGI app so async_db_manager stays on one loop.
"""

import asyncio
import os

import httpx
import pytest_asyncio


@pytest_asyncio.fixture(scope="session")
def event_loop():
    """One event loop for all API tests (required when USE_ASGI_CLIENT=1)."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def async_client():
    """Session-scoped HTTP client so in-process app's async_db_manager stays on one loop."""
    use_asgi = os.getenv("USE_ASGI_CLIENT", "").lower() in ("1", "true", "yes")
    if use_asgi:
        from httpx import ASGITransport

        from src.web.modern_main import app

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=httpx.Timeout(60.0))
    else:
        port = int(os.getenv("TEST_PORT", "8001"))
        client = httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=httpx.Timeout(60.0))
    try:
        yield client
    finally:
        await client.aclose()
