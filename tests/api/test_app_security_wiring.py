"""The real app loads a SecurityConfig and attaches X-Request-ID to responses."""

import httpx
import pytest


def test_app_exposes_security_config():
    from src.web.modern_main import SECURITY_CONFIG

    assert SECURITY_CONFIG.auth_mode.value in ("disabled", "trusted_header", "oidc")


@pytest.mark.api
@pytest.mark.asyncio
async def test_app_adds_request_id_header(async_client: httpx.AsyncClient):
    # A 404 path avoids any DB dependency; the middleware still stamps the header.
    response = await async_client.get("/api/__no_such_path__")
    assert response.status_code == 404
    assert response.headers.get("X-Request-ID")
