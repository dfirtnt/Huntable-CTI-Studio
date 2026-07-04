"""API routes for UI-managed scheduled Celery jobs."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.database.async_manager import async_db_manager
from src.services.audit_service import (
    ACTION_SCHEDULED_JOBS_UPDATED,
    STATUS_SUCCESS,
    AsyncAuditService,
    AuditEvent,
    build_actor_context,
)
from src.services.scheduled_jobs_service import (
    ScheduledJobsConfigError,
    ScheduledJobsService,
    SchedulerReloadError,
    serialize_scheduled_jobs_state,
)
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
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("")
async def api_update_scheduled_jobs(request: Request, payload: ScheduledJobsUpdateRequest):
    """Persist scheduled job config (audited atomically) and reload Celery beat."""
    try:
        service = ScheduledJobsService()
        jobs = {job_id: update.model_dump() for job_id, update in payload.jobs.items()}

        # Persist the config and its audit event in one transaction. The scheduler
        # restart is a non-rollbackable side effect, so it runs only after commit.
        async with async_db_manager.get_session() as session:
            normalized = await service.persist_config(session, jobs)
            await AsyncAuditService.record_mandatory(
                session,
                AuditEvent(
                    action=ACTION_SCHEDULED_JOBS_UPDATED,
                    target_type="scheduled_jobs",
                    target_id=None,
                    status=STATUS_SUCCESS,
                    summary=f"Updated scheduled job config ({len(jobs)} job(s))",
                    actor=build_actor_context(getattr(request.state, "identity", None), request),
                    metadata={"jobs": sorted(jobs.keys())},
                ),
            )
            await session.commit()

        reload_result = service.restart_scheduler()
        state = serialize_scheduled_jobs_state(normalized)
        state["scheduler_reload"] = reload_result
        return {"success": True, **state}
    except ScheduledJobsConfigError as exc:
        raise HTTPException(status_code=422, detail="Validation error") from exc
    except SchedulerReloadError as exc:
        # Config was persisted + audited; only the post-commit scheduler reload failed.
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Scheduled jobs update error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
