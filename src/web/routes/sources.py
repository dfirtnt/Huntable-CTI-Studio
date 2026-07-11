"""
Source management API routes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from celery import Celery
from fastapi import APIRouter, Depends, HTTPException, Request

from src.database.async_manager import async_db_manager
from src.models.source import SourceFilter, SourceUpdate
from src.services.audit_service import (
    ACTION_SOURCE_COLLECTION_REQUESTED,
    ACTION_SOURCE_TOGGLED,
    ACTION_SOURCE_UPDATED,
    STATUS_SUCCESS,
    AsyncAuditService,
    AuditEvent,
    build_actor_context,
)
from src.web.dependencies import logger

router = APIRouter(prefix="/api/sources", tags=["Sources"])


def _source_audit_event(
    request: Request,
    action: str,
    source_id: int,
    summary: str,
    metadata: dict[str, Any] | None = None,
    *,
    status: str = STATUS_SUCCESS,
) -> AuditEvent:
    """Build a source audit event with actor context from the request identity."""
    return AuditEvent(
        action=action,
        target_type="source",
        target_id=str(source_id),
        status=status,
        summary=summary,
        actor=build_actor_context(getattr(request.state, "identity", None), request),
        metadata=metadata or {},
    )


LOOKBACK_MIN_DAYS = 1
LOOKBACK_MAX_DAYS = 999


def _get_collection_method(source) -> str:
    """Determine collection method for a source."""
    # Check for Playwright first (newest method)
    config = source.config if isinstance(source.config, dict) else {}
    # Handle nested config structure
    if isinstance(config, dict) and "config" in config and isinstance(config["config"], dict):
        actual_config = config["config"]
    else:
        actual_config = config

    if isinstance(actual_config, dict) and actual_config.get("use_playwright", False):
        return "Playwright Scraping"

    # Check for RSS
    if source.rss_url and source.rss_url.strip():
        return "RSS Feed"

    # Default to Web Scraping
    return "Web Scraping"


@router.get("")
async def api_sources_list(filter_params: SourceFilter = Depends()):
    """API endpoint for listing sources."""
    try:
        sources = await async_db_manager.list_sources(filter_params)
        return {"sources": [source.dict() for source in sources]}
    except Exception as exc:
        logger.error("API sources list error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/failing")
async def api_sources_failing():
    """Get failing sources for dashboard."""
    try:
        sources = await async_db_manager.list_sources()
        failing_sources: list[dict[str, Any]] = []

        for source in sources:
            # Skip manual source from failure metrics
            if getattr(source, "identifier", "") == "manual":
                continue

            consecutive_failures = getattr(source, "consecutive_failures", 0)
            if consecutive_failures > 0:
                last_success = source.last_success
                last_success_str = last_success.strftime("%Y-%m-%d") if last_success else "Never"

                failing_sources.append(
                    {
                        "source_id": source.id,
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
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/{source_id}/toggle")
async def api_toggle_source_status(request: Request, source_id: int):
    """Toggle source active status."""
    try:
        async with async_db_manager.get_session() as session:
            result = await async_db_manager.toggle_source_status(source_id, session=session)
            if not result:
                raise HTTPException(status_code=404, detail="Source not found")
            await AsyncAuditService.record_mandatory(
                session,
                _source_audit_event(
                    request,
                    ACTION_SOURCE_TOGGLED,
                    source_id,
                    f"Toggled source {source_id} active status to {result['new_status']}",
                    {"old_status": result["old_status"], "new_status": result["new_status"]},
                ),
            )
            await session.commit()

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
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.post("/{source_id}/collect")
async def api_collect_from_source(request: Request, source_id: int):
    """Manually trigger collection from a specific source."""
    try:
        celery_app = Celery("cti_scraper")
        celery_app.config_from_object("src.worker.celeryconfig")

        task = celery_app.send_task(
            "src.worker.celery_app.collect_from_source",
            args=[source_id],
            queue="collection_immediate",
        )

        # No DB mutation here -- the worker performs collection asynchronously and
        # cannot be rolled back, so the dispatch is recorded best-effort with status.
        try:
            async with async_db_manager.get_session() as session:
                await AsyncAuditService.record_best_effort(
                    session,
                    _source_audit_event(
                        request,
                        ACTION_SOURCE_COLLECTION_REQUESTED,
                        source_id,
                        f"Requested collection for source {source_id}",
                        {"task_id": task.id},
                    ),
                )
        except Exception as audit_exc:  # noqa: BLE001
            logger.warning("Failed to audit source collection request for %s: %s", source_id, audit_exc)

        return {
            "success": True,
            "message": f"Collection task started for source {source_id}",
            "task_id": task.id,
        }

    except Exception as exc:
        logger.error("API collect from source error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/{source_id}/min_content_length")
async def api_update_source_min_content_length(request: Request, source_id: int, payload: dict):
    """Update source minimum content length."""
    try:
        min_content_length = payload.get("min_content_length")

        if min_content_length is None:
            raise HTTPException(status_code=400, detail="min_content_length is required")

        if not isinstance(min_content_length, int) or min_content_length < 0:
            raise HTTPException(
                status_code=400,
                detail="min_content_length must be a non-negative integer",
            )

        async with async_db_manager.get_session() as session:
            result = await async_db_manager.update_source_min_content_length(
                source_id, min_content_length, session=session
            )
            if not result:
                raise HTTPException(status_code=404, detail="Source not found")
            await AsyncAuditService.record_mandatory(
                session,
                _source_audit_event(
                    request,
                    ACTION_SOURCE_UPDATED,
                    source_id,
                    f"Updated min_content_length for source {source_id}",
                    {"min_content_length": min_content_length},
                ),
            )
            await session.commit()

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API update source min content length error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/{source_id}/image_ocr")
async def api_update_source_image_ocr(request: Request, source_id: int, payload: dict):
    """Set the per-source image OCR override: true (on), false (off), or null (inherit)."""
    try:
        if "image_ocr_enabled" not in payload:
            raise HTTPException(status_code=400, detail="image_ocr_enabled is required")

        value = payload["image_ocr_enabled"]
        if value is not None and not isinstance(value, bool):
            raise HTTPException(
                status_code=400,
                detail="image_ocr_enabled must be true, false, or null",
            )

        async with async_db_manager.get_session() as session:
            result = await async_db_manager.update_source_image_ocr_override(source_id, value, session=session)
            if result is None:
                raise HTTPException(status_code=404, detail="Source not found")
            if not result.get("success"):
                # Protected internal source: no mutation staged, so do not audit a success.
                raise HTTPException(status_code=400, detail=result.get("message", "Not allowed"))
            await AsyncAuditService.record_mandatory(
                session,
                _source_audit_event(
                    request,
                    ACTION_SOURCE_UPDATED,
                    source_id,
                    f"Updated image_ocr override for source {source_id} -> {result.get('state')}",
                    {"image_ocr_enabled": value, "state": result.get("state")},
                ),
            )
            await session.commit()

        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API update source image_ocr error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/{source_id}/lookback")
async def api_update_source_lookback(request: Request, source_id: int, payload: dict):
    """Update source lookback window."""
    try:
        lookback_days = payload.get("lookback_days")

        if not lookback_days:
            raise HTTPException(status_code=400, detail="lookback_days is required")

        if isinstance(lookback_days, str):
            try:
                lookback_days = int(lookback_days)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="lookback_days must be a valid integer") from exc

        if lookback_days < LOOKBACK_MIN_DAYS or lookback_days > LOOKBACK_MAX_DAYS:
            raise HTTPException(
                status_code=400,
                detail=(f"lookback_days must be between {LOOKBACK_MIN_DAYS} and {LOOKBACK_MAX_DAYS}"),
            )

        update_data = SourceUpdate(lookback_days=lookback_days)
        async with async_db_manager.get_session() as session:
            updated_source = await async_db_manager.update_source(source_id, update_data, session=session)
            if not updated_source:
                raise HTTPException(status_code=404, detail="Source not found")
            await AsyncAuditService.record_mandatory(
                session,
                _source_audit_event(
                    request,
                    ACTION_SOURCE_UPDATED,
                    source_id,
                    f"Updated lookback window for source {source_id} to {lookback_days} days",
                    {"lookback_days": lookback_days},
                ),
            )
            await session.commit()

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
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.put("/{source_id}/check_frequency")
async def api_update_source_check_frequency(request: Request, source_id: int, payload: dict):
    """Update source check frequency."""
    try:
        check_frequency = payload.get("check_frequency")

        if not check_frequency or not isinstance(check_frequency, int):
            raise HTTPException(status_code=400, detail="check_frequency must be a valid integer")

        if check_frequency < 60:
            raise HTTPException(status_code=400, detail="check_frequency must be at least 60 seconds")

        from sqlalchemy import update

        from src.database.models import SourceTable

        async with async_db_manager.get_session() as session:
            result = await session.execute(
                update(SourceTable)
                .where(SourceTable.id == source_id)
                .values(check_frequency=check_frequency, updated_at=datetime.now())
            )
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Source not found")
            await AsyncAuditService.record_mandatory(
                session,
                _source_audit_event(
                    request,
                    ACTION_SOURCE_UPDATED,
                    source_id,
                    f"Updated check frequency for source {source_id} to {check_frequency}s",
                    {"check_frequency": check_frequency},
                ),
            )
            await session.commit()

        logger.info(
            "Updated check frequency for source %s to %s seconds",
            source_id,
            check_frequency,
        )

        return {
            "success": True,
            "message": (f"Check frequency updated to {check_frequency} seconds ({check_frequency // 60} minutes)"),
            "check_frequency": check_frequency,
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Failed to update source check frequency: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.get("/{source_id}/stats")
async def api_source_stats(source_id: int):
    """Get source statistics."""
    try:
        source = await async_db_manager.get_source(source_id)
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        articles = await async_db_manager.list_articles_by_source(source_id)

        total_articles = len(articles)
        avg_content_length = sum(len(article.content or "") for article in articles) / max(total_articles, 1)

        threat_hunting_scores = []
        for article in articles:
            if article.article_metadata:
                score = article.article_metadata.get("threat_hunting_score", 0)
                if score > 0:
                    threat_hunting_scores.append(score)

        avg_threat_hunting_score = (
            sum(threat_hunting_scores) / len(threat_hunting_scores) if threat_hunting_scores else 0.0
        )

        articles_by_date: dict[str, int] = {}
        for article in articles:
            if article.published_at:
                date_key = article.published_at.strftime("%Y-%m-%d")
                articles_by_date[date_key] = articles_by_date.get(date_key, 0) + 1

        return {
            "source_id": source_id,
            "source_name": source.name,
            "active": getattr(source, "active", True),
            "tier": getattr(source, "tier", 1),
            "collection_method": _get_collection_method(source),
            "total_articles": total_articles,
            "avg_content_length": avg_content_length,
            "avg_threat_hunting_score": round(avg_threat_hunting_score, 1),
            "last_check": source.last_check.isoformat() if source.last_check else None,
            "articles_by_date": articles_by_date,
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("API source stats error: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error") from exc
