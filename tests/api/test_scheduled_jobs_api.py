"""API tests for scheduled jobs settings endpoints."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from src.services.scheduled_jobs_service import ScheduledJobsConfigError, SchedulerReloadError
from src.web.routes import scheduled_jobs as scheduled_jobs_routes


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
async def test_update_scheduled_jobs_returns_updated_state(monkeypatch):
    """PUT /api/scheduled-jobs should persist config and surface reload metadata."""
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
        "scheduler_reload": {"reloaded": True, "container": "cti_scheduler", "output": "cti_scheduler"},
    }

    class FakeService:
        async def update_state(self, jobs):
            assert jobs["cleanup_old_data"] == {"enabled": False, "cron": "15 1 * * *"}
            return expected

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())

    result = await scheduled_jobs_routes.api_update_scheduled_jobs(
        scheduled_jobs_routes.ScheduledJobsUpdateRequest(
            jobs={"cleanup_old_data": scheduled_jobs_routes.ScheduledJobUpdate(enabled=False, cron="15 1 * * *")}
        )
    )

    assert result["success"] is True
    assert result["scheduler_reload"]["reloaded"] is True


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_scheduled_jobs_maps_validation_errors(monkeypatch):
    """Validation errors should become 422 responses."""
    class FakeService:
        async def update_state(self, jobs):
            raise ScheduledJobsConfigError("Invalid cron expression")

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())

    with pytest.raises(HTTPException) as exc_info:
        await scheduled_jobs_routes.api_update_scheduled_jobs(
            scheduled_jobs_routes.ScheduledJobsUpdateRequest(
                jobs={"cleanup_old_data": scheduled_jobs_routes.ScheduledJobUpdate(enabled=True, cron="broken")}
            )
        )

    assert exc_info.value.status_code == 422


@pytest.mark.api
@pytest.mark.asyncio
async def test_update_scheduled_jobs_maps_reload_errors(monkeypatch):
    """Scheduler reload failures should become 500 responses."""
    class FakeService:
        async def update_state(self, jobs):
            raise SchedulerReloadError("restart failed")

    monkeypatch.setattr(scheduled_jobs_routes, "ScheduledJobsService", lambda: FakeService())

    with pytest.raises(HTTPException) as exc_info:
        await scheduled_jobs_routes.api_update_scheduled_jobs(
            scheduled_jobs_routes.ScheduledJobsUpdateRequest(
                jobs={"cleanup_old_data": scheduled_jobs_routes.ScheduledJobUpdate(enabled=True, cron="0 2 * * *")}
            )
        )

    assert exc_info.value.status_code == 500
