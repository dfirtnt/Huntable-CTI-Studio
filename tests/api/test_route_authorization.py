import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.web.security.config import load_security_config
from src.web.security.middleware import AuthorizationMiddleware, IdentityMiddleware, RequestIDMiddleware
from src.web.security.route_manifest import (
    RouteClassification,
    RouteManifestEntry,
)

pytestmark = pytest.mark.api


def _trusted_header_config():
    return load_security_config(
        {
            "APP_ENV": "development",
            "AUTH_MODE": "trusted_header",
            "TRUSTED_HOSTS": "localhost",
            "CORS_ALLOWED_ORIGINS": "http://localhost:8001",
            "AUTH_TRUSTED_PROXY_IPS": "10.0.0.1",
            "AUTH_ADMIN_GROUPS": "huntable-admins",
            "AUTH_OPERATOR_GROUPS": "huntable-operators",
        }
    )


def _disabled_config():
    return load_security_config({"APP_ENV": "development", "AUTH_MODE": "disabled"})


def _app(config) -> FastAPI:
    app = FastAPI()

    @app.get("/api/public")
    async def public():
        return {"ok": True}

    @app.get("/api/private")
    async def private():
        return {"ok": True}

    @app.post("/api/admin")
    async def admin():
        return {"ok": True}

    @app.post("/api/operator")
    async def operator():
        return {"ok": True}

    @app.post("/api/unclassified")
    async def unclassified():
        return {"ok": True}

    app.state.route_manifest = [
        RouteManifestEntry(
            method="GET",
            path="/api/public",
            endpoint_name="public",
            route_module="test",
            classification=RouteClassification.PUBLIC,
        ),
        RouteManifestEntry(
            method="GET",
            path="/api/private",
            endpoint_name="private",
            route_module="test",
            classification=RouteClassification.AUTHENTICATED,
        ),
        RouteManifestEntry(
            method="POST",
            path="/api/admin",
            endpoint_name="admin",
            route_module="test",
            classification=RouteClassification.ROLES,
            roles=("admin",),
        ),
        RouteManifestEntry(
            method="POST",
            path="/api/operator",
            endpoint_name="operator",
            route_module="test",
            classification=RouteClassification.ROLES,
            roles=("operator", "admin"),
        ),
    ]
    app.add_middleware(AuthorizationMiddleware, config=config)
    app.add_middleware(IdentityMiddleware, config=config)
    app.add_middleware(RequestIDMiddleware)
    return app


def _headers(groups: str = "huntable-admins") -> dict[str, str]:
    return {
        "X-Huntable-Verified": "true",
        "X-Huntable-User-Id": "u1",
        "X-Huntable-Email": "user@example.com",
        "X-Huntable-Groups": groups,
    }


async def _client(app: FastAPI):
    transport = ASGITransport(app=app, client=("10.0.0.1", 1234))
    return AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_public_route_allows_unauthenticated_request():
    async with await _client(_app(_trusted_header_config())) as client:
        response = await client.get("/api/public")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_private_route_requires_authenticated_identity_when_auth_enabled():
    async with await _client(_app(_trusted_header_config())) as client:
        response = await client.get("/api/private")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"
    assert response.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_trusted_identity_can_access_authenticated_route():
    async with await _client(_app(_trusted_header_config())) as client:
        response = await client.get("/api/private", headers=_headers())

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_role_route_rejects_authenticated_identity_without_required_role():
    async with await _client(_app(_trusted_header_config())) as client:
        response = await client.post("/api/admin", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_admin_role_satisfies_operator_route():
    async with await _client(_app(_trusted_header_config())) as client:
        response = await client.post("/api/operator", headers=_headers("huntable-admins"))

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unclassified_unsafe_route_fails_closed_when_auth_enabled():
    async with await _client(_app(_trusted_header_config())) as client:
        response = await client.post("/api/unclassified", headers=_headers("huntable-admins"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Route is not classified for unsafe access"


@pytest.mark.asyncio
async def test_disabled_auth_mode_keeps_local_dev_compatible():
    async with await _client(_app(_disabled_config())) as client:
        response = await client.post("/api/admin")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]
