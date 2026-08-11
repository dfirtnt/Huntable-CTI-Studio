"""Contract tests for the execution-snapshot schema migration plan."""

from __future__ import annotations

import pytest

from scripts.migrate_execution_snapshot_schema import (
    EXECUTIONS_TABLE,
    SNAPSHOT_COLUMN,
    SNAPSHOT_FOREIGN_KEY,
    SNAPSHOT_INDEX,
    SNAPSHOTS_TABLE,
    build_plan,
)

pytestmark = pytest.mark.unit


class Inspector:
    def __init__(self, *, snapshots=True, column=True, index=True, foreign_key=True):
        self.snapshots = snapshots
        self.column = column
        self.index = index
        self.foreign_key = foreign_key

    def get_table_names(self, schema):
        assert schema == "public"
        return [EXECUTIONS_TABLE] + ([SNAPSHOTS_TABLE] if self.snapshots else [])

    def get_columns(self, table, schema):
        assert (table, schema) == (EXECUTIONS_TABLE, "public")
        return [{"name": SNAPSHOT_COLUMN}] if self.column else []

    def get_indexes(self, table, schema):
        assert (table, schema) == (EXECUTIONS_TABLE, "public")
        return [{"name": SNAPSHOT_INDEX}] if self.index else []

    def get_foreign_keys(self, table, schema):
        assert (table, schema) == (EXECUTIONS_TABLE, "public")
        if not self.foreign_key:
            return []
        return [
            {"constrained_columns": [SNAPSHOT_COLUMN], "referred_table": SNAPSHOTS_TABLE, "name": SNAPSHOT_FOREIGN_KEY}
        ]


def test_current_schema_has_no_pending_ddl():
    assert build_plan(Inspector()).total() == 0


def test_missing_schema_plans_all_non_destructive_steps():
    plan = build_plan(Inspector(snapshots=False, column=False, index=False, foreign_key=False))

    assert plan.create_snapshot_table
    assert plan.add_snapshot_column
    assert plan.add_snapshot_index
    assert plan.add_snapshot_foreign_key


def test_existing_column_still_gets_missing_index_and_foreign_key():
    plan = build_plan(Inspector(index=False, foreign_key=False))

    assert not plan.create_snapshot_table
    assert not plan.add_snapshot_column
    assert plan.add_snapshot_index
    assert plan.add_snapshot_foreign_key
