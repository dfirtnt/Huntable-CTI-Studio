import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.web.routes import register_routes
from src.web.security.config import load_security_config
from src.web.security.middleware import AuthorizationMiddleware, IdentityMiddleware, RequestIDMiddleware
from src.web.security.route_manifest import build_route_manifest, validate_route_manifest

pytestmark = pytest.mark.api


def _config():
    return load_security_config(
        {
            "APP_ENV": "development",
            "AUTH_MODE": "trusted_header",
            "TRUSTED_HOSTS": "localhost",
            "CORS_ALLOWED_ORIGINS": "http://localhost:8001",
            "AUTH_TRUSTED_PROXY_IPS": "10.0.0.1",
            "AUTH_ADMIN_GROUPS": "huntable-admins",
            "AUTH_OPERATOR_GROUPS": "huntable-operators",
            "AUTH_REVIEWER_GROUPS": "huntable-reviewers",
            "AUTH_ANALYST_GROUPS": "huntable-analysts",
        }
    )


def _app() -> FastAPI:
    config = _config()
    app = FastAPI()
    register_routes(app)
    app.state.route_manifest = build_route_manifest(app)
    validate_route_manifest(app, config)
    app.add_middleware(AuthorizationMiddleware, config=config)
    app.add_middleware(IdentityMiddleware, config=config)
    app.add_middleware(RequestIDMiddleware)
    return app


def _headers(groups: str) -> dict[str, str]:
    return {
        "X-Huntable-Verified": "true",
        "X-Huntable-User-Id": "u1",
        "X-Huntable-Email": "user@example.com",
        "X-Huntable-Groups": groups,
    }


async def _client():
    return AsyncClient(
        transport=ASGITransport(app=_app(), client=("10.0.0.1", 1234)),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_backup_create_requires_admin_before_handler_runs():
    async with await _client() as client:
        response = await client.post("/api/backup/create", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_cron_replace_rejects_unauthenticated_request():
    async with await _client() as client:
        response = await client.put("/api/cron", json={"content": ""})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_source_collect_rejects_unauthenticated_request():
    async with await _client() as client:
        response = await client.post("/api/sources/1/collect")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_sigma_approval_requires_rule_reviewer_or_admin():
    async with await _client() as client:
        response = await client.post("/api/sigma-queue/1/approve", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_detailed_health_is_not_public():
    async with await _client() as client:
        response = await client.get("/api/health/database")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


# Regression coverage for the pre-release security-review finding: SAFE_ROUTE_RULES
# (GET requests) had no entries for /api/settings*, /api/backup/*, /api/model/*,
# /api/observables/training/*, or /api/sigma-queue/*, so those reads fell through to
# the bare AUTHENTICATED default -- any authenticated user with zero app role could
# read live secrets via GET /api/settings. UNSAFE_ROUTE_RULES already gated the write
# side of each of these to admin/rule_reviewer; the read side must match.
@pytest.mark.asyncio
async def test_settings_read_requires_admin():
    async with await _client() as client:
        response = await client.get("/api/settings", headers=_headers("huntable-analysts"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_settings_read_rejects_unauthenticated_request():
    async with await _client() as client:
        response = await client.get("/api/settings")

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.asyncio
async def test_backup_list_read_requires_admin():
    async with await _client() as client:
        response = await client.get("/api/backup/list", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_model_versions_read_requires_admin():
    async with await _client() as client:
        response = await client.get("/api/model/versions", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_sigma_queue_list_read_requires_rule_reviewer_or_admin():
    async with await _client() as client:
        response = await client.get("/api/sigma-queue/list", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"
