"""API routes for UI-managed scheduled Celery jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.services.scheduled_jobs_service import ScheduledJobsConfigError, ScheduledJobsService, SchedulerReloadError
from src.web.dependencies import logger

router = APIRouter(prefix="/api/scheduled-jobs", tags=["Scheduled Jobs"])


class ScheduledJobUpdate(BaseModel):
    """Editable state for a single scheduled job."""

    enabled: bool
    cron: str = Field(min_length=1)


class ScheduledJobsUpdateRequest(BaseModel):
    """Bulk update payload for scheduled jobs."""

    jobs: dict[str, ScheduledJobUpdate]


@router.get("")
async def api_get_scheduled_jobs():
    """Return the persisted scheduled job config for the Settings page."""
    try:
        service = ScheduledJobsService()
        return {"success": True, **await service.get_state()}
    except Exception as exc:  # noqa: BLE001
        logger.error("Scheduled jobs state error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("")
async def api_update_scheduled_jobs(payload: ScheduledJobsUpdateRequest):
    """Persist scheduled job config and reload Celery beat."""
    try:
        service = ScheduledJobsService()
        state = await service.update_state({job_id: update.model_dump() for job_id, update in payload.jobs.items()})
        return {"success": True, **state}
    except ScheduledJobsConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SchedulerReloadError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Scheduled jobs update error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
