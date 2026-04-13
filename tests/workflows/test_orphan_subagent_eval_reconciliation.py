"""Tests for orphan SubagentEvaluationTable reconciliation on workflow failure.

Regression coverage: when a workflow execution fails before reaching
extract_agent (e.g. during os_detection due to pool corruption), any linked
subagent_evaluations rows stay in "pending" forever. The eval report then
cannot distinguish in-flight work from runaway failures.

_mark_pending_subagent_evals_as_failed converts them to "failed" at terminal
failure points.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.workflows.agentic_workflow import _mark_pending_subagent_evals_as_failed

pytestmark = pytest.mark.unit


def _make_row(status="pending"):
    """Simulate a SubagentEvaluationTable row with the fields we mutate."""
    return SimpleNamespace(status=status, completed_at=None)


def _query_returning(pending_rows):
    """Build a chained mock matching db_session.query(...).filter(...).all()."""
    query = MagicMock()
    filtered = MagicMock()
    filtered.all.return_value = pending_rows
    query.filter.return_value = filtered
    return query


def test_marks_pending_rows_as_failed():
    pending = [_make_row(), _make_row(), _make_row()]
    db_session = MagicMock()
    db_session.query.return_value = _query_returning(pending)
    execution = SimpleNamespace(id=42)

    updated = _mark_pending_subagent_evals_as_failed(execution, db_session)

    assert updated == 3
    assert all(row.status == "failed" for row in pending)
    assert all(row.completed_at is not None for row in pending)
    db_session.commit.assert_called_once()


def test_returns_zero_when_no_pending_rows():
    db_session = MagicMock()
    db_session.query.return_value = _query_returning([])
    execution = SimpleNamespace(id=42)

    updated = _mark_pending_subagent_evals_as_failed(execution, db_session)

    assert updated == 0
    db_session.commit.assert_not_called()


def test_handles_missing_execution_safely():
    db_session = MagicMock()
    # Both None and an execution without an id should be inert no-ops.
    assert _mark_pending_subagent_evals_as_failed(None, db_session) == 0
    assert _mark_pending_subagent_evals_as_failed(SimpleNamespace(id=None), db_session) == 0
    db_session.query.assert_not_called()


def test_rolls_back_on_commit_failure():
    pending = [_make_row()]
    db_session = MagicMock()
    db_session.query.return_value = _query_returning(pending)
    db_session.commit.side_effect = RuntimeError("db unreachable")
    execution = SimpleNamespace(id=7)

    # Must not propagate; must attempt rollback.
    updated = _mark_pending_subagent_evals_as_failed(execution, db_session)

    assert updated == 0
    db_session.rollback.assert_called_once()
