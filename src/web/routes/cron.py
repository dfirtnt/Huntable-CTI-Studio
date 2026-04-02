"""Generic user crontab management API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.services.backup_cron_service import BackupCronService, CronCommandError, CronUnavailableError
from src.web.dependencies import logger

router = APIRouter(prefix="/api/cron", tags=["Cron"])


class CronUpdate(BaseModel):
    """Request model for replacing the current user's crontab."""

    content: str


@router.get("")
async def api_get_cron():
    """Return the current user's crontab, parsed jobs, and managed CTI entries."""
    try:
        service = BackupCronService()
        return {"success": True, **service.get_snapshot()}
    except CronCommandError as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Cron state error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("")
async def api_replace_cron(payload: CronUpdate):
    """Replace the current user's crontab."""
    try:
        service = BackupCronService()
        return {"success": True, **service.replace_crontab(payload.content)}
    except CronUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Service unavailable") from exc
    except CronCommandError as exc:
        raise HTTPException(status_code=500, detail="Internal server error") from exc
    except Exception as exc:  # noqa: BLE001
        logger.error("Cron replace error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
