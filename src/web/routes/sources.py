"""
Source management API routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException

from src.database.async_manager import async_db_manager
from src.models.source import SourceFilter, SourceUpdate
from src.web.dependencies import logger

router = APIRouter(prefix="/api/sources", tags=["Sources"])


@router.get("")
async def api_sources_list(filter_params: SourceFilter = Depends()):
    """API endpoint for listing sources."""
    try:
        sources = await async_db_manager.list_sources(filter_params)
        return {"sources": [source.dict() for source in sources]}
    except Exception as exc:
        logger.error("API sources list error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/failing")
async def api_sources_failing():
    """Get failing sources for dashboard."""
    try:
        sources = await async_db_manager.list_sources()
        failing_sources: list[dict[str, Any]] = []

        for source in sources:
            consecutive_failures = getattr(source, "consecutive_failures", 0)
            if consecutive_failures > 0:
                last_success = source.last_success
                last_success_str = last_success.strftime("%Y-%m-%d") if last_success else "Never"

                failing_sources.append(
                    {
                        "source_name": source.name,
                        "consecutive_failures": consecutive_failures,
                        "last_success": last_success_str,
                    }
                )

        failing_sources.sort(key=lambda x: x["consecutive_failures"], reverse=True)
        return failing_sources[:10]
    except Exception as exc:
        logger.error("Failing sources error: %s", exc)
        return []


@router.get("/{source_id}")
async def api_get_source(source_id: int):
    """API endpoint for getting a specific source."""
    try:
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        return source.dict()
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API get source error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{source_id}/toggle")
async def api_toggle_source_status(source_id: int):
    """Toggle source active status."""
    try:
        result = await async_db_manager.toggle_source_status(source_id)
        if not result:
            raise HTTPException(status_code=404, detail="Source not found")

        return {
            "success": True,
            "source_id": result["source_id"],
            "source_name": result["source_name"],
            "old_status": result["old_status"],
            "new_status": result["new_status"],
            "message": (
                f"Source {result['source_name']} status changed from "
                f"{'Active' if result['old_status'] else 'Inactive'} to "
                f"{'Active' if result['new_status'] else 'Inactive'}"
            ),
            "database_updated": True,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API toggle source status error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/{source_id}/collect")
async def api_collect_from_source(source_id: int):
    """Manually trigger collection from a specific source."""
    try:
        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")

        task = celery_app.send_task(
            "src.worker.celery_app.collect_from_source", args=[source_id], queue="collection"
        )

        return {
            "success": True,
            "message": f"Collection task started for source {source_id}",
            "task_id": task.id,
        }

    except Exception as exc:
        logger.error("API collect from source error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{source_id}/min_content_length")
async def api_update_source_min_content_length(source_id: int, request: dict):
    """Update source minimum content length."""
    try:
        min_content_length = request.get("min_content_length")

        if min_content_length is None:
            raise HTTPException(status_code=400, detail="min_content_length is required")

        if not isinstance(min_content_length, int) or min_content_length < 0:
            raise HTTPException(
                status_code=400,
                detail="min_content_length must be a non-negative integer",
            )

        result = await async_db_manager.update_source_min_content_length(
            source_id, min_content_length
        )
        if not result:
            raise HTTPException(status_code=404, detail="Source not found")

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API update source min content length error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{source_id}/lookback")
async def api_update_source_lookback(source_id: int, request: dict):
    """Update source lookback window."""
    try:
        lookback_days = request.get("lookback_days")

        if not lookback_days:
            raise HTTPException(status_code=400, detail="lookback_days is required")

        if isinstance(lookback_days, str):
            try:
                lookback_days = int(lookback_days)
            except ValueError as exc:
                raise HTTPException(
                    status_code=400, detail="lookback_days must be a valid integer"
                ) from exc

        if lookback_days < 1 or lookback_days > 365:
            raise HTTPException(
                status_code=400, detail="lookback_days must be between 1 and 365"
            )

        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        update_data = SourceUpdate(lookback_days=lookback_days)
        updated_source = await async_db_manager.update_source(source_id, update_data)
        if not updated_source:
            raise HTTPException(status_code=500, detail="Failed to update source")

        logger.info("Updated lookback window for source %s to %s days", source_id, lookback_days)

        return {
            "success": True,
            "message": f"Lookback window updated to {lookback_days} days",
            "lookback_days": lookback_days,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update source lookback window: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/{source_id}/check_frequency")
async def api_update_source_check_frequency(source_id: int, request: dict):
    """Update source check frequency."""
    try:
        check_frequency = request.get("check_frequency")

        if not check_frequency or not isinstance(check_frequency, int):
            raise HTTPException(
                status_code=400, detail="check_frequency must be a valid integer"
            )

        if check_frequency < 60:
            raise HTTPException(
                status_code=400, detail="check_frequency must be at least 60 seconds"
            )

        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        from sqlalchemy import update
        from src.database.models import SourceTable

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                update(SourceTable)
                .where(SourceTable.id == source_id)
                .values(check_frequency=check_frequency, updated_at=datetime.now())
            )
            await session.commit()

            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Source not found")

        logger.info(
            "Updated check frequency for source %s to %s seconds",
            source_id,
            check_frequency,
        )

        return {
            "success": True,
            "message": (
                f"Check frequency updated to {check_frequency} seconds "
                f"({check_frequency // 60} minutes)"
            ),
            "check_frequency": check_frequency,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update source check frequency: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{source_id}/stats")
async def api_source_stats(source_id: int):
    """Get source statistics."""
    try:
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        articles = await async_db_manager.list_articles_by_source(source_id)

        total_articles = len(articles)
        avg_content_length = sum(len(article.content or "") for article in articles) / max(
            total_articles, 1
        )

        threat_hunting_scores = []
        for article in articles:
            if article.article_metadata:
                score = article.article_metadata.get("threat_hunting_score", 0)
                if score > 0:
                    threat_hunting_scores.append(score)

        avg_threat_hunting_score = (
            sum(threat_hunting_scores) / len(threat_hunting_scores)
            if threat_hunting_scores
            else 0.0
        )

        articles_by_date: dict[str, int] = {}
        for article in articles:
            if article.published_at:
                date_key = article.published_at.strftime("%Y-%m-%d")
                articles_by_date[date_key] = articles_by_date.get(date_key, 0) + 1

        stats = {
            "source_id": source_id,
            "source_name": source.name,
            "active": getattr(source, "active", True),
            "tier": getattr(source, "tier", 1),
            "collection_method": "RSS" if source.rss_url else "Web Scraping",
            "total_articles": total_articles,
            "avg_content_length": avg_content_length,
            "avg_threat_hunting_score": round(avg_threat_hunting_score, 1),
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "articles_by_date": articles_by_date,
        }

        return stats
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API source stats error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

