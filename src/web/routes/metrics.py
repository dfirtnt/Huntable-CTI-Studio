"""
Metrics endpoints for dashboard charts.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger
from src.web.routes.dashboard import _bucket_article_volume, _compute_ingestion_health

router = APIRouter(tags=["Metrics"])


@router.get("/api/metrics/health")
async def api_metrics_health():
    """Get Article Ingestion Health metrics for dashboard."""
    try:
        sources = await async_db_manager.list_sources()

        total_sources = len(sources)
        health = _compute_ingestion_health(sources)

        avg_response_time = 1.42

        return {
            "uptime": health["uptime"],
            "status": health["status"],
            "label": health["label"],
            "total_sources": total_sources,
            "monitored_sources": health["monitored_sources"],
            "healthy_sources": health["healthy_sources"],
            "warning_sources": health["warning_sources"],
            "critical_sources": health["critical_sources"],
            "avg_response_time": avg_response_time,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Health metrics error: %s", exc)
        return {
            "uptime": 0.0,
            "status": "critical",
            "label": "Critical",
            "total_sources": 0,
            "monitored_sources": 0,
            "healthy_sources": 0,
            "warning_sources": 0,
            "critical_sources": 0,
            "avg_response_time": 0.0,
        }


@router.get("/api/metrics/volume")
async def api_metrics_volume():
    """Get article volume metrics for dashboard charts."""
    try:
        recent_articles = await async_db_manager.list_articles(limit=1000)
        daily_data, hourly_data = _bucket_article_volume(recent_articles)
        return {"daily": daily_data, "hourly": hourly_data}
    except Exception as exc:  # noqa: BLE001
        logger.error("Volume metrics error: %s", exc)
        return {"daily": {"2025-01-01": 0}, "hourly": {"00": 0}}
