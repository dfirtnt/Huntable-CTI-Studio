from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.database.async_manager import async_db_manager
from src.database.models import AuditEventTable
from src.web.routes import register_routes
from src.web.security.config import load_security_config
from src.web.security.middleware import AuthorizationMiddleware, IdentityMiddleware, RequestIDMiddleware
from src.web.security.route_manifest import build_route_manifest, validate_route_manifest

pytestmark = pytest.mark.api


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


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


def _headers(groups: str = "huntable-admins") -> dict[str, str]:
    return {
        "X-Huntable-Verified": "true",
        "X-Huntable-User-Id": "u1",
        "X-Huntable-Email": "admin@example.com",
        "X-Huntable-Groups": groups,
    }


async def _client():
    return AsyncClient(
        transport=ASGITransport(app=_app(), client=("10.0.0.1", 1234)),
        base_url="http://testserver",
    )


async def _seed_event(action: str = "test.event", *, created_at: datetime | None = None) -> None:
    async with async_db_manager.get_session() as session:
        session.add(
            AuditEventTable(
                created_at=created_at or _utc_now_naive(),
                actor_type="human",
                actor_id="seed-user",
                actor_roles=["admin"],
                action=action,
                target_type="test",
                target_id="1",
                status="success",
                summary="Seed event",
                event_metadata={"safe": True},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_admin_can_list_audit_events():
    await _seed_event("test.audit.list")

    async with await _client() as client:
        response = await client.get("/api/audit/events?action=test.audit.list", headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["events"][0]["action"] == "test.audit.list"


@pytest.mark.asyncio
async def test_non_admin_cannot_list_audit_events():
    async with await _client() as client:
        response = await client.get("/api/audit/events", headers=_headers("huntable-operators"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Insufficient role"


@pytest.mark.asyncio
async def test_admin_export_emits_audit_event():
    await _seed_event("test.audit.export")

    async with await _client() as client:
        response = await client.post("/api/audit/export?limit=10", headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["count"] >= 1

    async with await _client() as client:
        audit_response = await client.get("/api/audit/events?action=audit.exported", headers=_headers())
    assert audit_response.status_code == 200
    assert audit_response.json()["events"][0]["action"] == "audit.exported"


@pytest.mark.asyncio
async def test_admin_retention_deletes_old_events_and_emits_audit_event():
    await _seed_event("test.audit.retention.old", created_at=_utc_now_naive() - timedelta(days=10))

    async with await _client() as client:
        response = await client.delete("/api/audit/retention?retention_days=1", headers=_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["deleted_count"] >= 1

    async with await _client() as client:
        audit_response = await client.get("/api/audit/events?action=audit.retention_applied", headers=_headers())
    assert audit_response.status_code == 200
    assert audit_response.json()["events"][0]["action"] == "audit.retention_applied"


@pytest.mark.asyncio
async def test_retention_uses_env_default_when_no_param(monkeypatch):
    # No retention_days query param -> the endpoint resolves AUDIT_RETENTION_DAYS.
    monkeypatch.setenv("AUDIT_RETENTION_DAYS", "777")

    async with await _client() as client:
        response = await client.delete("/api/audit/retention", headers=_headers())

    assert response.status_code == 200
    assert response.json()["retention_days"] == 777
