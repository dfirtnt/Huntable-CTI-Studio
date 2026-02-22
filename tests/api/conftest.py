"""
API test configuration. Session-scoped event loop and client only when
USE_ASGI_CLIENT=1 so in-process app's async_db_manager stays on one loop.
When USE_ASGI_CLIENT is not set (e.g. smoke), root conftest's function-scoped
fixtures are used so smoke and live-server runs keep passing.
"""

import asyncio
import os

import httpx
import pytest_asyncio


def _use_asgi_client() -> bool:
    return os.getenv("USE_ASGI_CLIENT", "").lower() in ("1", "true", "yes")


# Only override with session-scoped fixtures when using in-process ASGI client.
# Otherwise smoke and other runs use root conftest (function-scoped) and avoid
# "Event loop is closed" from mixing session loop with default function-scoped test loop.
if _use_asgi_client():

    @pytest_asyncio.fixture(scope="session")
    def event_loop():
        """One event loop for all API tests (required when USE_ASGI_CLIENT=1)."""
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    @pytest_asyncio.fixture(scope="session")
    async def async_client(ensure_workflow_config_schema):
        """Session-scoped HTTP client when USE_ASGI_CLIENT=1."""
        from httpx import ASGITransport

        from src.web.modern_main import app

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        client = httpx.AsyncClient(transport=transport, base_url="http://testserver", timeout=httpx.Timeout(60.0))
        try:
            yield client
        finally:
            await client.aclose()
