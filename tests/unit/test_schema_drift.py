"""Tests for src/database/schema_drift.py.

This detector is what makes create_all's silent drift visible. `create_all` uses
checkfirst=True, so it skips existing tables and never reconciles their constraints
or indexes -- which is how 25 of 29 tables lost their primary keys, foreign keys,
and indexes without a single error being logged.

Two properties matter most and are covered here:

* Vector columns are never proposed for a B-tree index. A B-tree over Vector(768)
  exceeds PostgreSQL's 2704-byte row limit and raises ProgramLimitExceeded on every
  INSERT (scripts/migrate_pgvector_indexes.py exists to remove exactly those).
* log_drift never raises. It runs during startup; a diagnostic that can take the
  app down is worse than the drift it reports.
"""

from __future__ import annotations

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Index, Integer, MetaData, String, Table

from src.database.schema_drift import (
    DriftReport,
    declared_indexes,
    is_vector_column,
    live_index_coverage,
    log_drift,
)

pytestmark = pytest.mark.unit


class TestIsVectorColumn:
    """pgvector's type name renders as VECTOR, not Vector -- match case-insensitively."""

    def test_vector_detected(self):
        assert is_vector_column(Column("embedding", Vector(768))) is True

    def test_ordinary_columns_not_detected(self):
        assert is_vector_column(Column("id", Integer)) is False
        assert is_vector_column(Column("name", String(50))) is False


class TestDeclaredIndexes:
    def test_collects_column_level_index_flag(self):
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("source_id", Integer, index=True),
        )
        assert ("source_id",) in declared_indexes(table)

    def test_reports_uniqueness(self):
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("url", String(255), index=True, unique=True),
            Column("status", String(50), index=True),
        )
        declared = declared_indexes(table)
        assert declared[("url",)] is True
        assert declared[("status",)] is False

    def test_excludes_vector_columns(self):
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("embedding", Vector(768), index=True),
            Column("title", String(255), index=True),
        )
        declared = declared_indexes(table)
        assert ("embedding",) not in declared
        assert ("title",) in declared

    def test_excludes_composite_index_containing_a_vector(self):
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("embedding", Vector(768)),
            Column("kind", String(50)),
        )
        Index("ix_t_kind_embedding", table.c.kind, table.c.embedding)
        assert declared_indexes(table) == {}


class _FakeInspector:
    def __init__(self, indexes=None, unique_constraints=None):
        self._indexes = indexes or []
        self._unique = unique_constraints or []

    def get_indexes(self, table_name, schema=None):
        return self._indexes

    def get_unique_constraints(self, table_name, schema=None):
        return self._unique


class TestLiveIndexCoverage:
    def test_primary_key_counts_as_covered(self):
        assert ("id",) in live_index_coverage(_FakeInspector(), "t", {"id"})

    def test_composite_primary_key_sorted(self):
        assert ("a", "b") in live_index_coverage(_FakeInspector(), "t", {"b", "a"})

    def test_existing_indexes_and_unique_constraints_count(self):
        inspector = _FakeInspector(
            indexes=[{"column_names": ["source_id"]}],
            unique_constraints=[{"column_names": ["canonical_url"]}],
        )
        covered = live_index_coverage(inspector, "t", set())
        assert ("source_id",) in covered
        assert ("canonical_url",) in covered

    def test_absent_index_not_covered(self):
        assert ("check_time",) not in live_index_coverage(_FakeInspector(), "t", {"id"})


class TestDriftReport:
    def test_clean_report_has_no_drift(self):
        report = DriftReport()
        assert report.has_drift() is False
        assert report.total() == 0
        assert report.summary() == "none"

    def test_total_counts_every_category(self):
        report = DriftReport(
            missing_tables=["a"],
            missing_primary_keys=["b"],
            missing_columns=[("c", "col")],
            missing_indexes=[("d", ("x",))],
            missing_foreign_keys=[("e", ("y",), "parent")],
        )
        assert report.total() == 5
        assert report.has_drift() is True

    def test_summary_names_each_populated_category(self):
        report = DriftReport(missing_primary_keys=["a", "b"], missing_indexes=[("c", ("x",))])
        summary = report.summary()
        assert "2 primary key(s)" in summary
        assert "1 index(es)" in summary
        assert "table(s)" not in summary


class TestLogDriftNeverRaises:
    """log_drift runs at startup. It must degrade to a warning, never propagate."""

    def test_returns_empty_report_on_broken_bind(self, caplog):
        class Exploding:
            pass

        report = log_drift(Exploding())  # not a valid SQLAlchemy bind
        assert report.has_drift() is False
        assert any("failed to run" in record.message for record in caplog.records)

    def test_logs_error_when_drift_present(self, caplog, monkeypatch):
        import src.database.schema_drift as module

        monkeypatch.setattr(
            module,
            "detect_drift",
            lambda bind: DriftReport(missing_primary_keys=["source_checks"]),
        )
        with caplog.at_level("ERROR"):
            report = log_drift(object())
        assert report.has_drift() is True
        assert any("SCHEMA DRIFT DETECTED" in record.message for record in caplog.records)
        assert any("NO PRIMARY KEY" in record.message for record in caplog.records)
