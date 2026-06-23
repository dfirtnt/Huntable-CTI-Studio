"""API tests for generic cron endpoints."""

from __future__ import annotations

import pytest

from src.services.backup_cron_service import CronUnavailableError
from src.web.routes import cron as cron_routes

pytestmark = pytest.mark.api


async def _run_async(awaitable):
    return await awaitable


def test_get_cron_returns_snapshot(monkeypatch):
    """GET /api/cron should return the current crontab snapshot."""

    class FakeService:
        def get_snapshot(self):
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [{"schedule": "0 1 * * *", "command": "echo hi", "managed": False, "kind": "external"}],
                "managed_jobs": [],
                "raw": "0 1 * * * echo hi",
            }

    monkeypatch.setattr(cron_routes, "BackupCronService", lambda: FakeService())

    result = __import__("asyncio").run(cron_routes.api_get_cron())

    assert result["success"] is True
    assert result["cron_available"] is True
    assert result["raw"] == "0 1 * * * echo hi"


def test_replace_cron_returns_updated_snapshot(monkeypatch):
    """PUT /api/cron should replace the crontab and return the updated snapshot."""

    class FakeService:
        def replace_crontab(self, content: str):
            assert content == "5 4 * * * echo updated"
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [{"schedule": "5 4 * * *", "command": "echo updated", "managed": False, "kind": "external"}],
                "managed_jobs": [],
                "raw": content,
            }

    monkeypatch.setattr(cron_routes, "BackupCronService", lambda: FakeService())

    result = __import__("asyncio").run(
        cron_routes.api_replace_cron(cron_routes.CronUpdate(content="5 4 * * * echo updated"))
    )

    assert result["success"] is True
    assert result["jobs"][0]["schedule"] == "5 4 * * *"


def test_replace_cron_returns_success_when_cron_unavailable(monkeypatch):
    """Regression: PUT /api/cron must return 200 with cron_available:false when crontab is unavailable.

    On macOS (sandboxed or no Full Disk Access) crontab raises CronUnavailableError.
    Before the fix this propagated as 503, which the Settings page Save button treated
    as a failure and displayed 'Failed to save: cron editor'.
    """

    class FakeService:
        def replace_crontab(self, content: str):
            raise CronUnavailableError("crontab not available in this environment")

        def get_snapshot(self):
            return {
                "cron_available": False,
                "automated": False,
                "jobs": [],
                "managed_jobs": [],
                "raw": "",
            }

    monkeypatch.setattr(cron_routes, "BackupCronService", lambda: FakeService())

    result = __import__("asyncio").run(cron_routes.api_replace_cron(cron_routes.CronUpdate(content="")))

    assert result["success"] is True
    assert result["cron_available"] is False
    assert result["jobs"] == []


def test_cron_replace_is_operator_classified_in_manifest():
    """Enterprise contract (replaces the legacy 'no Depends() allowed' rule).

    PUT /api/cron is operator/admin-only and mandatorily audited. Authorization
    is enforced centrally by the route manifest + AuthorizationMiddleware (see
    tests/api/test_route_family_authorization.py for the live 401/403 behavior),
    not per-handler Depends(). The Settings page keeps working: in production the
    operator is authenticated by the upstream proxy; in local AUTH_MODE=disabled
    the synthetic local-dev admin identity satisfies the role.
    """
    from fastapi import FastAPI

    from src.web.routes import register_routes
    from src.web.security.route_manifest import (
        AuditRequirement,
        RouteClassification,
        build_route_manifest,
        find_manifest_entry,
    )

    app = FastAPI()
    register_routes(app)
    manifest = build_route_manifest(app)

    entry = find_manifest_entry(manifest, "PUT", "/api/cron")
    assert entry is not None, "PUT /api/cron missing from route manifest"
    assert entry.classification is RouteClassification.ROLES
    assert entry.roles == ("operator", "admin")
    assert entry.audit_requirement is AuditRequirement.MANDATORY
