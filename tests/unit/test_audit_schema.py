"""Unit tests for enterprise audit schema contracts."""

from __future__ import annotations

import pytest

from src.database.audit_schema import AUDIT_REQUIRED_INDEXES, missing_audit_schema_objects
from src.database.models import AuditEventTable

pytestmark = pytest.mark.unit


def test_audit_event_table_has_required_columns():
    columns = AuditEventTable.__table__.columns

    assert AuditEventTable.__tablename__ == "audit_events"
    for column_name in (
        "id",
        "created_at",
        "request_id",
        "actor_type",
        "actor_id",
        "actor_email",
        "actor_roles",
        "source_ip",
        "user_agent",
        "action",
        "target_type",
        "target_id",
        "status",
        "summary",
        "metadata",
        "before_hash",
        "after_hash",
        "error_code",
    ):
        assert column_name in columns


def test_audit_metadata_column_uses_non_reserved_python_attribute():
    assert "metadata" in AuditEventTable.__table__.columns
    assert hasattr(AuditEventTable, "event_metadata")
    assert AuditEventTable.event_metadata.name == "metadata"


def test_audit_event_table_declares_required_indexes():
    index_names = {index.name for index in AuditEventTable.__table__.indexes}

    assert set(AUDIT_REQUIRED_INDEXES).issubset(index_names)


def test_missing_audit_schema_objects_names_missing_table_and_indexes():
    missing = missing_audit_schema_objects(table_exists=False, existing_indexes=())

    assert "audit_events table" in missing
    assert "audit_events index ix_audit_events_created_at" in missing
    assert "audit_events index ix_audit_events_target_type_target_id" in missing


def test_missing_audit_schema_objects_passes_when_all_required_objects_exist():
    missing = missing_audit_schema_objects(table_exists=True, existing_indexes=AUDIT_REQUIRED_INDEXES)

    assert missing == []
