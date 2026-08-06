#!/usr/bin/env python3
"""Migration: reconcile live database schema against src/database/models.py.

Why
---
`Base.metadata.create_all` (manager.py:107, async_manager.py:150) defaults to
checkfirst=True. It skips any table that already exists and never reconciles an
existing table's constraints or indexes. Tables created by the hand-rolled
scripts/migrate_*.py helpers therefore keep their columns and id sequences but
silently lose the primary keys, foreign keys, and indexes that models.py
declares -- permanently, because create_all will never revisit them.

A 2026-08-06 audit found 25 of 29 declared tables drifted: 18 tables with no
primary key at all (source_checks at 57k rows, sigma_rules at 3.7k), 19 of 22
declared foreign keys absent, and 36 live indexes against 254 declared.

This script diffs models.py against the live schema and emits the missing DDL.
models.py is the contract source of truth (see CLAUDE.md); the database is
reconciled toward it, never the reverse.

Safety
------
Report-only by default -- it never writes unless --apply is passed.

- Indexes are created CONCURRENTLY so they do not block writes.
- Vector columns are always excluded. A B-tree over Vector(768) exceeds the
  2704-byte row limit and raises ProgramLimitExceeded on every INSERT. See
  scripts/migrate_pgvector_indexes.py, which owns HNSW indexes for those.
- Primary keys are preflighted for duplicate and NULL values, and skipped when
  the column cannot support one.
- Foreign keys are preflighted for orphan rows and require an explicit
  --include-foreign-keys flag, because adding one to a table with orphans fails
  and the remedy is deleting rows -- an operator decision, not a migration's.

Usage
-----
    python scripts/migrate_reconcile_schema.py              # report the drift
    python scripts/migrate_reconcile_schema.py --sql        # print DDL, run nothing
    python scripts/migrate_reconcile_schema.py --apply      # PKs + indexes
    python scripts/migrate_reconcile_schema.py --apply --include-foreign-keys

Idempotent: re-running after a successful apply reports no remaining drift.
Run this after any fresh create_all, database restore, or migrate_* script that
creates a table.
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

from src.database.models import Base

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


@dataclass
class Plan:
    """DDL statements to reconcile the schema, grouped by risk."""

    primary_keys: list[tuple[str, str]] = field(default_factory=list)
    indexes: list[tuple[str, str]] = field(default_factory=list)
    foreign_keys: list[tuple[str, str]] = field(default_factory=list)
    blocked: list[tuple[str, str]] = field(default_factory=list)

    def total(self) -> int:
        return len(self.primary_keys) + len(self.indexes) + len(self.foreign_keys)


def _is_vector(column) -> bool:
    """True for pgvector columns, which must never receive a B-tree index.

    pgvector's class is `Vector` but its SQLAlchemy type name renders as `VECTOR`,
    so match case-insensitively rather than on an exact spelling.
    """
    type_name = type(column.type).__name__
    return type_name.upper() in {"VECTOR", "HALFVEC", "SPARSEVEC", "BIT"}


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _declared_indexes(table) -> dict[tuple[str, ...], bool]:
    """Map column-tuple -> is_unique for every index models.py declares."""
    declared: dict[tuple[str, ...], bool] = {}
    for index in table.indexes:
        columns = tuple(c.name for c in index.columns)
        if any(_is_vector(c) for c in index.columns):
            continue
        declared[columns] = bool(index.unique)
    # Column(index=True) does not appear in table.indexes
    for column in table.columns:
        if column.index and not _is_vector(column):
            declared.setdefault((column.name,), bool(column.unique))
    return declared


def _live_indexes(inspector, table_name: str, live_pk: set[str]) -> set[tuple[str, ...]]:
    """Column-tuples already covered by an index, including the implicit PK index."""
    covered = {tuple(ix["column_names"]) for ix in inspector.get_indexes(table_name, schema="public")}
    covered |= {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table_name, schema="public")}
    if live_pk:
        covered.add(tuple(sorted(live_pk)))
    return covered


def _scalar(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql)).scalar() or 0)


def _preflight_primary_key(engine: Engine, table_name: str, columns: list[str]) -> str | None:
    """Return a human-readable reason the PK cannot be added, or None if safe."""
    column_list = ", ".join(_quote(c) for c in columns)
    null_predicate = " OR ".join(f"{_quote(c)} IS NULL" for c in columns)
    nulls = _scalar(engine, f"SELECT count(*) FROM {_quote(table_name)} WHERE {null_predicate}")
    if nulls:
        return f"{nulls} row(s) with NULL in ({', '.join(columns)})"
    duplicates = _scalar(
        engine,
        f"SELECT count(*) FROM (SELECT {column_list} FROM {_quote(table_name)} "
        f"GROUP BY {column_list} HAVING count(*) > 1) d",
    )
    if duplicates:
        return f"{duplicates} duplicated key value(s) in ({', '.join(columns)})"
    return None


def _preflight_unique_index(engine: Engine, table_name: str, columns: tuple[str, ...]) -> str | None:
    """Return a reason a UNIQUE index cannot be built, or None if safe.

    A failed CREATE UNIQUE INDEX CONCURRENTLY leaves an INVALID index behind that
    must be dropped by hand, so duplicates are caught before we ever emit the DDL.
    """
    column_list = ", ".join(_quote(c) for c in columns)
    duplicates = _scalar(
        engine,
        f"SELECT count(*) FROM (SELECT {column_list} FROM {_quote(table_name)} "
        f"GROUP BY {column_list} HAVING count(*) > 1) d",
    )
    if duplicates:
        return f"{duplicates} duplicated value(s) in ({', '.join(columns)})"
    return None


def _preflight_foreign_key(
    engine: Engine, table_name: str, columns: list[str], referred_table: str, referred_columns: list[str]
) -> str | None:
    """Return a reason the FK cannot be added (orphan rows), or None if safe."""
    join_predicate = " AND ".join(
        f"p.{_quote(parent)} = c.{_quote(child)}" for child, parent in zip(columns, referred_columns, strict=True)
    )
    not_null = " AND ".join(f"c.{_quote(c)} IS NOT NULL" for c in columns)
    orphans = _scalar(
        engine,
        f"SELECT count(*) FROM {_quote(table_name)} c "
        f"LEFT JOIN {_quote(referred_table)} p ON {join_predicate} "
        f"WHERE {not_null} AND p.{_quote(referred_columns[0])} IS NULL",
    )
    if orphans:
        return f"{orphans} orphan row(s) referencing a missing {referred_table}"
    return None


def build_plan(engine: Engine) -> Plan:
    inspector = inspect(engine)
    live_tables = set(inspector.get_table_names(schema="public"))
    plan = Plan()

    for table_name in sorted(Base.metadata.tables):
        if table_name not in live_tables:
            logger.warning("  table %s declared but absent from the database -- create_all will handle it", table_name)
            continue

        table = Base.metadata.tables[table_name]
        live_pk = set(inspector.get_pk_constraint(table_name, schema="public").get("constrained_columns") or [])
        live_columns = {c["name"] for c in inspector.get_columns(table_name, schema="public")}

        # Columns can drift too, not just constraints. Indexing a column that does
        # not exist is an error, and preflighting one crashes the whole run, so
        # surface the gap and skip anything that depends on it.
        def _present(columns: "list[str] | tuple[str, ...]", _live: set[str] = live_columns) -> bool:
            return all(c in _live for c in columns)

        missing_columns = sorted({c.name for c in table.columns} - live_columns)
        if missing_columns:
            plan.blocked.append(
                (table_name, f"COLUMNS declared in models.py but absent from the table: {', '.join(missing_columns)}")
            )

        # --- primary key ---
        declared_pk = [c.name for c in table.primary_key.columns]
        if declared_pk and not live_pk and not _present(declared_pk):
            plan.blocked.append((table_name, f"PRIMARY KEY blocked: column(s) {', '.join(declared_pk)} absent"))
        elif declared_pk and not live_pk:
            reason = _preflight_primary_key(engine, table_name, declared_pk)
            columns = ", ".join(_quote(c) for c in declared_pk)
            statement = (
                f"ALTER TABLE {_quote(table_name)} "
                f"ADD CONSTRAINT {_quote(table_name + '_pkey')} PRIMARY KEY ({columns});"
            )
            if reason:
                plan.blocked.append((table_name, f"PRIMARY KEY blocked: {reason}"))
            else:
                plan.primary_keys.append((table_name, statement))
                live_pk = set(declared_pk)  # so the implicit index is not also proposed

        # --- indexes ---
        covered = _live_indexes(inspector, table_name, live_pk)
        for columns, is_unique in sorted(_declared_indexes(table).items()):
            if columns in covered or not _present(columns):
                continue
            index_name = f"ix_{table_name}_{'_'.join(columns)}"
            if is_unique:
                reason = _preflight_unique_index(engine, table_name, columns)
                if reason:
                    plan.blocked.append((table_name, f"UNIQUE INDEX on ({', '.join(columns)}) blocked: {reason}"))
                    continue
            unique = "UNIQUE " if is_unique else ""
            column_list = ", ".join(_quote(c) for c in columns)
            plan.indexes.append(
                (
                    table_name,
                    f"CREATE {unique}INDEX CONCURRENTLY IF NOT EXISTS {_quote(index_name)} "
                    f"ON {_quote(table_name)} ({column_list});",
                )
            )

        # --- foreign keys ---
        live_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"])
            for fk in inspector.get_foreign_keys(table_name, schema="public")
        }
        for constraint in table.foreign_key_constraints:
            columns = list(constraint.column_keys)
            referred_table = constraint.referred_table.name
            if (tuple(columns), referred_table) in live_fks:
                continue
            referred_columns = [element.column.name for element in constraint.elements]
            if referred_table not in live_tables:
                plan.blocked.append((table_name, f"FOREIGN KEY blocked: referred table {referred_table} is absent"))
                continue
            referred_live = {c["name"] for c in inspector.get_columns(referred_table, schema="public")}
            if not _present(columns) or not all(c in referred_live for c in referred_columns):
                plan.blocked.append(
                    (table_name, f"FOREIGN KEY ({', '.join(columns)}) -> {referred_table} blocked: column(s) absent")
                )
                continue
            reason = _preflight_foreign_key(engine, table_name, columns, referred_table, referred_columns)
            if reason:
                plan.blocked.append(
                    (table_name, f"FOREIGN KEY ({', '.join(columns)}) -> {referred_table} blocked: {reason}")
                )
                continue
            ondelete = ""
            for element in constraint.elements:
                if element.ondelete:
                    ondelete = f" ON DELETE {element.ondelete.upper()}"
                    break
            constraint_name = constraint.name or f"{table_name}_{'_'.join(columns)}_fkey"
            plan.foreign_keys.append(
                (
                    table_name,
                    f"ALTER TABLE {_quote(table_name)} ADD CONSTRAINT {_quote(constraint_name)} "
                    f"FOREIGN KEY ({', '.join(_quote(c) for c in columns)}) "
                    f"REFERENCES {_quote(referred_table)} "
                    f"({', '.join(_quote(c) for c in referred_columns)}){ondelete};",
                )
            )

    return plan


def report(plan: Plan, include_foreign_keys: bool) -> None:
    logger.info("")
    logger.info("=" * 78)
    logger.info("SCHEMA DRIFT: %d statement(s) needed, %d blocked", plan.total(), len(plan.blocked))
    logger.info("=" * 78)

    for label, statements in (
        ("PRIMARY KEYS", plan.primary_keys),
        ("INDEXES", plan.indexes),
        ("FOREIGN KEYS", plan.foreign_keys),
    ):
        if not statements:
            continue
        suffix = "" if label != "FOREIGN KEYS" or include_foreign_keys else "  [requires --include-foreign-keys]"
        logger.info("")
        logger.info("--- %s (%d)%s", label, len(statements), suffix)
        for _, statement in statements:
            logger.info("  %s", statement)

    if plan.blocked:
        logger.info("")
        logger.info("--- BLOCKED (%d) -- needs an operator decision, not applied", len(plan.blocked))
        for table_name, reason in plan.blocked:
            logger.info("  %s: %s", table_name, reason)


def apply_plan(engine: Engine, plan: Plan, include_foreign_keys: bool) -> bool:
    statements = list(plan.primary_keys) + list(plan.indexes)
    if include_foreign_keys:
        statements += plan.foreign_keys

    if not statements:
        logger.info("")
        logger.info("Nothing to apply.")
        return True

    logger.info("")
    logger.info("Applying %d statement(s)...", len(statements))

    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    failures = 0
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for table_name, statement in statements:
            try:
                conn.execute(text(statement))
                logger.info("  ok    %s", statement)
            except Exception as exc:  # noqa: BLE001 - report and continue, one bad table must not abort the rest
                failures += 1
                logger.error("  FAIL  %s (%s)", statement, str(exc).splitlines()[0])
                # A failed CONCURRENTLY build leaves an INVALID index that blocks retries.
                if "CONCURRENTLY" in statement:
                    index_name = statement.split('"')[1]
                    try:
                        conn.execute(text(f"DROP INDEX IF EXISTS {_quote(index_name)}"))
                        logger.info("        cleaned up invalid index %s", index_name)
                    except Exception as cleanup_exc:  # noqa: BLE001
                        logger.error("        could not clean up %s: %s", index_name, cleanup_exc)

    logger.info("")
    if failures:
        logger.error("Completed with %d failure(s) of %d statement(s)", failures, len(statements))
        return False
    logger.info("Applied %d statement(s) successfully", len(statements))
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Reconcile the live database schema against models.py")
    parser.add_argument("--apply", action="store_true", help="execute the DDL (default is report only)")
    parser.add_argument("--sql", action="store_true", help="print the DDL to stdout and exit")
    parser.add_argument(
        "--include-foreign-keys",
        action="store_true",
        help="also add foreign keys (only those with no orphan rows)",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return 1
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")

    engine = create_engine(database_url)
    plan = build_plan(engine)

    if args.sql:
        statements = list(plan.primary_keys) + list(plan.indexes)
        if args.include_foreign_keys:
            statements += plan.foreign_keys
        for _, statement in statements:
            print(statement)
        return 0

    report(plan, args.include_foreign_keys)

    if not args.apply:
        logger.info("")
        logger.info("Report only. Re-run with --apply to execute.")
        return 0

    return 0 if apply_plan(engine, plan, args.include_foreign_keys) else 1


if __name__ == "__main__":
    sys.exit(main())
