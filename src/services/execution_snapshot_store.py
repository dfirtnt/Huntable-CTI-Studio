"""Content-addressed storage for immutable execution configuration snapshots."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from src.database.models import AgenticWorkflowExecutionSnapshotTable, AgenticWorkflowExecutionTable
from src.services.workflow_config_snapshot import SNAPSHOT_HASH_KEY, canonical_snapshot_hash


def store_snapshot(session: Session, payload: dict) -> AgenticWorkflowExecutionSnapshotTable:
    """Return the immutable row for *payload*, creating it once per content hash."""
    content_hash = payload.get(SNAPSHOT_HASH_KEY) or canonical_snapshot_hash(payload)
    record = (
        session.query(AgenticWorkflowExecutionSnapshotTable)
        .filter(AgenticWorkflowExecutionSnapshotTable.content_hash == content_hash)
        .first()
    )
    if record is None:
        record = AgenticWorkflowExecutionSnapshotTable(content_hash=content_hash, payload=dict(payload))
        session.add(record)
        session.flush()
    return record


def attach_snapshot(session: Session, execution: AgenticWorkflowExecutionTable, payload: dict) -> None:
    """Store *payload* once and leave only its immutable reference on the execution."""
    record = store_snapshot(session, payload)
    execution.config_snapshot_id = record.id
    execution.config_snapshot = {"snapshot_id": record.id}


def hydrate_snapshot(execution: AgenticWorkflowExecutionTable) -> dict:
    """Return the full immutable payload, falling back to legacy inline JSON."""
    record = getattr(execution, "snapshot_record", None)
    if record is not None and isinstance(record.payload, dict):
        return dict(record.payload)
    return dict(execution.config_snapshot) if isinstance(execution.config_snapshot, dict) else {}


async def attach_snapshot_async(
    session: AsyncSession, execution: AgenticWorkflowExecutionTable, payload: dict
) -> None:
    """Async equivalent used by MCP retry writes."""
    content_hash = payload.get(SNAPSHOT_HASH_KEY) or canonical_snapshot_hash(payload)
    result = await session.execute(
        select(AgenticWorkflowExecutionSnapshotTable).where(
            AgenticWorkflowExecutionSnapshotTable.content_hash == content_hash
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        record = AgenticWorkflowExecutionSnapshotTable(content_hash=content_hash, payload=dict(payload))
        session.add(record)
        await session.flush()
    execution.config_snapshot_id = record.id
    execution.config_snapshot = {"snapshot_id": record.id}


async def hydrate_snapshot_async(session: AsyncSession, execution: AgenticWorkflowExecutionTable) -> dict:
    """Hydrate an async execution reference, preserving the legacy fallback."""
    if execution.config_snapshot_id is not None:
        record = await session.get(AgenticWorkflowExecutionSnapshotTable, execution.config_snapshot_id)
        if record is not None and isinstance(record.payload, dict):
            return dict(record.payload)
    return dict(execution.config_snapshot) if isinstance(execution.config_snapshot, dict) else {}
