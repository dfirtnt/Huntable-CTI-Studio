"""
Celery task monitoring endpoints.
"""

from __future__ import annotations

import json
import os
from datetime import datetime

from fastapi import APIRouter, HTTPException

from src.web.dependencies import logger

router = APIRouter(tags=["Tasks"])


@router.get("/api/tasks/{task_id}/status")
async def api_get_task_status(task_id: str):
    """Get the status and result of a Celery task."""
    try:
        from celery import Celery

        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")
        result = celery_app.AsyncResult(task_id)

        response = {
            "task_id": task_id,
            "status": result.status,
            "ready": result.ready(),
            "successful": result.successful() if result.ready() else False,
            "failed": result.failed() if result.ready() else False,
        }

        if result.ready():
            if result.successful():
                response["result"] = result.result
            elif result.failed():
                response["error"] = str(result.result)
        elif hasattr(result, "info") and result.info:
            response["info"] = result.info

        return response

    except Exception as exc:  # noqa: BLE001
        logger.error("API get task status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/api/jobs/status")
async def api_jobs_status():
    """Get current status of all Celery jobs using Celery inspect API."""
    try:
        import asyncio

        from src.worker.celery_app import celery_app

        # Use Celery's inspect API to get active tasks directly from workers
        inspect = celery_app.control.inspect(timeout=1.0)  # 1 second timeout

        # Helper to run sync inspect calls with timeout
        def run_inspect(func_name):
            try:
                func = getattr(inspect, func_name)
                return func() or {}
            except Exception as e:
                logger.warning(f"Failed to get {func_name}: {e}")
                return {}

        # Get active tasks from all workers (with timeout handling)
        active_tasks = await asyncio.wait_for(asyncio.to_thread(run_inspect, "active"), timeout=2.0)

        # Get worker stats
        stats = await asyncio.wait_for(asyncio.to_thread(run_inspect, "stats"), timeout=2.0)

        # Get registered tasks
        registered = await asyncio.wait_for(asyncio.to_thread(run_inspect, "registered"), timeout=2.0)

        # Get scheduled tasks
        scheduled = await asyncio.wait_for(asyncio.to_thread(run_inspect, "scheduled"), timeout=2.0)

        # Get reserved tasks
        reserved = await asyncio.wait_for(asyncio.to_thread(run_inspect, "reserved"), timeout=2.0)

        # Get active queues for each worker
        active_queues = await asyncio.wait_for(asyncio.to_thread(run_inspect, "active_queues"), timeout=2.0)

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "active_tasks": active_tasks,
            "scheduled_tasks": scheduled,
            "reserved_tasks": reserved,
            "worker_stats": stats,
            "registered_tasks": registered,
            "active_queues": active_queues,
        }
    except TimeoutError:
        logger.warning("Celery inspect timeout")
        return {
            "status": "timeout",
            "timestamp": datetime.now().isoformat(),
            "active_tasks": {},
            "scheduled_tasks": {},
            "reserved_tasks": {},
            "worker_stats": {},
            "registered_tasks": {},
            "active_queues": {},
            "error": "Worker inspection timeout",
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get job status: %s", exc)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "active_tasks": {},
            "scheduled_tasks": {},
            "reserved_tasks": {},
            "worker_stats": {},
            "registered_tasks": {},
            "active_queues": {},
            "error": str(exc),
        }


@router.get("/api/jobs/queues")
async def api_jobs_queues():
    """Get queue information and lengths."""
    try:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_client = redis.from_url(redis_url, decode_responses=True)

        queues = {
            "default": redis_client.llen("celery"),
            "source_checks": redis_client.llen("source_checks"),
            "priority_checks": redis_client.llen("priority_checks"),
            "maintenance": redis_client.llen("maintenance"),
            "reports": redis_client.llen("reports"),
            "connectivity": redis_client.llen("connectivity"),
            "collection": redis_client.llen("collection"),
            "workflows": redis_client.llen("workflows"),
        }

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "queues": queues,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get queue info: %s", exc)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }


@router.get("/api/jobs/history")
async def api_jobs_history(limit: int = 50):
    """Get recent job history from Redis."""
    try:
        import redis

        redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
        redis_client = redis.from_url(redis_url, decode_responses=True)

        task_keys = redis_client.keys("celery-task-meta-*")
        recent_tasks = []

        for key in task_keys[:limit]:
            try:
                task_data = redis_client.get(key)
                if task_data:
                    task_info = json.loads(task_data)
                    recent_tasks.append(
                        {
                            "task_id": key.replace("celery-task-meta-", ""),
                            "status": task_info.get("status"),
                            "result": task_info.get("result"),
                            "date_done": task_info.get("date_done"),
                        }
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed to parse task data for key %s: %s", key, exc)
                continue

        def _parse_dt(value):
            try:
                if not value:
                    return datetime.min
                dt = datetime.fromisoformat(str(value))
                if dt.tzinfo is not None:
                    return dt.astimezone(tz=None).replace(tzinfo=None)
                return dt
            except Exception:
                return datetime.min

        recent_tasks.sort(key=lambda item: _parse_dt(item.get("date_done")), reverse=True)

        return {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "recent_tasks": recent_tasks[:limit],
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to get job history: %s", exc)
        return {
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": str(exc),
        }
