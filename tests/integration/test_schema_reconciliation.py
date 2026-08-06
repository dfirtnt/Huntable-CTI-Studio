"""End-to-end tests for schema drift detection and reconciliation.

These cover the parts that only exist against a real database: the structural diff
in src/database/schema_drift.py, the data-dependent safety preflights in
scripts/migrate_reconcile_schema.py, and the apply cycle.

They matter disproportionately. Both bugs found while building the reconciler --
a vector-exclusion guard that was silently dead (`Vector` vs `VECTOR`) and a crash
on column drift -- were caught by running against a real drifted schema, not by the
mocked unit tests, which passed clean through both. This module makes that run
repeatable.

Each test builds a scratch database whose shape reproduces the production defect:
tables that have their columns and id sequences but none of the primary keys,
foreign keys, or indexes models.py declares -- exactly what
`create_all(checkfirst=True)` leaves behind when a table already exists.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.migrate_reconcile_schema import apply_plan, build_plan  # noqa: E402
from src.database.schema_drift import detect_drift  # noqa: E402
from tests.utils.test_database_url import build_test_database_url  # noqa: E402

pytestmark = pytest.mark.integration

# Worker-scoped so a parallel run (-n) cannot have two workers dropping and creating
# the same database underneath each other.
SCRATCH_DB = "cti_scratch_reconcile_test_" + os.getenv("PYTEST_XDIST_WORKER", "main")

# Mirrors models.py column-for-column, but with no PRIMARY KEY, no FOREIGN KEY and
# no indexes -- the exact residue create_all(checkfirst=True) leaves on a table that
# was created by a hand-rolled migrate_* script.
DRIFTED_SCHEMA = """
CREATE TABLE sources (
    id serial,
    identifier varchar(100),
    name varchar(255),
    url varchar(1000)
);
ALTER TABLE sources ADD PRIMARY KEY (id);

CREATE TABLE source_checks (
    id serial,
    source_id integer NOT NULL,
    check_time timestamp NOT NULL,
    success boolean NOT NULL,
    method varchar(50) NOT NULL,
    articles_found integer NOT NULL,
    response_time double precision,
    error_message text,
    check_metadata json NOT NULL
);

INSERT INTO sources (identifier, name, url)
VALUES ('s1', 'Source One', 'http://a'), ('s2', 'Source Two', 'http://b');

