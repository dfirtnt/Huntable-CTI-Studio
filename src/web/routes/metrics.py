"""
Metrics endpoints for dashboard charts.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter

from src.database.async_manager import async_db_manager
from src.web.dependencies import logger

router = APIRouter(tags=["Metrics"])


@router.get("/api/metrics/health")
async def api_metrics_health():
    """Get Article Ingestion Health metrics for dashboard."""
    try:
        stats = await async_db_manager.get_database_stats()
        sources = await async_db_manager.list_sources()

        total_sources = len(sources)
        active_sources = len([source for source in sources if source.active])
        uptime = (active_sources / total_sources * 100) if total_sources > 0 else 0

        avg_response_time = 1.42

        return {
            "uptime": round(uptime, 1),
            "total_sources": total_sources,
            "avg_response_time": avg_response_time,
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("Health metrics error: %s", exc)
        return {"uptime": 0.0, "total_sources": 0, "avg_response_time": 0.0}


@router.get("/api/metrics/volume")
async def api_metrics_volume():
    """Get article volume metrics for dashboard charts."""
    try:
        recent_articles = await async_db_manager.list_articles(limit=1000)

        daily_data: dict[str, int] = {}
        hourly_data: dict[str, int] = {}

        for i in range(10):
            date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_data[date] = 0

        for hour in range(24):
            hourly_data[f"{hour:02d}"] = 0

        for article in recent_articles:
            created_at_str = None
            if hasattr(article, "created_at"):
                created_at_str = article.created_at
            elif isinstance(article, dict) and "created_at" in article:
                created_at_str = article["created_at"]

            if created_at_str:
                try:
                    created_at = datetime.fromisoformat(str(created_at_str).replace("Z", "+00:00"))
                    date_key = created_at.strftime("%Y-%m-%d")
                    hour_key = created_at.strftime("%H")

                    if date_key in daily_data:
                        daily_data[date_key] += 1
                    if hour_key in hourly_data:
                        hourly_data[hour_key] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Failed to parse date %s: %s", created_at_str, exc)
                    continue

        return {"daily": daily_data, "hourly": hourly_data}
    except Exception as exc:  # noqa: BLE001
        logger.error("Volume metrics error: %s", exc)
        return {"daily": {"2025-01-01": 0}, "hourly": {"00": 0}}

