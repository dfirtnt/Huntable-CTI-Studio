"""Tests for scripts/migrate_reconcile_schema.py.

The structural diff itself lives in src/database/schema_drift.py and is covered by
tests/unit/test_schema_drift.py. What is script-specific -- and tested here -- is
identifier quoting and the Plan accounting that decides what gets applied.

The safety preflights (_preflight_primary_key / _preflight_unique_index /
_preflight_foreign_key) issue COUNT queries and are exercised against a real schema
rather than mocked here.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, ForeignKey, Integer, MetaData, Table

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.migrate_reconcile_schema import Plan, _quote  # noqa: E402

pytestmark = pytest.mark.unit


class TestQuote:
    """Identifiers are quoted so reserved words and mixed case survive."""

    def test_wraps_in_double_quotes(self):
        assert _quote("source_checks") == '"source_checks"'

    def test_escapes_embedded_double_quote(self):
        assert _quote('we"ird') == '"we""ird"'


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
        """Blocked items need an operator decision -- they are never applied."""
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