INSERT INTO source_checks (source_id, check_time, success, method, articles_found, check_metadata)
SELECT (i % 2) + 1, now(), true, 'rss', 3, '{}'::json FROM generate_series(1, 50) i;
"""


def _sync_base_url() -> str:
    """Base URL with a sync driver.

    build_test_database_url returns TEST_DATABASE_URL verbatim when it is set,
    ignoring asyncpg=False -- and the test harness sets it to the +asyncpg form.
    These tests use the sync Inspector API, so force the driver here.
    """
    url = build_test_database_url(asyncpg=False)
    return url.replace("+asyncpg", "").rsplit("/", 1)[0]


def _admin_url() -> str:
    return _sync_base_url() + "/postgres"


def _scratch_url() -> str:
    return _sync_base_url() + "/" + SCRATCH_DB


@pytest.fixture
def drifted_engine():
    """A scratch database whose schema reproduces the production drift."""
    admin = create_engine(_admin_url(), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))
        conn.execute(text(f"CREATE DATABASE {SCRATCH_DB}"))

    engine = create_engine(_scratch_url())
    with engine.begin() as conn:
        for statement in filter(None, (s.strip() for s in DRIFTED_SCHEMA.split(";"))):
            conn.execute(text(statement))

    try:
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :db AND pid <> pg_backend_pid()"
                ),
                {"db": SCRATCH_DB},
            )
            conn.execute(text(f"DROP DATABASE IF EXISTS {SCRATCH_DB}"))
        admin.dispose()


def _constraint_count(engine, table: str, contype: str) -> int:
    with engine.connect() as conn:
        return int(
            conn.execute(
                # CAST(), not `:t::regclass` -- the `::` cast collides with bind-param syntax.
                text("SELECT count(*) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) AND contype = :c"),
                {"t": table, "c": contype},
            ).scalar()
            or 0
        )


def _index_names(engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname='public' AND tablename = :t"),
            {"t": table},
        )
        return {r[0] for r in rows}


class TestDetectDrift:
    """The structural diff must see what create_all silently skipped."""

    def test_detects_missing_primary_key(self, drifted_engine):
        report = detect_drift(drifted_engine)
        assert "source_checks" in report.missing_primary_keys

    def test_detects_missing_indexes(self, drifted_engine):
        report = detect_drift(drifted_engine)
        missing = {cols for table, cols in report.missing_indexes if table == "source_checks"}
        assert ("source_id",) in missing
        assert ("check_time",) in missing

    def test_detects_missing_foreign_key(self, drifted_engine):
        report = detect_drift(drifted_engine)
        assert ("source_checks", ("source_id",), "sources") in report.missing_foreign_keys

    def test_detects_missing_columns_without_crashing(self, drifted_engine):
        """Column drift must be reported, not raise -- it crashed the planner once."""
        report = detect_drift(drifted_engine)
        missing = {column for table, column in report.missing_columns if table == "sources"}
        assert "active" in missing  # declared in models.py, absent from the scratch table

    def test_reports_drift(self, drifted_engine):
        report = detect_drift(drifted_engine)
        assert report.has_drift() is True
        assert "primary key(s)" in report.summary()

    def test_never_proposes_a_btree_over_a_vector_column(self, drifted_engine):
        """A B-tree over Vector(768) breaks every INSERT; it must never be proposed."""
        report = detect_drift(drifted_engine)
        proposed = {cols for _, cols in report.missing_indexes}
        assert ("embedding",) not in proposed
        assert ("logsource_embedding",) not in proposed


class TestPreflights:
    """The preflights are what stand between an apply and a broken table."""

    def test_orphan_rows_block_the_foreign_key(self, drifted_engine):
        with drifted_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO source_checks (source_id, check_time, success, method, "
                    "articles_found, check_metadata) VALUES (999, now(), true, 'rss', 0, '{}'::json)"
                )
            )
        plan = build_plan(drifted_engine)
        blocked = " ".join(reason for table, reason in plan.blocked if table == "source_checks")
        assert "orphan" in blocked
        assert not any(table == "source_checks" for table, _ in plan.foreign_keys)

    def test_clean_data_allows_the_foreign_key(self, drifted_engine):
        plan = build_plan(drifted_engine)
        statements = " ".join(s for t, s in plan.foreign_keys if t == "source_checks")
        assert "REFERENCES" in statements

    def test_duplicate_ids_block_the_primary_key(self, drifted_engine):
        with drifted_engine.begin() as conn:
            # Force a duplicate id, which ADD PRIMARY KEY could not survive.
            conn.execute(text("UPDATE source_checks SET id = 1 WHERE id = 2"))
        plan = build_plan(drifted_engine)
        blocked = " ".join(reason for table, reason in plan.blocked if table == "source_checks")
        assert "PRIMARY KEY blocked" in blocked
        assert not any(table == "source_checks" for table, _ in plan.primary_keys)

    def test_duplicate_values_block_a_unique_index(self, drifted_engine):
        """A failed CREATE UNIQUE INDEX CONCURRENTLY leaves an INVALID index behind."""
        with drifted_engine.begin() as conn:
            conn.execute(text("UPDATE sources SET identifier = 'dup'"))
        plan = build_plan(drifted_engine)
        blocked = " ".join(reason for table, reason in plan.blocked if table == "sources")
        assert "UNIQUE INDEX" in blocked and "duplicated" in blocked


class TestApplyCycle:
    """Apply creates the safe objects, and a second pass has nothing left to do."""

    def test_apply_creates_primary_key_and_indexes(self, drifted_engine):
        assert _constraint_count(drifted_engine, "source_checks", "p") == 0

        plan = build_plan(drifted_engine)
        assert apply_plan(drifted_engine, plan, include_foreign_keys=False) is True

        assert _constraint_count(drifted_engine, "source_checks", "p") == 1
        indexes = _index_names(drifted_engine, "source_checks")
        assert "ix_source_checks_source_id" in indexes
        assert "ix_source_checks_check_time" in indexes

    def test_apply_creates_foreign_keys_when_requested(self, drifted_engine):
        assert _constraint_count(drifted_engine, "source_checks", "f") == 0

        plan = build_plan(drifted_engine)
        assert apply_plan(drifted_engine, plan, include_foreign_keys=True) is True

        assert _constraint_count(drifted_engine, "source_checks", "f") == 1

    def test_foreign_keys_are_withheld_without_the_flag(self, drifted_engine):
        plan = build_plan(drifted_engine)
        apply_plan(drifted_engine, plan, include_foreign_keys=False)
        assert _constraint_count(drifted_engine, "source_checks", "f") == 0

    def test_second_run_is_idempotent(self, drifted_engine):
        plan = build_plan(drifted_engine)
        apply_plan(drifted_engine, plan, include_foreign_keys=True)

        report = detect_drift(drifted_engine)
        assert "source_checks" not in report.missing_primary_keys
        assert not [cols for table, cols in report.missing_indexes if table == "source_checks"]
        assert not [f for f in report.missing_foreign_keys if f[0] == "source_checks"]

        replan = build_plan(drifted_engine)
        assert not [s for t, s in replan.primary_keys if t == "source_checks"]
        assert not [s for t, s in replan.indexes if t == "source_checks"]
        assert not [s for t, s in replan.foreign_keys if t == "source_checks"]

    def test_applied_foreign_key_actually_rejects_an_orphan(self, drifted_engine):
        """The point of the FK is that new orphans become impossible."""
        plan = build_plan(drifted_engine)
        apply_plan(drifted_engine, plan, include_foreign_keys=True)

        with pytest.raises(Exception, match="violates foreign key constraint"):
            with drifted_engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO source_checks (source_id, check_time, success, method, "
                        "articles_found, check_metadata) VALUES (999, now(), true, 'rss', 0, '{}'::json)"
                    )
                )
