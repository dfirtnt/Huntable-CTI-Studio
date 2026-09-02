"""Version allocation must stay correct where the sequence is absent or behind.

The concurrency guarantee lives in `tests/integration/` against a real Postgres.
These cover the two branches that test cannot reach: a database the migration has
not run against yet (deploy ordering), and a sequence sitting at or below a
version already in the table (a restore, or a writer still running the old code).
Getting either wrong hands out a number the unique index would reject, turning
every config save into a 500.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.web.routes.workflow_config import _next_workflow_config_version

pytestmark = pytest.mark.unit


def _session(*, dialect: str | None, sequence_present: bool, max_version: int, nextval: int | None = None):
    """Session stub covering the two SQL probes and the max(version) ORM query."""
    session = MagicMock()
    session.bind = None if dialect is None else SimpleNamespace(dialect=SimpleNamespace(name=dialect))

    executed: list[str] = []

    def execute(statement, params=None):
        sql = str(statement)
        executed.append(sql)
        result = MagicMock()
        if "to_regclass" in sql:
            result.scalar.return_value = "agentic_workflow_config_version_seq" if sequence_present else None
        elif "nextval" in sql:
            result.scalar.return_value = nextval
        else:  # setval
            result.scalar.return_value = nextval
        return result

    session.execute.side_effect = execute
    session.query.return_value.scalar.return_value = max_version
    session.executed = executed
    return session


class TestSequenceAbsent:
    def test_falls_back_to_max_plus_one_before_the_migration_runs(self):
        """Safe to deploy the code ahead of the migration."""
        session = _session(dialect="postgresql", sequence_present=False, max_version=7967)

        assert _next_workflow_config_version(session) == 7968
        assert not any("nextval" in sql for sql in session.executed), "queried a sequence it had just found missing"

    def test_probes_with_to_regclass_rather_than_a_failing_nextval(self):
        """A missing relation aborts the transaction, which would drop the advisory lock."""
        session = _session(dialect="postgresql", sequence_present=False, max_version=1)

        _next_workflow_config_version(session)

        assert any("to_regclass" in sql for sql in session.executed)

    @pytest.mark.parametrize("dialect", ["sqlite", None])
    def test_non_postgres_backends_use_the_arithmetic_path(self, dialect):
        session = _session(dialect=dialect, sequence_present=True, max_version=41)

        assert _next_workflow_config_version(session) == 42
        assert session.executed == [], "issued Postgres-only SQL against a non-Postgres bind"

    def test_empty_table_starts_at_one(self):
        session = _session(dialect="postgresql", sequence_present=False, max_version=None)

        assert _next_workflow_config_version(session) == 1


class TestSequencePresent:
    def test_uses_the_allocated_value_when_it_is_ahead(self):
        session = _session(dialect="postgresql", sequence_present=True, max_version=7967, nextval=7968)

        assert _next_workflow_config_version(session) == 7968

    @pytest.mark.parametrize("allocated", [100, 7967])
    def test_realigns_past_rows_the_sequence_does_not_know_about(self, allocated):
        """A stale sequence would otherwise return a number the unique index rejects."""
        session = _session(dialect="postgresql", sequence_present=True, max_version=7967, nextval=allocated)

        assert _next_workflow_config_version(session) == 7968
        assert any("setval" in sql for sql in session.executed), "returned a fresh number without realigning"

    def test_never_returns_a_version_already_in_the_table(self):
        """The invariant the unique index enforces, checked on both branches."""
        for allocated in (1, 500, 7967, 7968, 90000):
            session = _session(dialect="postgresql", sequence_present=True, max_version=7967, nextval=allocated)
            assert _next_workflow_config_version(session) > 7967, allocated
