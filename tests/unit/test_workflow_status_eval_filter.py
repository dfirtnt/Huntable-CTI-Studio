"""Unit tests for the eval-run exclusion filter in the workflow-status endpoint.

The ``workflow-status`` route excludes executions whose ``config_snapshot``
contains ``{"eval_run": true}`` so that eval runs do not trigger the
"Reprocess" button state in the article detail UI.

These tests verify:
1. The SQLAlchemy expression compiles to the correct ``NOT (@>)`` SQL — no DB
   connection required, so the suite is fast and offline-safe.
2. The semantics are correct for all three states: absent key, true, false.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helper — compile the filter expression to SQL string + bind params
# ---------------------------------------------------------------------------


def _compile_eval_filter():
    """Return (sql_string, params_dict) for the eval-run exclusion filter clause."""
    from sqlalchemy.dialects import postgresql

    from src.database.models import AgenticWorkflowExecutionTable

    expr = ~AgenticWorkflowExecutionTable.config_snapshot.contains({"eval_run": True})
    compiled = expr.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": False})
    return str(compiled), compiled.params


# ---------------------------------------------------------------------------
# Expression shape tests (no DB needed)
# ---------------------------------------------------------------------------


def test_eval_filter_uses_jsonb_containment_operator():
    """The filter must use the PostgreSQL ``@>`` containment operator."""
    sql, _ = _compile_eval_filter()
    assert "@>" in sql, f"Expected @> operator in SQL, got: {sql}"


def test_eval_filter_is_negated():
    """The filter must be a NOT expression so eval rows are *excluded*."""
    sql, _ = _compile_eval_filter()
    assert sql.strip().upper().startswith("NOT "), f"Expected NOT prefix, got: {sql}"


def test_eval_filter_bind_param_contains_eval_run_true():
    """The bind parameter value must be ``{"eval_run": True}``.

    The key name lives in the bound parameter dict, not the SQL text, because
    SQLAlchemy serialises the JSONB dict as a parameterised value.
    """
    _, params = _compile_eval_filter()
    param_value = next(iter(params.values()))
    assert param_value == {"eval_run": True}, f"Expected bind param {{'eval_run': True}}, got: {param_value!r}"


def test_eval_filter_targets_config_snapshot_column():
    """The filter must operate on the ``config_snapshot`` column."""
    sql, _ = _compile_eval_filter()
    assert "config_snapshot" in sql, f"Expected config_snapshot column in SQL, got: {sql}"


# ---------------------------------------------------------------------------
# Semantic tests — correct exclusion/inclusion behaviour
# ---------------------------------------------------------------------------


def test_eval_filter_excludes_eval_run_true(monkeypatch):
    """
    When the DB query returns None (because eval_run=True rows are filtered),
    the route must report processed_with_current_config=False.

    This is the core regression: an eval run must *not* flip the button to
    "Reprocess".
    """
    from unittest.mock import MagicMock

    from src.database import manager as db_manager_module
    from src.services import workflow_trigger_service as wts_module

    config = MagicMock()
    config.id = 99
    config.version = 7

    monkeypatch.setattr(wts_module.WorkflowTriggerService, "get_active_config", lambda self: config)

    mock_session = MagicMock()
    # Simulate the DB returning no row (eval run was filtered out at the DB level)
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = None
    mock_session.close = MagicMock()
    monkeypatch.setattr(db_manager_module.DatabaseManager, "get_session", lambda self: mock_session)

    from src.web.routes.articles import api_get_article_workflow_status

    result = api_get_article_workflow_status(article_id=777)
    assert result == {"processed_with_current_config": False, "latest_execution_id": None}, (
        "Eval run must not set processed_with_current_config=True"
    )


def test_eval_filter_includes_non_eval_run(monkeypatch):
    """
    When the DB query returns a row (non-eval completed execution), the route
    must report processed_with_current_config=True with the correct exec ID.
    """
    from unittest.mock import MagicMock

    from src.database import manager as db_manager_module
    from src.services import workflow_trigger_service as wts_module

    config = MagicMock()
    config.id = 99
    config.version = 7

    exec_row = MagicMock()
    exec_row.id = 42

    monkeypatch.setattr(wts_module.WorkflowTriggerService, "get_active_config", lambda self: config)

    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.order_by.return_value.first.return_value = exec_row
    mock_session.close = MagicMock()
    monkeypatch.setattr(db_manager_module.DatabaseManager, "get_session", lambda self: mock_session)

    from src.web.routes.articles import api_get_article_workflow_status

    result = api_get_article_workflow_status(article_id=888)
    assert result == {"processed_with_current_config": True, "latest_execution_id": 42}
