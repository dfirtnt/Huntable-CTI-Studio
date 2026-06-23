"""Audit event read/export/retention endpoints."""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import delete, func, select

from src.database.async_manager import async_db_manager
from src.database.models import AuditEventTable
from src.services.audit_service import (
    ACTION_AUDIT_EXPORTED,
    ACTION_AUDIT_RETENTION_APPLIED,
    STATUS_SUCCESS,
    AsyncAuditService,
    AuditEvent,
    build_actor_context,
)

router = APIRouter(prefix="/api/audit", tags=["Audit"])

DEFAULT_AUDIT_RETENTION_DAYS = 365


def _default_retention_days() -> int:
    """Resolve the retention window from AUDIT_RETENTION_DAYS (default 365)."""
    raw = os.getenv("AUDIT_RETENTION_DAYS")
    if not raw:
        return DEFAULT_AUDIT_RETENTION_DAYS
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_AUDIT_RETENTION_DAYS
    return value if value >= 1 else DEFAULT_AUDIT_RETENTION_DAYS


def _utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _serialize_event(row: AuditEventTable) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "request_id": row.request_id,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "actor_email": row.actor_email,
        "actor_roles": row.actor_roles,
        "source_ip": row.source_ip,
        "user_agent": row.user_agent,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "status": row.status,
        "summary": row.summary,
        "metadata": row.event_metadata,
        "before_hash": row.before_hash,
        "after_hash": row.after_hash,
        "error_code": row.error_code,
    }


@router.get("/events")
async def list_audit_events(
    limit: int = Query(100, ge=1, le=500),
    action: str | None = None,
    actor_id: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
):
    """List recent audit events."""
    async with async_db_manager.get_session() as session:
        stmt = select(AuditEventTable).order_by(AuditEventTable.created_at.desc()).limit(limit)
        if action:
            stmt = stmt.where(AuditEventTable.action == action)
        if actor_id:
            stmt = stmt.where(AuditEventTable.actor_id == actor_id)
        if target_type:
            stmt = stmt.where(AuditEventTable.target_type == target_type)
        if target_id:
            stmt = stmt.where(AuditEventTable.target_id == target_id)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    return {"success": True, "events": [_serialize_event(row) for row in rows]}


@router.post("/export")
async def export_audit_events(request: Request, limit: int = Query(1000, ge=1, le=10000)):
    """Export recent audit events and audit the export action."""
    async with async_db_manager.get_session() as session:
        result = await session.execute(select(AuditEventTable).order_by(AuditEventTable.created_at.desc()).limit(limit))
        rows = result.scalars().all()
        events = [_serialize_event(row) for row in rows]

        await AsyncAuditService.record_mandatory(
            session,
            AuditEvent(
                action=ACTION_AUDIT_EXPORTED,
                target_type="audit_events",
                target_id=None,
                status=STATUS_SUCCESS,
                summary=f"Exported {len(events)} audit events",
                actor=build_actor_context(getattr(request.state, "identity", None), request),
                metadata={"exported_count": len(events), "limit": limit},
            ),
        )
        await session.commit()

    return {
        "success": True,
        "exported_at": datetime.now(UTC).isoformat(),
        "count": len(events),
        "events": events,
    }


@router.delete("/retention")
async def apply_audit_retention(request: Request, retention_days: int | None = Query(None, ge=1, le=3650)):
    """Delete audit events older than the retention window.

    Defaults to AUDIT_RETENTION_DAYS (or 365) when no explicit window is given.
    """
    if retention_days is None:
        retention_days = _default_retention_days()
    cutoff = _utc_now_naive() - timedelta(days=retention_days)

    async with async_db_manager.get_session() as session:
        count_result = await session.execute(
            select(func.count()).select_from(AuditEventTable).where(AuditEventTable.created_at < cutoff)
        )
        deleted_count = int(count_result.scalar() or 0)

        await session.execute(delete(AuditEventTable).where(AuditEventTable.created_at < cutoff))
        await AsyncAuditService.record_mandatory(
            session,
            AuditEvent(
                action=ACTION_AUDIT_RETENTION_APPLIED,
                target_type="audit_events",
                target_id=None,
                status=STATUS_SUCCESS,
                summary=f"Deleted {deleted_count} audit events older than {retention_days} days",
                actor=build_actor_context(getattr(request.state, "identity", None), request),
                metadata={
                    "retention_days": retention_days,
                    "deleted_count": deleted_count,
                    "cutoff": cutoff.isoformat(),
                },
            ),
        )
        await session.commit()

    return {"success": True, "deleted_count": deleted_count, "retention_days": retention_days}


@router.get("/health")
async def audit_health():
    """Return minimal audit storage readiness."""
    try:
        async with async_db_manager.get_session() as session:
            result = await session.execute(select(func.count()).select_from(AuditEventTable))
            count = int(result.scalar() or 0)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Audit storage unavailable") from exc

    return {"success": True, "audit_events": count}
