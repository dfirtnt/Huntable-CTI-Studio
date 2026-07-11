"""Denied-request audit contract (Chunk C Task 5 Step 1).

The authorization middleware is the single denial path: every 401/403 it
returns must emit exactly one best-effort ``auth.request_denied`` audit event,
and allowed requests must emit none (no double-writes from route dependencies).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.services.audit_service import ACTION_AUTH_REQUEST_DENIED, STATUS_DENIED
from src.web.security.config import load_security_config
from src.web.security.middleware import AuthorizationMiddleware, IdentityMiddleware, RequestIDMiddleware
from src.web.security.route_manifest import RouteClassification, RouteManifestEntry

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


def _app() -> FastAPI:
    app = FastAPI()
    config = _trusted_header_config()

    @app.post("/api/admin")
    async def admin():
        return {"ok": True}

    @app.post("/api/unclassified")
    async def unclassified():
        return {"ok": True}

    app.state.route_manifest = [
        RouteManifestEntry(
            method="POST",
            path="/api/admin",
            endpoint_name="admin",
            route_module="test",
            classification=RouteClassification.ROLES,
            roles=("admin",),
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


def _client(app: FastAPI) -> AsyncClient:
    transport = ASGITransport(app=app, client=("10.0.0.1", 1234))
    return AsyncClient(transport=transport, base_url="http://testserver")


class _AsyncSessionCtx:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *exc):
        return False


def _patched_audit():
    """Patch the middleware's audit sink; returns (db_patch, record_patch)."""
    db = MagicMock()
    db.get_session.return_value = _AsyncSessionCtx()
    return (
        patch("src.web.security.middleware.async_db_manager", db),
        patch(
            "src.web.security.middleware.AsyncAuditService.record_best_effort",
            new_callable=AsyncMock,
        ),
    )


@pytest.mark.asyncio
async def test_unauthenticated_request_emits_one_denied_event():
    db_patch, record_patch = _patched_audit()
    with db_patch, record_patch as mock_record:
        async with _client(_app()) as client:
            response = await client.post("/api/admin")

    assert response.status_code == 401
    assert mock_record.await_count == 1
    event = mock_record.await_args.args[1]
    assert event.action == ACTION_AUTH_REQUEST_DENIED
    assert event.status == STATUS_DENIED
    assert event.error_code == "401"
    assert event.target_id == "POST /api/admin"


@pytest.mark.asyncio
async def test_insufficient_role_emits_one_denied_event():
    db_patch, record_patch = _patched_audit()
    with db_patch, record_patch as mock_record:
        async with _client(_app()) as client:
            response = await client.post("/api/admin", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert mock_record.await_count == 1
    event = mock_record.await_args.args[1]
    assert event.action == ACTION_AUTH_REQUEST_DENIED
    assert event.error_code == "403"
    assert event.actor.actor_id == "u1"


@pytest.mark.asyncio
async def test_unclassified_unsafe_route_emits_one_denied_event():
    db_patch, record_patch = _patched_audit()
    with db_patch, record_patch as mock_record:
        async with _client(_app()) as client:
            response = await client.post("/api/unclassified", headers=_headers())

    assert response.status_code == 403
    assert mock_record.await_count == 1
    assert mock_record.await_args.args[1].action == ACTION_AUTH_REQUEST_DENIED


@pytest.mark.asyncio
async def test_allowed_request_emits_no_denied_event():
    db_patch, record_patch = _patched_audit()
    with db_patch, record_patch as mock_record:
        async with _client(_app()) as client:
            response = await client.post("/api/admin", headers=_headers())

    assert response.status_code == 200
    mock_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_denial_still_responds_when_audit_sink_fails():
    db_patch, record_patch = _patched_audit()
    with db_patch, record_patch as mock_record:
        mock_record.side_effect = RuntimeError("audit storage down")
        async with _client(_app()) as client:
            response = await client.post("/api/admin")

    # Best-effort contract: denial responses never depend on audit storage.
    assert response.status_code == 401
