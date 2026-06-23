"""API tests for scheduled jobs settings endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from src.database.models import AuditEventTable
from src.services import audit_service
from src.services.scheduled_jobs_service import ScheduledJobsConfigError, SchedulerReloadError
from src.web.routes import scheduled_jobs as scheduled_jobs_routes


class _AsyncCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *exc):
        return False


def _req():
    return SimpleNamespace(
        state=SimpleNamespace(
            request_id="t",
            identity=SimpleNamespace(actor_type="local-dev", user_id="local-dev", email=None, roles=("admin",)),
        ),
        client=SimpleNamespace(host="127.0.0.1"),
        headers={"user-agent": "pytest"},
    )


def _audit_session():
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


def _audit_rows(session):
    return [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditEventTable)]


def _patch_session(monkeypatch, session):
    monkeypatch.setattr(scheduled_jobs_routes.async_db_manager, "get_session", lambda: _AsyncCtx(session))


def _patch_serialize(monkeypatch):
    monkeypatch.setattr(
        scheduled_jobs_routes,
        "serialize_scheduled_jobs_state",
        lambda normalized: {"timezone": "UTC", "jobs": [{"id": "cleanup_old_data", "cron": "15 1 * * *"}]},
    )


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_scheduled_jobs_returns_state(monkeypatch):
    """GET /api/scheduled-jobs should surface the persisted state."""
    expected = {
        "timezone": "UTC",
        "jobs": [
            {
                "id": "cleanup_old_data",
                "label": "Cleanup Old Data",
                "description": "Prune aged operational records from the database.",
                "task_name": "src.worker.celery_app.cleanup_old_data",
                "registered_name": "cleanup-old-data-daily",
                "queue": "maintenance",
                "timezone": "UTC",
                "default_cron": "0 2 * * *",
                "cron": "15 1 * * *",
                "enabled": False,
            }
        ],
    }

    class FakeService:
        async def get_state(self):
            return expected

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())

    result = await scheduled_jobs_routes.api_get_scheduled_jobs()

    assert result["success"] is True
    assert result["timezone"] == "UTC"
    assert result["jobs"][0]["cron"] == "15 1 * * *"


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_scheduled_jobs_persists_audits_and_reloads(monkeypatch):
    """PUT persists config + audit atomically, then reloads the scheduler."""

    class FakeService:
        async def persist_config(self, session, jobs):
            assert jobs["cleanup_old_data"] == {"enabled": False, "cron": "15 1 * * *"}
            return {"cleanup_old_data": {"enabled": False, "cron": "15 1 * * *"}}

        def restart_scheduler(self):
            return {"reloaded": True, "container": "cti_scheduler", "output": "cti_scheduler"}

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())
    session = _audit_session()
    _patch_session(monkeypatch, session)
    _patch_serialize(monkeypatch)

    result = await scheduled_jobs_routes.api_update_scheduled_jobs(
        _req(),
        scheduled_jobs_routes.ScheduledJobsUpdateRequest(
            jobs={"cleanup_old_data": scheduled_jobs_routes.ScheduledJobUpdate(enabled=False, cron="15 1 * * *")}
        ),
    )

    assert result["success"] is True
    assert result["scheduler_reload"]["reloaded"] is True
    rows = _audit_rows(session)
    assert len(rows) == 1
    assert rows[0].action == audit_service.ACTION_SCHEDULED_JOBS_UPDATED
    session.commit.assert_awaited_once()


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_scheduled_jobs_maps_validation_errors(monkeypatch):
    """Validation errors should become 422 responses and not commit."""

    class FakeService:
        async def persist_config(self, session, jobs):
            raise ScheduledJobsConfigError("Invalid cron expression")

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())
    session = _audit_session()
    _patch_session(monkeypatch, session)

    with pytest.raises(HTTPException) as exc_info:
        await scheduled_jobs_routes.api_update_scheduled_jobs(
            _req(),
            scheduled_jobs_routes.ScheduledJobsUpdateRequest(
                jobs={"cleanup_old_data": scheduled_jobs_routes.ScheduledJobUpdate(enabled=True, cron="broken")}
            ),
        )

    assert exc_info.value.status_code == 422
    session.commit.assert_not_awaited()


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_scheduled_jobs_maps_reload_errors(monkeypatch):
    """A post-commit scheduler reload failure should become a 500 (config already audited)."""

    class FakeService:
        async def persist_config(self, session, jobs):
            return {"cleanup_old_data": {"enabled": True, "cron": "0 2 * * *"}}

        def restart_scheduler(self):
            raise SchedulerReloadError("restart failed")

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())
    session = _audit_session()
    _patch_session(monkeypatch, session)
    _patch_serialize(monkeypatch)

    with pytest.raises(HTTPException) as exc_info:
        await scheduled_jobs_routes.api_update_scheduled_jobs(
            _req(),
            scheduled_jobs_routes.ScheduledJobsUpdateRequest(
                jobs={"cleanup_old_data": scheduled_jobs_routes.ScheduledJobUpdate(enabled=True, cron="0 2 * * *")}
            ),
        )

    assert exc_info.value.status_code == 500
    # The persist transaction committed with its audit event before the reload failed.
    assert len(_audit_rows(session)) == 1
    session.commit.assert_awaited_once()
