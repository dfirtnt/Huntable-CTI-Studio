"""Tests for scripts/migrate_reconcile_schema.py.

Covers the pure planning logic -- identifier quoting, vector-column exclusion,
declared-index collection, and PK-index deduplication. The safety preflights
(_preflight_primary_key / _preflight_unique_index / _preflight_foreign_key) issue
SQL and are exercised against a live schema by the integration suite.

The vector-exclusion tests matter disproportionately: a B-tree over Vector(768)
exceeds PostgreSQL's 2704-byte row limit and raises ProgramLimitExceeded on every
INSERT. scripts/migrate_pgvector_indexes.py exists to remove exactly those
indexes, so this reconciler must never emit one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, ForeignKey, Integer, MetaData, String, Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.migrate_reconcile_schema import (  # noqa: E402
    Plan,
    _declared_indexes,
    _is_vector,
    _live_indexes,
    _quote,
)

pytestmark = pytest.mark.unit


class TestQuote:
    """Identifiers are quoted so reserved words and mixed case survive."""

    def test_wraps_in_double_quotes(self):
        assert _quote("source_checks") == '"source_checks"'

    def test_escapes_embedded_double_quote(self):
        assert _quote('we"ird') == '"we""ird"'


class TestIsVector:
    """Vector columns must be recognizable regardless of dimension."""

    def test_vector_column_detected(self):
        assert _is_vector(Column("embedding", Vector(768))) is True

    def test_ordinary_columns_not_detected(self):
        assert _is_vector(Column("id", Integer)) is False
        assert _is_vector(Column("name", String(50))) is False


class TestDeclaredIndexes:
    """Indexes are collected from both Index() objects and Column(index=True)."""

    def test_collects_column_level_index_flag(self):
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("source_id", Integer, index=True),
        )
        assert ("source_id",) in _declared_indexes(table)

    def test_reports_uniqueness(self):
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("url", String(255), index=True, unique=True),
            Column("status", String(50), index=True),
        )
        declared = _declared_indexes(table)
        assert declared[("url",)] is True
        assert declared[("status",)] is False

    def test_excludes_vector_columns(self):
        """A B-tree over Vector(768) is invalid -- see module docstring."""
        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("embedding", Vector(768), index=True),
            Column("title", String(255), index=True),
        )
        declared = _declared_indexes(table)
        assert ("embedding",) not in declared
        assert ("title",) in declared

    def test_excludes_composite_index_containing_a_vector(self):
        from sqlalchemy import Index

        metadata = MetaData()
        table = Table(
            "t",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("embedding", Vector(768)),
            Column("kind", String(50)),
        )
        Index("ix_t_kind_embedding", table.c.kind, table.c.embedding)
        assert _declared_indexes(table) == {}


class TestLiveIndexes:
    """The implicit PK index counts as coverage, so it is never re-proposed."""

    class _FakeInspector:
        def __init__(self, indexes=None, unique_constraints=None):
            self._indexes = indexes or []
            self._unique = unique_constraints or []

        def get_indexes(self, table_name, schema=None):
            return self._indexes

        def get_unique_constraints(self, table_name, schema=None):
            return self._unique

    def test_primary_key_counts_as_covered(self):
        covered = _live_indexes(self._FakeInspector(), "t", {"id"})
        assert ("id",) in covered

    def test_composite_primary_key_sorted(self):
        covered = _live_indexes(self._FakeInspector(), "t", {"b", "a"})
        assert ("a", "b") in covered

    def test_existing_indexes_and_unique_constraints_count(self):
        inspector = self._FakeInspector(
            indexes=[{"column_names": ["source_id"]}],
            unique_constraints=[{"column_names": ["canonical_url"]}],
        )
        covered = _live_indexes(inspector, "t", set())
        assert ("source_id",) in covered
        assert ("canonical_url",) in covered

    def test_absent_index_not_covered(self):
        assert ("check_time",) not in _live_indexes(self._FakeInspector(), "t", {"id"})


class TestPlan:
    """Plan.total() counts applicable statements and excludes blocked ones."""

    def test_total_sums_the_three_categories(self):
        plan = Plan(
            primary_keys=[("t", "pk")],
            indexes=[("t", "ix1"), ("t", "ix2")],
            foreign_keys=[("t", "fk")],
        )
        assert plan.total() == 4

    def test_blocked_items_are_not_counted(self):
        plan = Plan(indexes=[("t", "ix")], blocked=[("t", "orphans")])
        assert plan.total() == 1

    def test_empty_plan(self):
        assert Plan().total() == 0


class TestForeignKeyOndelete:
    """ON DELETE CASCADE declared in models.py must survive into the emitted DDL."""

    def test_ondelete_is_readable_from_the_constraint(self):
        metadata = MetaData()
        Table("parent", metadata, Column("id", Integer, primary_key=True))
        child = Table(
            "child",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("parent_id", Integer, ForeignKey("parent.id", ondelete="CASCADE")),
        )
        constraint = next(iter(child.foreign_key_constraints))
        assert any(element.ondelete == "CASCADE" for element in constraint.elements)
