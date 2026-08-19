#!/usr/bin/env python3
"""Provision the content-addressed execution-snapshot schema.

``Base.metadata.create_all()`` creates the new snapshot table on a fresh
database, but it does not add ``config_snapshot_id`` to an existing executions
table. This script closes that migration gap.

It is report-only by default. ``--apply`` creates the snapshot table, adds the
nullable execution reference, its concurrent index, and its foreign key. It
never changes execution snapshot payloads or deletes legacy inline JSON.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from src.database.models import AgenticWorkflowExecutionSnapshotTable, Base

EXECUTIONS_TABLE = "agentic_workflow_executions"
SNAPSHOTS_TABLE = "agentic_workflow_execution_snapshots"
SNAPSHOT_COLUMN = "config_snapshot_id"
SNAPSHOT_INDEX = "ix_agentic_workflow_executions_config_snapshot_id"
SNAPSHOT_FOREIGN_KEY = "fk_agentic_workflow_executions_config_snapshot_id"


@dataclass(frozen=True)
class SchemaPlan:
    """Missing, non-destructive DDL steps for the snapshot schema."""

    create_snapshot_table: bool
    add_snapshot_column: bool
    add_snapshot_index: bool
    add_snapshot_foreign_key: bool

    def total(self) -> int:
        return sum(vars(self).values())


def build_plan(inspector) -> SchemaPlan:
    """Compare the narrow snapshot contract with the live database schema."""
    tables = set(inspector.get_table_names(schema="public"))
    snapshots_exist = SNAPSHOTS_TABLE in tables
    executions_exist = EXECUTIONS_TABLE in tables
    if not executions_exist:
        raise RuntimeError(f"Required table {EXECUTIONS_TABLE} is absent")

    execution_columns = {column["name"] for column in inspector.get_columns(EXECUTIONS_TABLE, schema="public")}
    column_exists = SNAPSHOT_COLUMN in execution_columns
    index_names = {index["name"] for index in inspector.get_indexes(EXECUTIONS_TABLE, schema="public")}
    foreign_keys = inspector.get_foreign_keys(EXECUTIONS_TABLE, schema="public")
    foreign_key_exists = any(
        foreign_key["constrained_columns"] == [SNAPSHOT_COLUMN] and foreign_key["referred_table"] == SNAPSHOTS_TABLE
        for foreign_key in foreign_keys
    )
    return SchemaPlan(
        create_snapshot_table=not snapshots_exist,
        add_snapshot_column=not column_exists,
        add_snapshot_index=not column_exists or SNAPSHOT_INDEX not in index_names,
        add_snapshot_foreign_key=not foreign_key_exists,
    )


def report(plan: SchemaPlan) -> None:
    if plan.total() == 0:
        print("Execution snapshot schema is current.")
        return
    print("Execution snapshot schema needs:")
    for needed, description in (
        (plan.create_snapshot_table, f"create {SNAPSHOTS_TABLE}"),
        (plan.add_snapshot_column, f"add {EXECUTIONS_TABLE}.{SNAPSHOT_COLUMN}"),
        (plan.add_snapshot_index, f"create {SNAPSHOT_INDEX} concurrently"),
        (plan.add_snapshot_foreign_key, f"add foreign key {SNAPSHOT_FOREIGN_KEY}"),
    ):
        if needed:
            print(f"  - {description}")


def apply_plan(engine: Engine, plan: SchemaPlan) -> None:
    """Apply only missing DDL; payload and execution data remain untouched."""
    if plan.create_snapshot_table:
        Base.metadata.create_all(engine, tables=[AgenticWorkflowExecutionSnapshotTable.__table__])

    with engine.begin() as connection:
        if plan.add_snapshot_column:
            connection.execute(text(f"ALTER TABLE {EXECUTIONS_TABLE} ADD COLUMN {SNAPSHOT_COLUMN} INTEGER"))
        if plan.add_snapshot_foreign_key:
            connection.execute(
                text(
                    f"ALTER TABLE {EXECUTIONS_TABLE} ADD CONSTRAINT {SNAPSHOT_FOREIGN_KEY} "
                    f"FOREIGN KEY ({SNAPSHOT_COLUMN}) REFERENCES {SNAPSHOTS_TABLE}(id) ON DELETE RESTRICT"
                )
            )

    if plan.add_snapshot_index:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
            connection.execute(
                text(
                    f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {SNAPSHOT_INDEX} "
                    f"ON {EXECUTIONS_TABLE} ({SNAPSHOT_COLUMN})"
                )
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="execute DDL; the default is report-only")
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        parser.error("DATABASE_URL environment variable is required")
    engine = create_engine(database_url.replace("postgresql+asyncpg://", "postgresql://"))
    plan = build_plan(inspect(engine))
    report(plan)
    if args.apply and plan.total():
        apply_plan(engine, plan)
        print("Applied execution snapshot schema migration.")
    elif not args.apply and plan.total():
        print("Run again with --apply to execute this DDL.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
