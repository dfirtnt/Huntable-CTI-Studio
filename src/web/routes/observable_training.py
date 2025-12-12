"""
Observable extractor training API endpoints.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

from src.services.observable_training import (
    get_observable_training_summary,
    run_observable_training_job,
    SUPPORTED_OBSERVABLE_TYPES,
)
from src.web.dependencies import logger

try:
    from src.worker.tasks.observable_training import train_observable_extractor
except Exception:  # pragma: no cover
    train_observable_extractor = None

router = APIRouter(prefix="/api/observables/training", tags=["Observable Training"])


@router.get("/summary")
async def api_observable_training_summary():
    """Return observable annotation and artifact statistics."""
    try:
        summary = await get_observable_training_summary()
        return {"success": True, **summary}
    except Exception as exc:  # noqa: BLE001
        logger.error("Observable training summary error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/run")
async def api_run_cmd_training(body: Dict[str, Any] | None = None):
    """Trigger observable extractor training via Celery or fallback to synchronous mode."""
    body = body or {}
    observable_type = (body.get("observable_type") or "CMD").upper()
    if observable_type not in SUPPORTED_OBSERVABLE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported observable type")
    try:
        if train_observable_extractor:
            task = train_observable_extractor.delay(observable_type)
            return {
                "success": True,
                "mode": "async",
                "task_id": task.id,
                "observable_type": observable_type,
                "message": f"{observable_type} training task submitted",
            }
    except Exception as exc:  # noqa: BLE001
        logger.warning("Celery submission failed, falling back to synchronous run: %s", exc)

    # Fallback to synchronous execution (useful for tests or environments without Celery)
    try:
        result = run_observable_training_job(observable_type)
        return {
            "success": True,
            "mode": "sync",
            "observable_type": observable_type,
            "result": result,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Observable training run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
