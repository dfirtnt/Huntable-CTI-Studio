"""API tests for backup cron management endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.services.maintenance_client import MaintenanceServiceError
from src.web.routes import backup as backup_routes


@pytest.fixture(autouse=True)
def _no_real_audit_writes():
    """Stub the backup routes' audit sink for this module.

    These tests call the route coroutines directly with no live database. The
    routes emit status-aware audit events, which would otherwise be the only real
    DB access here. Audit emission is covered by
    tests/unit/test_privileged_route_audit.py.
    """
    with patch(
        "src.web.routes.backup.AsyncAuditService.record_out_of_band",
        new=AsyncMock(return_value=True),
    ):
        yield


def _audit_request():
    """Minimal Request stand-in for routes that now capture actor context."""
    return SimpleNamespace(
        state=SimpleNamespace(identity=None, request_id="test-req"),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
    )


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_backup_cron_returns_state(monkeypatch):
    """GET handler should surface cron state payload."""
    expected = {
        "cron_available": True,
        "automated": True,
        "jobs": [
            {
                "schedule": "0 2 * * *",
                "command": "echo hi",
                "managed": False,
                "kind": "external",
                "comment": None,
                "raw": "0 2 * * * echo hi",
            }
        ],
        "managed_jobs": [],
        "config": {"backup_time": "02:00"},
    }
    monkeypatch.setattr(backup_routes, "_get_cron_state", lambda: expected)

    result = await backup_routes.api_get_backup_cron()

    assert result["success"] is True
    assert result["cron_available"] is True
    assert result["config"]["backup_time"] == "02:00"


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_backup_cron_saves_config_and_applies_when_requested(monkeypatch):
    """POST handler should save config and install managed cron jobs when requested."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

        def validate_config(self):
            return []

        def save_config(self):
            return True

    class FakeService:
        def get_state(self, cfg):
            return {
                "cron_available": True,
                "automated": False,
                "jobs": [],
                "managed_jobs": [],
                "config": {"backup_time": cfg.backup_time},
            }

        def install_backup_schedule(self, cfg):
            return {
                "cron_available": True,
                "automated": True,
                "jobs": [],
                "managed_jobs": [{"kind": "backup"}],
                "config": {"backup_time": cfg.backup_time},
            }

    monkeypatch.setattr(backup_routes, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_routes, "BackupCronService", lambda: FakeService())

    payload = backup_routes.BackupCronUpdate(
        backup_time="04:20",
        cleanup_time="05:30",
        daily=8,
        weekly=4,
        monthly=2,
        max_size_gb=60,
        backup_dir="archives",
        backup_type="database",
        compress=False,
        verify=True,
        install_crontab=True,
    )

    result = await backup_routes.api_update_backup_cron(_audit_request(), payload)

    assert result["success"] is True
    assert result["crontab_applied"] is True
    assert result["automated"] is True
    assert config.backup_time == "04:20"
    assert config.backup_type == "database"
    assert config.compress is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_delete_backup_cron_removes_managed_jobs(monkeypatch):
    """DELETE handler should call service removal and return updated state."""
    config = SimpleNamespace()

    class FakeManager:
        def get_config(self):
            return config

    class FakeService:
        def remove_backup_schedule(self, cfg):
            assert cfg is config
            return {"cron_available": True, "automated": False, "jobs": [], "managed_jobs": [], "config": {}}

    monkeypatch.setattr(backup_routes, "get_backup_config_manager", lambda: FakeManager())
    monkeypatch.setattr(backup_routes, "BackupCronService", lambda: FakeService())

    result = await backup_routes.api_delete_backup_cron(_audit_request())

    assert result["success"] is True
    assert result["automated"] is False


@pytest.mark.api
@pytest.mark.asyncio
async def test_restore_from_file_rejects_invalid_extension():
    """Only .sql and .sql.gz files should be accepted for file-based restore."""
    from io import BytesIO

    from fastapi import UploadFile

    bad_file = UploadFile(filename="backup.txt", file=BytesIO(b"irrelevant"))
    with pytest.raises(Exception) as exc_info:
        await backup_routes.api_restore_from_file(_audit_request(), file=bad_file)
    assert exc_info.value.status_code == 400
    assert "Invalid file type" in str(exc_info.value.detail)


@pytest.mark.api
@pytest.mark.asyncio
async def test_create_backup_returns_json_http_error_when_maintenance_is_unavailable(monkeypatch):
    """A maintenance outage must not leak an HTML 500 page to the UI."""
    request = _audit_request()
    request.json = AsyncMock(return_value={})

    async def unavailable(*args, **kwargs):
        raise MaintenanceServiceError("connection failed")

    monkeypatch.setattr(backup_routes, "run_backup_operation", unavailable)

    with pytest.raises(backup_routes.HTTPException) as exc_info:
        await backup_routes.api_create_backup(request)

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Backup service unavailable"


@pytest.mark.api
@pytest.mark.asyncio
async def test_restore_from_file_accepts_sql_extension(monkeypatch, tmp_path):
    """A .sql file should pass extension validation and proceed to script invocation."""
    from io import BytesIO

    from fastapi import UploadFile

    async def fake_operation(operation, payload, *, timeout):
        assert operation == "restore-file"
        assert payload["suffix"] == ".sql"
        return {"returncode": 0, "stdout": "restored", "stderr": ""}

    monkeypatch.setattr(backup_routes, "run_backup_operation", fake_operation)

    sql_file = UploadFile(filename="backup.sql", file=BytesIO(b"SELECT 1"))
    result = await backup_routes.api_restore_from_file(_audit_request(), file=sql_file)
    assert result["success"] is True


@pytest.mark.api
@pytest.mark.asyncio
async def test_restore_from_file_accepts_sql_gz_extension(monkeypatch, tmp_path):
    """A .sql.gz file should pass extension validation."""
    from io import BytesIO

    from fastapi import UploadFile

    async def fake_operation(operation, payload, *, timeout):
        assert operation == "restore-file"
        assert payload["suffix"] == ".sql.gz"
        return {"returncode": 0, "stdout": "restored", "stderr": ""}

    monkeypatch.setattr(backup_routes, "run_backup_operation", fake_operation)

    gz_file = UploadFile(filename="backup.sql.gz", file=BytesIO(b"\x1f\x8b"))
    result = await backup_routes.api_restore_from_file(_audit_request(), file=gz_file)
    assert result["success"] is True


@pytest.mark.api
def test_backup_endpoints_are_admin_classified_in_manifest():
    """Enterprise contract (replaces the legacy 'no Depends() allowed' rule).

    Backup create/restore/cron endpoints are admin-only and mandatorily audited.
    Authorization is enforced centrally by the route manifest +
    AuthorizationMiddleware (see tests/api/test_route_family_authorization.py for
    the live 403 behavior), not per-handler Depends(). The Settings page keeps
    working: in production the admin is authenticated by the upstream proxy; in
    local AUTH_MODE=disabled the synthetic local-dev admin identity satisfies the
    role.
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

    for method, path in (
        ("POST", "/api/backup/create"),
        ("POST", "/api/backup/restore"),
        ("POST", "/api/backup/restore-from-file"),
        ("POST", "/api/backup/cron"),
        ("DELETE", "/api/backup/cron"),
    ):
        entry = find_manifest_entry(manifest, method, path)
        assert entry is not None, f"{method} {path} missing from route manifest"
        assert entry.classification is RouteClassification.ROLES, f"{method} {path} not role-gated"
        assert entry.roles == ("admin",), f"{method} {path} not admin-only"
        assert entry.audit_requirement is AuditRequirement.MANDATORY, f"{method} {path} not mandatory-audit"
