"""Tests for orphan SigmaEvaluationTable reconciliation on workflow failure.

Regression coverage (the "§5" gap): the ``has_error`` completion branch of the
agentic workflow marks the execution ``failed`` but historically did NOT
reconcile pending ``sigma_evaluations`` rows. The outer ``except`` (raised
exceptions) called ``mark_pending_sigma_evals_as_failed``, but a workflow that
finished ``ainvoke()`` with an error *in state* (no raise) left its
SigmaEvaluation row stranded in ``pending`` forever -- exactly the perpetual
PENDING row the end-to-end Sigma eval surfaces.

``mark_pending_sigma_evals_as_failed`` converts them to ``failed``; this module
locks down both the function behavior and that the has_error branch wires it.
Mirrors ``test_orphan_subagent_eval_reconciliation.py`` for the sigma path.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.services.sigma_eval_service import mark_pending_sigma_evals_as_failed

pytestmark = pytest.mark.unit


def _make_row(status="pending"):
    """Simulate a SigmaEvaluationTable row with the fields we mutate."""
    return SimpleNamespace(status=status, completed_at=None)


def _query_returning(pending_rows):
    """Build a chained mock matching db_session.query(...).filter(...).all()."""
    query = MagicMock()
    filtered = MagicMock()
    filtered.all.return_value = pending_rows
    query.filter.return_value = filtered
    return query


def test_marks_pending_sigma_rows_as_failed():
    pending = [_make_row(), _make_row(), _make_row()]
    db_session = MagicMock()
    db_session.query.return_value = _query_returning(pending)
    execution = SimpleNamespace(id=42)

    updated = mark_pending_sigma_evals_as_failed(execution, db_session)

    assert updated == 3
    assert all(row.status == "failed" for row in pending)
    assert all(row.completed_at is not None for row in pending)
    db_session.commit.assert_called_once()


def test_returns_zero_when_no_pending_rows():
    db_session = MagicMock()
    db_session.query.return_value = _query_returning([])
    execution = SimpleNamespace(id=42)

    updated = mark_pending_sigma_evals_as_failed(execution, db_session)

    assert updated == 0
    db_session.commit.assert_not_called()


def test_handles_missing_execution_safely():
    db_session = MagicMock()
    # Both None and an execution without an id should be inert no-ops.
    assert mark_pending_sigma_evals_as_failed(None, db_session) == 0
    assert mark_pending_sigma_evals_as_failed(SimpleNamespace(id=None), db_session) == 0
    db_session.query.assert_not_called()


def test_rolls_back_on_commit_failure():
    pending = [_make_row()]
    db_session = MagicMock()
    db_session.query.return_value = _query_returning(pending)
    db_session.commit.side_effect = RuntimeError("db unreachable")
    execution = SimpleNamespace(id=7)

    # Must not propagate; must attempt rollback.
    updated = mark_pending_sigma_evals_as_failed(execution, db_session)

    assert updated == 0
    db_session.rollback.assert_called_once()


# ---------------------------------------------------------------------------
# §5 call-site regression: the has_error completion branch must reconcile
# pending Sigma eval rows. Source-level assertion (mirrors TestDeadCodeRemoval
# in test_agentic_workflow_helpers.py) because the completion handler is inline
# in the monolithic workflow runner with no isolated seam to invoke.
# ---------------------------------------------------------------------------


def test_has_error_branch_reconciles_pending_sigma_evals():
    """Before the fix, only the outer ``except`` called
    ``mark_pending_sigma_evals_as_failed``, so an error-in-state completion
    (which does not raise) stranded the SigmaEvaluation row in ``pending``. The
    has_error branch must call the reconciler too so the row reaches a terminal
    ``failed`` state."""
    import src.workflows.agentic_workflow as wf

    src = inspect.getsource(wf)
    # Isolate the `if has_error:` completion block, up to the sibling
    # `elif execution.status == "running":` at the same indentation.
    m = re.search(
        r"\n(?P<indent>[ \t]*)if has_error:\n(?P<body>.*?)\n(?P=indent)elif execution\.status == \"running\":",
        src,
        re.DOTALL,
    )
    assert m, "could not locate the has_error completion block in agentic_workflow"
    has_error_block = m.group("body")
    assert "mark_pending_sigma_evals_as_failed(execution, db_session)" in has_error_block, (
        "has_error completion branch must call mark_pending_sigma_evals_as_failed so "
        "pending Sigma eval rows are reconciled to 'failed' on error-in-state completions"
    )
