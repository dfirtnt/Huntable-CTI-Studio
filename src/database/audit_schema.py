"""Audit schema constants and validation helpers."""

from __future__ import annotations

AUDIT_TABLE_NAME = "audit_events"

AUDIT_REQUIRED_INDEXES = (
    "ix_audit_events_created_at",
    "ix_audit_events_actor_id",
    "ix_audit_events_action",
    "ix_audit_events_request_id",
    "ix_audit_events_target_type_target_id",
)

AUDIT_INDEX_DDLS = (
    "CREATE INDEX IF NOT EXISTS ix_audit_events_created_at ON audit_events (created_at)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_actor_id ON audit_events (actor_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_action ON audit_events (action)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_request_id ON audit_events (request_id)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_target_type_target_id ON audit_events (target_type, target_id)",
)


def missing_audit_schema_objects(*, table_exists: bool, existing_indexes: tuple[str, ...] | list[str]) -> list[str]:
    """Return required audit schema objects missing from the current database."""
    existing = set(existing_indexes)
    missing: list[str] = []
    if not table_exists:
        missing.append("audit_events table")
    for index_name in AUDIT_REQUIRED_INDEXES:
        if index_name not in existing:
            missing.append(f"audit_events index {index_name}")
    return missing
