"""Detect divergence between src/database/models.py and the live database schema.

Why this exists
---------------
`Base.metadata.create_all` defaults to ``checkfirst=True``: it skips any table that
already exists and never reconciles that table's constraints or indexes. A table
created by one of the hand-rolled ``scripts/migrate_*.py`` helpers therefore keeps
its columns and id sequence but silently loses every primary key, foreign key, and
index that models.py declares -- permanently, because create_all never revisits it.

An audit on 2026-08-06 found 25 of 29 declared tables drifted this way, including
18 tables with no primary key at all. Nothing surfaced it because create_all
reports success either way.

This module is the detector. It is deliberately **structural only**: it compares
declarations against catalog metadata and never scans table data, so it is cheap
enough to run on every startup. Remediation lives in
``scripts/migrate_reconcile_schema.py``, which adds the data-dependent safety
preflights (duplicates, NULLs, orphans) and emits the DDL.

Startup must never apply DDL itself. Both create_tables() paths already bound their
idempotent ALTERs with a short ``lock_timeout`` because a pending ACCESS EXCLUSIVE
request blocks all readers of a table and can freeze the app; and
``CREATE INDEX CONCURRENTLY`` cannot run inside a transaction at all. Detect and
report loudly -- let an operator choose when to reconcile.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy import inspect
from sqlalchemy.engine import Connection, Engine

from src.database.models import Base

logger = logging.getLogger(__name__)

# pgvector columns must never receive a B-tree index: a B-tree over Vector(768)
# exceeds PostgreSQL's 2704-byte row limit and raises ProgramLimitExceeded on every
# INSERT. scripts/migrate_pgvector_indexes.py owns HNSW indexes for these columns.
# The class is `Vector` but the SQLAlchemy type name renders as `VECTOR`, so this
# must match case-insensitively.
_VECTOR_TYPE_NAMES = {"VECTOR", "HALFVEC", "SPARSEVEC"}


@dataclass
class DriftReport:
    """Structural gaps between models.py and the live schema."""

    missing_tables: list[str] = field(default_factory=list)
    missing_primary_keys: list[str] = field(default_factory=list)
    missing_columns: list[tuple[str, str]] = field(default_factory=list)
    missing_indexes: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)
    missing_foreign_keys: list[tuple[str, tuple[str, ...], str]] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.missing_tables)
            + len(self.missing_primary_keys)
            + len(self.missing_columns)
            + len(self.missing_indexes)
            + len(self.missing_foreign_keys)
        )

    def has_drift(self) -> bool:
        return self.total() > 0

    def summary(self) -> str:
        """One-line summary suitable for a log record."""
        parts = []
        if self.missing_tables:
            parts.append(f"{len(self.missing_tables)} table(s)")
        if self.missing_primary_keys:
            parts.append(f"{len(self.missing_primary_keys)} primary key(s)")
        if self.missing_columns:
            parts.append(f"{len(self.missing_columns)} column(s)")
        if self.missing_indexes:
            parts.append(f"{len(self.missing_indexes)} index(es)")
        if self.missing_foreign_keys:
            parts.append(f"{len(self.missing_foreign_keys)} foreign key(s)")
        return ", ".join(parts) if parts else "none"


def is_vector_column(column) -> bool:
    """True for pgvector columns, which must never receive a B-tree index."""
    return type(column.type).__name__.upper() in _VECTOR_TYPE_NAMES


def declared_indexes(table) -> dict[tuple[str, ...], bool]:
    """Map column-tuple -> is_unique for every index models.py declares on a table."""
    declared: dict[tuple[str, ...], bool] = {}
    for index in table.indexes:
        if any(is_vector_column(c) for c in index.columns):
            continue
        declared[tuple(c.name for c in index.columns)] = bool(index.unique)
    # Column(index=True) never appears in table.indexes
    for column in table.columns:
        if column.index and not is_vector_column(column):
            declared.setdefault((column.name,), bool(column.unique))
    return declared


def live_index_coverage(inspector, table_name: str, live_pk: set[str]) -> set[tuple[str, ...]]:
    """Column-tuples already covered by an index, including the implicit PK index."""
    covered = {tuple(ix["column_names"]) for ix in inspector.get_indexes(table_name, schema="public")}
    covered |= {tuple(u["column_names"]) for u in inspector.get_unique_constraints(table_name, schema="public")}
    if live_pk:
        covered.add(tuple(sorted(live_pk)))
    return covered


def detect_drift(bind: Engine | Connection) -> DriftReport:
    """Compare models.py against the live schema. Catalog reads only -- no table scans.

    Accepts an Engine or an already-open Connection. Callers inside ``run_sync`` should
    pass the connection so the check does not take a second connection from the pool.
    """
    inspector = inspect(bind)
    live_tables = set(inspector.get_table_names(schema="public"))
    report = DriftReport()

    for table_name in sorted(Base.metadata.tables):
        if table_name not in live_tables:
            report.missing_tables.append(table_name)
            continue

        table = Base.metadata.tables[table_name]
        live_columns = {c["name"] for c in inspector.get_columns(table_name, schema="public")}
        live_pk = set(inspector.get_pk_constraint(table_name, schema="public").get("constrained_columns") or [])

        for column_name in sorted({c.name for c in table.columns} - live_columns):
            report.missing_columns.append((table_name, column_name))

        declared_pk = [c.name for c in table.primary_key.columns]
        if declared_pk and not live_pk:
            report.missing_primary_keys.append(table_name)
            live_pk = set(declared_pk)  # do not also report its implicit index

        covered = live_index_coverage(inspector, table_name, live_pk)
        for columns in sorted(declared_indexes(table)):
            if columns not in covered and all(c in live_columns for c in columns):
                report.missing_indexes.append((table_name, columns))

        live_fks = {
            (tuple(fk["constrained_columns"]), fk["referred_table"])
            for fk in inspector.get_foreign_keys(table_name, schema="public")
        }
        for constraint in table.foreign_key_constraints:
            key = (tuple(constraint.column_keys), constraint.referred_table.name)
            if key not in live_fks:
                report.missing_foreign_keys.append((table_name, key[0], key[1]))

    return report


def log_drift(bind: Engine | Connection) -> DriftReport:
    """Detect drift and log it loudly. Never raises -- a check must not break startup."""
    try:
        report = detect_drift(bind)
    except Exception as exc:  # noqa: BLE001 - a diagnostic must never take the app down
        logger.warning("Schema drift check failed to run: %s", exc)
        return DriftReport()

    if not report.has_drift():
        logger.info("Schema drift check: database matches models.py")
        return report

    # Severity split. Missing tables, primary keys, or columns are app-breaking and
    # invisible by design (create_all reports success while the schema is wrong) --
    # those stay a loud, itemized ERROR; silence is what let 25 of 29 tables drift
    # unnoticed. Missing indexes and foreign keys are an integrity/perf gap, not a
    # crash risk, and adding the FKs is commonly blocked by historical orphan rows
    # that need an operator decision -- so drift limited to those logs a single
    # WARNING instead of an ERROR wall on every boot.
    severe = report.missing_tables or report.missing_primary_keys or report.missing_columns
    if not severe:
        logger.warning(
            "Schema drift (non-fatal): database does not match models.py (%s). "
            "Run `python scripts/migrate_reconcile_schema.py --apply --include-foreign-keys` to reconcile.",
            report.summary(),
        )
        return report

    logger.error(
        "SCHEMA DRIFT DETECTED: database does not match models.py (%s). "
        "Run `python scripts/migrate_reconcile_schema.py` to review, then --apply to fix.",
        report.summary(),
    )
    for table_name in report.missing_primary_keys:
        logger.error("  %s: NO PRIMARY KEY", table_name)
    for table_name, column_name in report.missing_columns:
        logger.error("  %s: missing column %s", table_name, column_name)
    return report
