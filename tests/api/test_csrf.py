"""CSRF enforcement contract tests (Chunk B Task 4)."""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.web.security.config import load_security_config
from src.web.security.csrf import issue_csrf_token
from src.web.security.middleware import (
    AuthorizationMiddleware,
    CsrfMiddleware,
    IdentityMiddleware,
    RequestIDMiddleware,
)
from src.web.security.route_manifest import (
    CsrfRequirement,
    RouteClassification,
    RouteManifestEntry,
)

pytestmark = pytest.mark.api

SECRET = "csrf-test-secret-key-long-enough-000000"


def _csrf_config():
    return load_security_config(
        {
            "APP_ENV": "development",
            "AUTH_MODE": "trusted_header",
            "TRUSTED_HOSTS": "localhost",
            "CORS_ALLOWED_ORIGINS": "http://localhost:8001",
            "AUTH_TRUSTED_PROXY_IPS": "10.0.0.1",
            "AUTH_ADMIN_GROUPS": "huntable-admins",
            "CSRF_ENABLED": "true",
            "SECRET_KEY": SECRET,
        }
    )


def _disabled_config():
    return load_security_config({"APP_ENV": "development", "AUTH_MODE": "disabled"})


def _app(config) -> FastAPI:
    app = FastAPI()

    @app.get("/api/private")
    async def private():
        return {"ok": True}

    @app.post("/api/admin")
    async def admin():
        return {"ok": True}

    @app.post("/api/service-hook")
    async def service_hook():
        return {"ok": True}

    app.state.route_manifest = [
        RouteManifestEntry(
            method="GET",
            path="/api/private",
            endpoint_name="private",
            route_module="test",
            classification=RouteClassification.AUTHENTICATED,
            csrf_requirement=CsrfRequirement.REQUIRED,
        ),
        RouteManifestEntry(
            method="POST",
            path="/api/admin",
            endpoint_name="admin",
            route_module="test",
            classification=RouteClassification.ROLES,
            roles=("admin",),
            csrf_requirement=CsrfRequirement.REQUIRED,
        ),
        RouteManifestEntry(
            method="POST",
            path="/api/service-hook",
            endpoint_name="service_hook",
            route_module="test",
            classification=RouteClassification.AUTHENTICATED,
            csrf_requirement=CsrfRequirement.SERVICE_ONLY,
        ),
    ]
    app.add_middleware(CsrfMiddleware, config=config)
    app.add_middleware(AuthorizationMiddleware, config=config)
    app.add_middleware(IdentityMiddleware, config=config)
    app.add_middleware(RequestIDMiddleware)
    return app


def _headers(groups="huntable-admins", **extra):
    h = {
        "X-Huntable-Verified": "true",
        "X-Huntable-User-Id": "u1",
        "X-Huntable-Email": "user@example.com",
        "X-Huntable-Groups": groups,
    }
    h.update(extra)
    return h


async def _client(app: FastAPI):
    transport = ASGITransport(app=app, client=("10.0.0.1", 1234))
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_safe_get_does_not_require_csrf():
    async with await _client(_app(_csrf_config())) as client:
        response = await client.get("/api/private", headers=_headers())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unsafe_post_without_token_is_rejected():
    async with await _client(_app(_csrf_config())) as client:
        response = await client.post("/api/admin", headers=_headers())
    assert response.status_code == 403
    assert "csrf" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_unsafe_post_with_valid_token_passes_csrf():
    token = issue_csrf_token(SECRET, "u1")
    async with await _client(_app(_csrf_config())) as client:
        response = await client.post("/api/admin", headers=_headers(**{"X-CSRF-Token": token}))
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unsafe_post_with_invalid_token_is_rejected():
    async with await _client(_app(_csrf_config())) as client:
        response = await client.post("/api/admin", headers=_headers(**{"X-CSRF-Token": "garbage"}))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_token_for_wrong_subject_is_rejected():
    token = issue_csrf_token(SECRET, "someone-else")
    async with await _client(_app(_csrf_config())) as client:
        response = await client.post("/api/admin", headers=_headers(**{"X-CSRF-Token": token}))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_service_only_route_does_not_require_csrf_token():
    async with await _client(_app(_csrf_config())) as client:
        response = await client.post("/api/service-hook", headers=_headers())
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_csrf_inactive_in_disabled_mode():
    async with await _client(_app(_disabled_config())) as client:
        response = await client.post("/api/admin")
    assert response.status_code == 200
